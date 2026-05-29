# 🚀 Deployment Guide

**Collaborative Whiteboard - Production Deployment**

This guide covers deploying the whiteboard application to production with Docker.

---

## 📋 Prerequisites

- Docker 24.0+ and Docker Compose v2
- 2GB RAM minimum (4GB recommended for 300 users)
- Domain name (for production)
- SSL certificate (via reverse proxy)

---

## 🔐 Security Checklist

Before deploying, ensure you have:

- [x] `SECRET_KEY` - **Auto-generated** and stored in database on first run
- [ ] Generated secure `ADMIN_API_TOKEN` (or use web setup wizard)
- [ ] Generated secure `POSTGRES_PASSWORD`
- [ ] Configured `ALLOWED_ORIGINS` with your domain(s)
- [ ] Set `TAVLE_EMBED_FRAME_ANCESTORS` to each parent-app **origin** that may iframe boards (see below), unless `ALLOWED_ORIGINS` already lists only those origins (non-`*`)
- [ ] Set up SSL termination (Nginx, Traefik, Caddy, or cloud LB)
- [ ] Configured firewall rules (only expose ports 80/443)

---

## 🚀 Quick Start (Development)

```bash
# Clone and navigate to project
cd tavle_v2

# Start with Docker Compose
docker compose up -d

# View logs
docker compose logs -f app

# Access at http://localhost:5050
```

---

## 🏭 Production Deployment

### Step 1: Generate Secrets

The `SECRET_KEY` is **automatically generated** on first run and stored securely in the database. You only need to generate it manually if running multiple app instances that need to share sessions.

```bash
# (Optional) Generate SECRET_KEY for multi-instance deployments
python3 -c "import secrets; print(secrets.token_hex(32))"

# Generate ADMIN_API_TOKEN (or use web setup wizard at /setup)
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate POSTGRES_PASSWORD
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
```

### Step 2: Create Environment File

```bash
# Copy example and edit
cp .env.example .env
nano .env
```

**Required settings for production:**

```bash
# .env
# SECRET_KEY is auto-generated - only set for multi-instance deployments:
# SECRET_KEY=<your-64-char-hex-key>
ADMIN_API_TOKEN=<your-admin-token>
POSTGRES_PASSWORD=<your-db-password>
FLASK_ENV=production
ALLOWED_ORIGINS=https://whiteboard.yourdomain.com
```

### Parent-app iframe embed (`frame-ancestors`)

If your application iframes Tavle from another **origin** (e.g. `https://app.example.com` while Tavle is `https://whiteboard.example.com`), list every parent origin that may embed boards:

```bash
# Comma-separated; scheme + host + port (no path)
TAVLE_EMBED_FRAME_ANCESTORS=https://app.yourdomain.com,https://staging.yourdomain.com
```

If you omit this, a non-`*` **`ALLOWED_ORIGINS`** value is reused for `frame-ancestors`.  
**Development:** when both are unset (and `FLASK_ENV` is not production), `http://localhost:8000` and `http://127.0.0.1:8000` are added automatically so a local parent on :8000 can embed Tavle on :5050.

The same localhost pair is also used when `FLASK_ENV=production` but **`ALLOWED_ORIGINS` is `*`** (typical local Gunicorn), since there is no concrete origin list to inherit. For real production, set **`TAVLE_EMBED_FRAME_ANCESTORS`** or a non-`*` **`ALLOWED_ORIGINS`** that includes your parent app’s HTTPS origin.

**Legacy `CSP_POLICY`:** If you set a full `CSP_POLICY` string in Docker or systemd, any `frame-ancestors …` clause in it is **removed** when building the policy and replaced with the computed value above, so an old `frame-ancestors 'self'` entry cannot block cross-origin embeds.

### Board branding (`TAVLE_EXTRA_STYLESHEETS`)

Optional extra CSS for the **board page** (`/board/…`, `/b/…`) without forking templates. Sheets load **after** the built-in `/static/css/whiteboard.css`, so overrides win in the cascade.

- **Comma-separated** entries. Each entry is either:
  - A **same-origin path** starting with `/` (recommended with Docker): mount a file into the container and point at it, e.g. `/static/css/brand.css`. No CSP change needed (`'self'` already allows it).
  - An absolute **`http://` or `https://` URL** (e.g. CSS on your main app or CDN). With the **default** CSP (no custom `CSP_POLICY`), Tavle adds that URL’s **origin** to `style-src` and `font-src` automatically (for `@font-face`).

```bash
# Mount ./brand.css to /app/static/css/brand.css and reference it:
TAVLE_EXTRA_STYLESHEETS=/static/css/brand.css

# Multiple sheets (mix allowed):
TAVLE_EXTRA_STYLESHEETS=/static/css/brand.css,https://cdn.example.com/tavle-overrides.css
```

If you set a **custom `CSP_POLICY`**, external stylesheet origins are **not** patched into your policy. Tavle logs a startup warning; add those origins to **`style-src`** and **`font-src`** yourself.

Utility classes from Tailwind in the board HTML are unchanged by this setting; use your overlay CSS (specificity or future `--tavle-*` variables in upstream) to tune colors and chrome.

Mount your CSS into the container (or serve it from your main app) and point Tavle at a **browser-reachable** URL—for example:

```bash
TAVLE_EXTRA_STYLESHEETS=/static/css/brand.css
# Or load from your main app origin:
# TAVLE_EXTRA_STYLESHEETS=https://app.example.com/static/css/tavle-brand.css
```

Custom `@font-face` rules need matching `font-src` in Tavle’s CSP (extend `CSP_POLICY` or use same-origin font CSS). Default Tavle CSP allows `font-src` only from `'self'` and `cdn.jsdelivr.net`.

### Step 3: Deploy with Production Settings

```bash
# Build and start
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Check status
docker compose ps

# View logs
docker compose logs -f
```

### Step 4: Verify Deployment

```bash
# Check health endpoint
curl http://localhost:5050/health

# Expected response:
# {"database": "postgresql", "pool": {"available": 0, "in_use": 1, "max_connections": 32}, "status": "healthy"}
```

---

## 🔄 SSL/TLS Configuration

The application expects SSL termination at the reverse proxy level. Options:

### Option A: Nginx (Recommended)

```nginx
# /etc/nginx/sites-available/whiteboard
upstream whiteboard {
    server 127.0.0.1:5050;
}

server {
    listen 80;
    server_name whiteboard.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name whiteboard.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/whiteboard.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/whiteboard.yourdomain.com/privkey.pem;

    # Do not set X-Frame-Options here: Tavle uses CSP ``frame-ancestors`` so a parent app
    # on another origin can iframe boards. Proxy-level SAMEORIGIN would block that.
    add_header X-Content-Type-Options "nosniff" always;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    limit_conn_zone $binary_remote_addr zone=conn:10m;

    location / {
        proxy_pass http://whiteboard;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Rate limiting
        limit_req zone=api burst=20 nodelay;
        limit_conn conn 10;
    }

    # WebSocket specific
    location /socket.io/ {
        proxy_pass http://whiteboard/socket.io/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;  # 24 hours for WebSocket
    }
}
```

### Option B: Traefik (Docker-native)

Uncomment the Traefik service in `docker-compose.yml` and add labels to the app service.

### Option C: Cloud Load Balancer

Use your cloud provider's load balancer (AWS ALB, GCP LB, Azure LB) with SSL termination.

---

## 📊 Monitoring

### Health Check

```bash
# Application health
curl http://localhost:5050/health

# Docker health status
docker compose ps
```

### Logs

```bash
# All services
docker compose logs -f

# Application only
docker compose logs -f app

# Database only
docker compose logs -f db
```

### Log Files

Logs are stored in Docker volumes:
- Application logs: `app-logs` volume → `/app/logs/`
- Security events: `/app/logs/security.log`
- Application logs: `/app/logs/whiteboard.log`

```bash
# Access logs directly
docker compose exec app cat /app/logs/security.log
docker compose exec app tail -f /app/logs/whiteboard.log
```

---

## 🔧 Operations

### Backup Database

```bash
# Create backup
docker compose exec db pg_dump -U whiteboard whiteboard > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore backup
cat backup_20260110_120000.sql | docker compose exec -T db psql -U whiteboard whiteboard
```

### Update Application

```bash
# Pull latest code
git pull

# Rebuild and restart
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Verify
docker compose ps
curl http://localhost:5050/health
```

### Scale (Not recommended for SocketIO)

Due to WebSocket sticky session requirements, horizontal scaling requires additional configuration. For most deployments, vertical scaling (more CPU/RAM) is recommended.

---

## 🐛 Troubleshooting

### Container won't start

```bash
# Check logs
docker compose logs app

# Common issues:
# - Missing SECRET_KEY in production
# - Database connection failed (check db container)
# - Port already in use
```

### Database connection errors

```bash
# Check database health
docker compose exec db pg_isready -U whiteboard

# Check database logs
docker compose logs db

# Connect manually
docker compose exec db psql -U whiteboard whiteboard
```

### WebSocket connection issues

1. Ensure `ALLOWED_ORIGINS` includes your domain
2. Check reverse proxy WebSocket configuration
3. Verify firewall allows WebSocket connections

### High memory usage

```bash
# Check current usage
docker stats

# Restart application
docker compose restart app
```

---

## 📈 Performance Tuning

### For 300 Daily Users

The default configuration supports 300 daily users comfortably:

| Setting | Default | Notes |
|---------|---------|-------|
| `DB_MAX_CONNECTIONS` | 32 | Sufficient for 300 users |
| `WORKERS` | 1 | Required for SocketIO |
| Memory | 1GB limit | Increase for heavy boards |

### For Higher Load

1. **Vertical scaling**: Increase container memory/CPU limits
2. **Database**: Consider dedicated PostgreSQL server
3. **Redis**: Add Redis for SocketIO message queue (requires code changes)

---

## � Backup & Recovery

### What to Backup

| Data | Location | Method |
|------|----------|--------|
| PostgreSQL database | Docker volume `postgres_data` | `pg_dump` or volume snapshot |
| Application logs | Docker volume or `/app/logs` | Optional (for debugging) |

### Automated Daily Backup (Recommended)

Create a backup script:

```bash
#!/bin/bash
# /opt/whiteboard/backup.sh

BACKUP_DIR="/opt/whiteboard/backups"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30

# Create backup directory
mkdir -p $BACKUP_DIR

# Dump PostgreSQL database
docker compose exec -T db pg_dump -U whiteboard whiteboard | gzip > "$BACKUP_DIR/whiteboard_$DATE.sql.gz"

# Remove old backups
find $BACKUP_DIR -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete

echo "Backup completed: whiteboard_$DATE.sql.gz"
```

Add to crontab:
```bash
# Run daily at 2 AM
0 2 * * * /opt/whiteboard/backup.sh >> /var/log/whiteboard-backup.log 2>&1
```

### Manual Backup

```bash
# Quick database dump
docker compose exec -T db pg_dump -U whiteboard whiteboard > backup.sql

# Compressed backup
docker compose exec -T db pg_dump -U whiteboard whiteboard | gzip > backup_$(date +%Y%m%d).sql.gz
```

### Restore from Backup

```bash
# Stop the application (keep database running)
docker compose stop app

# Restore database
gunzip -c backup_20260110.sql.gz | docker compose exec -T db psql -U whiteboard whiteboard

# Restart application
docker compose start app
```

### SQLite Backup (Development)

If using SQLite for development:

```bash
# Simple file copy (while app is stopped)
cp whiteboard.db whiteboard_backup_$(date +%Y%m%d).db

# Or use SQLite's backup command (while running)
sqlite3 whiteboard.db ".backup 'whiteboard_backup.db'"
```

---

## �🔒 Security Hardening

### Additional Recommendations

1. **Network isolation**: Use Docker networks to isolate database
2. **Secrets management**: Use Docker secrets or HashiCorp Vault
3. **Regular updates**: Keep base images and dependencies updated
4. **Audit logging**: Monitor `/app/logs/security.log` for anomalies
5. **Rate limiting**: Configure at reverse proxy level for DDoS protection

### Firewall Rules

```bash
# Only expose necessary ports
ufw allow 80/tcp    # HTTP (redirect to HTTPS)
ufw allow 443/tcp   # HTTPS
ufw deny 5050/tcp   # Block direct app access
ufw deny 5432/tcp   # Block direct database access
```

---

## 📝 Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | No | Auto-generated | Flask session secret (auto-generated and stored in DB) |
| `ADMIN_API_TOKEN` | Yes* | dev token | Admin API authentication |
| `FLASK_ENV` | No | development | Set to `production` for prod |
| `DATABASE_URL` | No | SQLite | PostgreSQL connection URL |
| `POSTGRES_PASSWORD` | No | whiteboard | Database password |
| `ALLOWED_ORIGINS` | No | * | CORS allowed origins |
| `DB_MAX_CONNECTIONS` | No | 32 | Connection pool size |
| `LOG_LEVEL` | No | INFO | Logging verbosity |

*Required when `FLASK_ENV=production` (or complete setup via web UI)

---

## 📞 Support

For issues:
1. Check logs: `docker compose logs -f`
2. Review security log: `/app/logs/security.log`
3. Check health endpoint: `/health`
