"""
Main Flask application with SocketIO for real-time collaboration.
Security-hardened version with input validation, session management, and rate limiting.
"""
import os
import re
import logging
from logging.handlers import RotatingFileHandler
from urllib.parse import urlparse

from flask import Flask, render_template, request, abort, jsonify, redirect, url_for
from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from models import init_db, get_document_by_token, open_db_connection, close_db_connection, get_pool_status
from api import api_bp
from socketio_handlers import register_socketio_handlers
from setup import needs_setup, complete_setup, get_admin_token, get_secret_key, get_or_create_admin_token, mark_setup_complete
from docs import docs_bp
from validators import MAX_IMAGE_DATA_SIZE

# =============================================================================
# Logging Setup
# =============================================================================

def setup_logging(app_instance):
    """
    Configure production logging with file rotation.
    Creates separate logs for application and security events.
    """
    # Create logs directory
    log_dir = os.environ.get('LOG_DIR', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Determine log level from environment
    log_level = getattr(logging, os.environ.get('LOG_LEVEL', 'INFO').upper(), logging.INFO)
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s %(levelname)s [%(name)s] %(message)s'
    )
    
    # Application log with rotation (10MB, 5 backups)
    app_handler = RotatingFileHandler(
        os.path.join(log_dir, 'whiteboard.log'),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    app_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s [%(name)s] %(message)s'
    ))
    app_handler.setLevel(log_level)
    app_instance.logger.addHandler(app_handler)
    
    # Security log with rotation (10MB, 10 backups - keep more history)
    security_handler = RotatingFileHandler(
        os.path.join(log_dir, 'security.log'),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=10
    )
    security_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s [%(name)s] %(message)s'
    ))
    security_handler.setLevel(logging.WARNING)
    
    # Create security logger
    security_logger = logging.getLogger('security')
    security_logger.addHandler(security_handler)
    security_logger.setLevel(logging.WARNING)
    
    # Also add console handler for security events in production
    if os.environ.get('FLASK_ENV') == 'production':
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s SECURITY %(levelname)s %(message)s'
        ))
        security_logger.addHandler(console_handler)
    
    return security_logger


logger = logging.getLogger(__name__)

# =============================================================================
# Initialize Flask app
# =============================================================================

app = Flask(__name__)
app.config['SECRET_KEY'] = get_secret_key()

# Setup logging (creates security_logger as module-level for import by other modules)
security_logger = setup_logging(app)


def parse_tavle_extra_stylesheets(raw: str) -> tuple[list[str], list[str]]:
    """Parse ``TAVLE_EXTRA_STYLESHEETS`` env: comma-separated paths or https? URLs.

    Returns (hrefs_for_link_tags, unique_origins_for_csp). Paths must start with a
    single ``/`` (same-origin). ``//host`` protocol-relative URLs are rejected.
    """
    hrefs: list[str] = []
    csp_origins: list[str] = []
    if not raw or not str(raw).strip():
        return hrefs, csp_origins
    for part in str(raw).split(","):
        s = part.strip()
        if not s:
            continue
        if s.startswith("//"):
            logger.warning("Ignoring protocol-relative TAVLE_EXTRA_STYLESHEETS entry")
            continue
        if s.startswith("/"):
            hrefs.append(s)
            continue
        parsed = urlparse(s)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            hrefs.append(s)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            if origin not in csp_origins:
                csp_origins.append(origin)
            continue
        logger.warning("Ignoring invalid TAVLE_EXTRA_STYLESHEETS entry: %r", s[:120])
    return hrefs, csp_origins


def _resolve_tavle_extra_stylesheets_env() -> str:
    """Raw ``TAVLE_EXTRA_STYLESHEETS`` env; unset or empty means no extra sheets."""
    return (os.environ.get("TAVLE_EXTRA_STYLESHEETS") or "").strip()


_extra_sheet_hrefs, _extra_sheet_csp_origins = parse_tavle_extra_stylesheets(
    _resolve_tavle_extra_stylesheets_env()
)
app.config["TAVLE_EXTRA_STYLESHEET_HREFS"] = _extra_sheet_hrefs
app.config["TAVLE_EXTRA_STYLESHEET_CSP_ORIGINS"] = _extra_sheet_csp_origins
if _extra_sheet_hrefs:
    logger.info("Tavle extra stylesheets: %s", ", ".join(_extra_sheet_hrefs))
if os.environ.get("CSP_POLICY", "").strip() and _extra_sheet_csp_origins:
    logger.warning(
        "CSP_POLICY is set while TAVLE_EXTRA_STYLESHEETS includes external URLs; "
        "extend style-src and font-src in CSP_POLICY to include: %s",
        " ".join(_extra_sheet_csp_origins),
    )

# =============================================================================
# Production Security Checks
# =============================================================================

def check_production_config():
    """Ensure production configuration is secure."""
    is_production = (
        os.environ.get('FLASK_ENV') == 'production' or
        os.environ.get('ENVIRONMENT') == 'production'
    )
    
    if is_production and app.debug:
        logger.warning("Debug mode is enabled - should be disabled in production!")

# =============================================================================
# Initialize rate limiter (HTTP routes)
# =============================================================================

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    # Set reasonable default limits for anonymous users
    default_limits=["1000 per day", "200 per hour"],
    storage_uri="memory://",
)

# =============================================================================
# Initialize SocketIO with CORS restriction
# =============================================================================

# Get allowed origins from environment (comma-separated), default to * for dev
ALLOWED_ORIGINS = os.environ.get('ALLOWED_ORIGINS', '*')
if ALLOWED_ORIGINS != '*':
    ALLOWED_ORIGINS = [origin.strip() for origin in ALLOWED_ORIGINS.split(',')]

socketio = SocketIO(
    app,
    cors_allowed_origins=ALLOWED_ORIGINS,
    async_mode='eventlet',
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=MAX_IMAGE_DATA_SIZE
)

# Register all SocketIO event handlers
register_socketio_handlers(socketio)

# =============================================================================
# Security Headers
# =============================================================================


def _is_production():
    return (
        os.environ.get('FLASK_ENV') == 'production' or
        os.environ.get('ENVIRONMENT') == 'production'
    )


def _expand_localhost_origin_pairs(origins: list[str]) -> list[str]:
    """Add localhost <-> 127.0.0.1 variants for the same scheme/port."""
    out: list[str] = []
    seen: set[str] = set()
    pending = list(origins)
    while pending:
        origin = pending.pop(0)
        if not origin or origin in seen:
            continue
        seen.add(origin)
        out.append(origin)
        parsed = urlparse(origin)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            continue
        port_suffix = f':{parsed.port}' if parsed.port else ''
        alt_host = None
        if parsed.hostname == 'localhost':
            alt_host = '127.0.0.1'
        elif parsed.hostname == '127.0.0.1':
            alt_host = 'localhost'
        if alt_host:
            alt = f'{parsed.scheme}://{alt_host}{port_suffix}'
            if alt not in seen:
                pending.append(alt)
    return out


def _frame_ancestors_clause():
    """Who may embed Tavle board pages in an iframe.

    Tavle often runs on a different host/port than the parent app (e.g. :5050 vs :8000),
    so ``frame-ancestors 'self'`` alone blocks cross-origin iframe embeds.
    """
    raw = os.environ.get('TAVLE_EMBED_FRAME_ANCESTORS', '').strip()
    extras: list[str] = []
    if raw:
        extras = [x.strip() for x in raw.split(',') if x.strip()]
    else:
        ao_raw = os.environ.get('ALLOWED_ORIGINS', '*').strip()
        if ao_raw and ao_raw != '*':
            extras = [x.strip() for x in ao_raw.split(',') if x.strip()]
        # Gunicorn often sets FLASK_ENV=production while a local parent app still runs on
        # localhost:8000. With ALLOWED_ORIGINS=* there is no concrete origin list
        # to reuse — add typical local dev URLs so embeds work.
        if not extras and (not _is_production() or ao_raw in ('*', '')):
            extras = ['http://localhost:8000', 'http://127.0.0.1:8000']
    parts: list[str] = []
    for token in ["'self'"] + _expand_localhost_origin_pairs(extras):
        if token not in parts:
            parts.append(token)
    return 'frame-ancestors ' + ' '.join(parts)


def _build_default_csp():
    fa = _frame_ancestors_clause()
    extra_origins = list(app.config.get("TAVLE_EXTRA_STYLESHEET_CSP_ORIGINS") or [])
    origins_suffix = (" " + " ".join(extra_origins)) if extra_origins else ""
    style_src = f"'self' 'unsafe-inline' https://cdn.jsdelivr.net{origins_suffix}"
    font_src = f"'self' https://cdn.jsdelivr.net{origins_suffix}"
    return (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        f"style-src {style_src}; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' ws: wss:; "
        f"font-src {font_src}; "
        f"{fa};"
    )


_FRAME_ANCESTORS_DIRECTIVE_RE = re.compile(
    r"\s*frame-ancestors\s+[^;]+;?",
    re.IGNORECASE,
)


def _merge_csp_with_frame_ancestors(policy: str) -> str:
    """Remove any ``frame-ancestors`` from *policy*, then append our directive.

    ``CSP_POLICY`` is often set in Docker/.env to a legacy value ending in
    ``frame-ancestors 'self'``, which blocks the parent app when it runs on another
    origin (e.g. :8000 vs Tavle :5050). Always reconcile embed parents here.
    """
    cleaned = _FRAME_ANCESTORS_DIRECTIVE_RE.sub("", policy)
    cleaned = re.sub(r";{2,}", ";", cleaned)
    cleaned = cleaned.strip().strip(";").strip()
    fa = _frame_ancestors_clause()
    if not cleaned:
        return _build_default_csp()
    return f"{cleaned}; {fa}"


def _resolve_csp_policy() -> str:
    raw = os.environ.get("CSP_POLICY", "").strip()
    if raw:
        return _merge_csp_with_frame_ancestors(raw)
    return _build_default_csp()


@app.context_processor
def inject_tavle_theme():
    return {
        "tavle_extra_stylesheets": app.config.get("TAVLE_EXTRA_STYLESHEET_HREFS", []),
    }


@app.after_request
def add_security_headers(response):
    """Add security headers to all responses."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # Framing is governed only by CSP ``frame-ancestors`` (see ``_frame_ancestors_clause``).
    # ``X-Frame-Options: SAMEORIGIN`` would forbid cross-origin embeds (e.g. parent :8000
    # iframing Tavle :5050) on browsers that honor XFO alongside CSP.
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = _resolve_csp_policy()
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    return response

# =============================================================================
# Database Connection Management (for connection pooling)
# =============================================================================

@app.before_request
def before_request():
    """Open database connection before each request."""
    open_db_connection()


@app.teardown_request
def teardown_request(exception=None):
    """Close database connection after each request (returns to pool)."""
    close_db_connection()

# =============================================================================
# Error Handlers
# =============================================================================

@app.errorhandler(400)
def bad_request_error(error):
    """Handle 400 Bad Request errors."""
    return render_template('errors/400.html'), 400


@app.errorhandler(403)
def forbidden_error(error):
    """Handle 403 Forbidden errors."""
    return render_template('errors/403.html'), 403


@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 Not Found errors."""
    return render_template('errors/404.html'), 404


@app.errorhandler(429)
def too_many_requests_error(error):
    """Handle 429 Too Many Requests errors (rate limiting)."""
    return render_template('errors/429.html'), 429


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 Internal Server errors."""
    logger.error(f'Internal server error: {error}')
    return render_template('errors/500.html'), 500

# =============================================================================
# Register API blueprint
# =============================================================================

app.register_blueprint(api_bp)

# =============================================================================
# Public Routes
# =============================================================================

@app.route('/setup')
@limiter.limit("10 per minute")
def setup_page():
    """
    First-run setup page.
    Only accessible if setup hasn't been completed yet.
    Shows the generated admin API token.
    """
    if not needs_setup():
        # Setup already complete, redirect to landing
        return redirect(url_for('index'))
    
    # Get or generate the admin token (but don't mark setup as complete)
    admin_token = get_or_create_admin_token()
    
    return render_template('setup.html', 
                           admin_token=admin_token,
                           setup_complete=False)


@app.route('/setup/complete', methods=['POST'])
@limiter.limit("5 per minute")
def complete_setup_route():
    """
    Mark setup as complete when user confirms they've saved their token.
    """
    if not needs_setup():
        # Already complete
        return redirect(url_for('index'))
    
    mark_setup_complete()
    return redirect(url_for('index'))


@app.route('/')
@limiter.limit("60 per minute")
def index():
    """Landing page. Redirects to setup if first run."""
    if needs_setup():
        return redirect(url_for('setup_page'))
    return render_template('landing.html')


@app.route('/docs')
@limiter.limit("60 per minute")
def api_docs():
    """API Documentation page."""
    return render_template('docs.html')


@app.route('/board/<token>')
@app.route('/b/<token>')
@limiter.limit("120 per minute")
def board(token):
    """Render whiteboard for a specific document using access token.

    Supports query params for iframe hosts:

    * ``embed=1`` — adjusts toolbar placement for a framed viewport
    * ``nohud=1`` — hide toolbar and connection/user chrome (live gallery tiles)
    * ``readonly=1`` — watch-only: no local drawing or canvas interaction
    * ``name=<display name>`` — skip the name picker and join as that user
      (e.g. Studito passes the logged-in student's username)
    """
    doc = get_document_by_token(token)
    if not doc:
        abort(403)

    def _query_flag(name: str) -> bool:
        return (request.args.get(name) or '').strip() in ('1', 'true', 'yes')

    embed = _query_flag('embed')
    nohud = _query_flag('nohud')
    readonly = _query_flag('readonly')
    return render_template(
        'index.html',
        token_id=token,
        access_token=token,
        embed=embed,
        nohud=nohud,
        readonly=readonly,
    )


@app.route('/get/<token>')
@limiter.limit("120 per minute")
def get_document(token):
    """Get document data for rendering whiteboard (without exposing sensitive data)."""
    doc = get_document_by_token(token)
    
    if not doc:
        logger.info(f'Document not found for token: {token[:10]}...')
        abort(404)

    # Return sanitized data - remove sensitive fields
    result = doc.to_dict()
    result.pop('access_token', None)  # Don't expose token in response
    result.pop('id', None)  # Don't expose internal ID
    return result


@app.route('/health')
@limiter.exempt
def health_check():
    """
    Health check endpoint for monitoring.
    Returns database pool status in production.
    """
    pool_status = get_pool_status()
    
    return jsonify({
        'status': 'healthy',
        'database': 'postgresql' if pool_status else 'sqlite',
        'pool': pool_status,
    })


app.register_blueprint(docs_bp)

# =============================================================================
# Application Entry Point
# =============================================================================

# Check production configuration
# Must be run before starting the app
# Both in development and production to catch misconfigurations early
# Production uses gunicorn with eventlet, so this script is still run
check_production_config()

# Initialize database
init_db()


if __name__ == '__main__':
    _host = os.environ.get('TAVLE_HOST', '127.0.0.1').strip() or '127.0.0.1'
    _port = int(os.environ.get('PORT', '5050'))
    _debug = os.environ.get('FLASK_ENV', 'development') == 'development'

    logger.info('Starting whiteboard server on http://%s:%s', _host, _port)
    logger.info(f'CORS allowed origins: {ALLOWED_ORIGINS}')

    socketio.run(app, host=_host, port=_port, debug=_debug)
