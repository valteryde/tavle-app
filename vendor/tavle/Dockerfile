# =============================================================================
# Collaborative Whiteboard - Production Dockerfile
# =============================================================================
# Multi-stage build for smaller image size
# Runs as non-root user for security

# -----------------------------------------------------------------------------
# Stage 1: Build dependencies
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies (build context = repo root; see docker-compose tavle service)
COPY tavle/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

# -----------------------------------------------------------------------------
# Stage 2: Production image
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS production

# Security: Create non-root user
RUN groupadd -r appgroup && \
    useradd -r -g appgroup -d /app -s /sbin/nologin appuser

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy application code (build context = repo root when using tavle/docker-compose.yml)
COPY --chown=appuser:appgroup tavle/ .

# Create logs directory
RUN mkdir -p /app/logs && chown appuser:appgroup /app/logs

# Remove unnecessary files
RUN rm -rf __pycache__ *.pyc .env .git .gitignore tests/ *.md

# Switch to non-root user
USER appuser

# Environment defaults
ENV FLASK_ENV=production \
    HOST=0.0.0.0 \
    PORT=5050 \
    WORKERS=1 \
    LOG_DIR=/app/logs \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 5050

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5050/health || exit 1

# Run with gunicorn (eventlet worker for WebSocket support)
# Note: Only 1 worker supported with SocketIO
CMD ["gunicorn", \
     "--worker-class", "eventlet", \
     "--workers", "1", \
     "--bind", "0.0.0.0:5050", \
     "--timeout", "120", \
     "--keep-alive", "5", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--capture-output", \
     "server:app"]
