"""
Peewee ORM models for the collaborative whiteboard.
SQLite-first design with easy PostgreSQL migration support.
Includes connection pooling for production PostgreSQL.
"""
import os
import json
import uuid
import secrets
from datetime import datetime
from peewee import (
    Model, SqliteDatabase,
    CharField, DateTimeField, FloatField, TextField, ForeignKeyField, BooleanField,
    IntegerField,
)
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# Database Configuration
# =============================================================================

DATABASE_URL = os.environ.get('DATABASE_URL')

# Connection pool settings (via environment variables)
DB_MAX_CONNECTIONS = int(os.environ.get('DB_MAX_CONNECTIONS', '32'))
DB_STALE_TIMEOUT = int(os.environ.get('DB_STALE_TIMEOUT', '300'))  # 5 minutes
DB_TIMEOUT = int(os.environ.get('DB_TIMEOUT', '30'))  # 30 seconds

if DATABASE_URL and DATABASE_URL.startswith('postgres'):
    # PostgreSQL with connection pooling for production
    from playhouse.pool import PooledPostgresqlExtDatabase
    from urllib.parse import urlparse
    
    # Parse DATABASE_URL
    parsed = urlparse(DATABASE_URL)
    
    db = PooledPostgresqlExtDatabase(
        parsed.path[1:],  # Remove leading '/' from path
        user=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port or 5432,
        max_connections=DB_MAX_CONNECTIONS,
        stale_timeout=DB_STALE_TIMEOUT,
        timeout=DB_TIMEOUT,
        autorollback=True,  # Auto-rollback on connection errors
    )
    
    logger.info(f"PostgreSQL connection pool initialized: max={DB_MAX_CONNECTIONS}, "
                f"stale_timeout={DB_STALE_TIMEOUT}s, timeout={DB_TIMEOUT}s")
else:
    # SQLite configuration (development/testing)
    _data_dir = os.environ.get('WHITEBOARD_DATA_DIR', '').strip()
    if _data_dir:
        os.makedirs(_data_dir, exist_ok=True)
        _db_path = os.path.join(_data_dir, 'whiteboard.db')
    else:
        _db_path = 'whiteboard.db'
    db = SqliteDatabase(_db_path, pragmas={
        'journal_mode': 'wal',
        'cache_size': -1 * 64000,  # 64MB
        'foreign_keys': 1,
        'ignore_check_constraints': 0,
    })
    
    if DATABASE_URL:
        logger.warning(f"DATABASE_URL set but not PostgreSQL: {DATABASE_URL[:20]}...")


class BaseModel(Model):
    """Base model with database binding."""
    class Meta:
        database = db


class Document(BaseModel):
    """Represents a whiteboard document/room."""
    id = CharField(primary_key=True, max_length=255)
    access_token = CharField(max_length=64, unique=True, index=True)  # Long token for URL access
    name = CharField(max_length=255, default='Untitled')
    is_active = BooleanField(default=True)  # Can be deactivated by admin
    # Monotonic change counter bumped on every stroke/image mutation.
    # Cheap signal for `has this changed since I last looked?` checks
    # without diffing payloads or relying on clock skew.
    version = IntegerField(default=0)
    # PNG render cache (base64, no data: prefix). Keyed by `render_cache_version`
    # so we can decide cheaply whether the cached image is still fresh.
    render_cache = TextField(null=True)
    render_cache_version = IntegerField(null=True)
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    def save(self, *args, **kwargs):
        self.updated_at = datetime.utcnow()
        return super().save(*args, **kwargs)

    def bump_version(self):
        """Increment `version` and invalidate the render cache.

        Callers should invoke this on any stroke/image mutation. We keep
        invalidation eager so consumers fetching a render after a write
        always get a fresh PNG, even before the next save() of the
        document itself.

        Also schedules a debounced outbound webhook notification (no-op
        when not configured).
        """
        try:
            self.version = (self.version or 0) + 1
        except TypeError:
            self.version = 1
        self.render_cache = None
        self.render_cache_version = None
        self.save()
        try:
            # Local import to avoid circular dependency at module load
            # (webhooks.py doesn't import models, but keeping the cost
            # close to the call site lets us hot-reload either independently).
            from webhooks import notify_board_updated
            notify_board_updated(self.id, int(self.version or 0), self.updated_at.isoformat())
        except Exception as exc:  # pragma: no cover - never block writes
            logger.debug(f'Webhook scheduling skipped: {exc}')

    def to_dict(self, include_strokes=True):
        result = {
            'id': self.id,
            'access_token': self.access_token,
            'name': self.name,
            'is_active': self.is_active,
            'version': int(self.version or 0),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
        if include_strokes:
            result['strokes'] = [stroke.to_dict() for stroke in self.strokes]
            result['images'] = [image.to_dict() for image in self.images]
        return result

    @classmethod
    def create_new(cls, name='Untitled'):
        """Create a new document with generated ID and access token."""
        doc_id = str(uuid.uuid4())
        access_token = secrets.token_urlsafe(32)  # 43 characters, URL-safe
        doc = cls.create(
            id=doc_id,
            access_token=access_token,
            name=name
        )
        return doc

    @classmethod
    def get_by_token(cls, token):
        """Get document by access token."""
        try:
            return cls.get(cls.access_token == token, cls.is_active == True)
        except cls.DoesNotExist:
            return None


class Stroke(BaseModel):
    """Represents a single stroke on the whiteboard."""
    id = CharField(primary_key=True, max_length=36)  # UUID
    document = ForeignKeyField(Document, backref='strokes', on_delete='CASCADE')
    points = TextField()  # JSON: [{x, y, pressure}, ...]
    color = CharField(max_length=20, default='#000000')
    stroke_width = FloatField(default=4.0)
    transform = TextField(default='{"x": 0, "y": 0, "scale": 1}')  # JSON: {x, y, scale}
    z_index = FloatField(default=0)  # Z-order for layering (shared with images)
    created_at = DateTimeField(default=datetime.now)

    def get_points(self):
        """Parse points JSON."""
        try:
            return json.loads(self.points) if self.points else []
        except json.JSONDecodeError:
            logger.error(f"Failed to decode points JSON for stroke {self.id}")
            return []
    

    def set_points(self, points_list):
        """Serialize points to JSON."""
        self.points = json.dumps(points_list)

    def get_transform(self):
        """Parse transform JSON."""
        try:
            return json.loads(self.transform) if self.transform else {'x': 0, 'y': 0, 'scale': 1}
        except json.JSONDecodeError:
            logger.error(f"Failed to decode transform JSON for stroke {self.id}")
            return {'x': 0, 'y': 0, 'scale': 1}
    

    def set_transform(self, transform_dict):
        """Serialize transform to JSON."""
        self.transform = json.dumps(transform_dict)

    def to_dict(self):
        return {
            'id': self.id,
            'documentId': self.document_id,
            'points': self.get_points(),
            'color': self.color,
            'strokeWidth': self.stroke_width,
            'transform': self.get_transform(),
            'zIndex': self.z_index,
            'createdAt': self.created_at.isoformat()
        }

    @classmethod
    def create_new(cls, document_id, points, color='#000000', stroke_width=4.0, transform=None, z_index=0):
        """Create a new stroke with a generated UUID."""
        stroke_id = str(uuid.uuid4())
        stroke = cls(
            id=stroke_id,
            document_id=document_id,
            color=color,
            stroke_width=stroke_width,
            z_index=z_index
        )
        stroke.set_points(points)
        if transform:
            stroke.set_transform(transform)
        return stroke

class Image(BaseModel):
    """Represents an image on the whiteboard."""
    id = CharField(primary_key=True, max_length=36)  # UUID
    document = ForeignKeyField(Document, backref='images', on_delete='CASCADE')
    data = TextField()  # Base64 encoded image data
    x = FloatField(default=0)  # Position X
    y = FloatField(default=0)  # Position Y
    width = FloatField(default=200)  # Display width
    height = FloatField(default=200)  # Display height
    transform = TextField(default='{"x": 0, "y": 0, "scale": 1}')  # JSON: {x, y, scale}
    z_index = FloatField(default=0)  # Z-order for layering (shared with strokes)
    # Free-form JSON metadata. Integrators use this to tag images they inject
    # (e.g. `{"source": "my_app", "kind": "task_card", "task_id": "..."}`)
    # so the integrator can find/remove its own insertions without affecting
    # user-drawn content.
    meta = TextField(null=True)
    created_at = DateTimeField(default=datetime.now)

    def get_transform(self):
        """Parse transform JSON."""
        return json.loads(self.transform) if self.transform else {'x': 0, 'y': 0, 'scale': 1}

    def set_transform(self, transform_dict):
        """Serialize transform to JSON."""
        self.transform = json.dumps(transform_dict)

    def get_meta(self):
        """Parse meta JSON, defaulting to an empty dict."""
        if not self.meta:
            return {}
        try:
            value = json.loads(self.meta)
        except json.JSONDecodeError:
            logger.error(f"Failed to decode meta JSON for image {self.id}")
            return {}
        return value if isinstance(value, dict) else {}

    def set_meta(self, meta_dict):
        """Serialize meta dict to JSON (None clears it)."""
        if meta_dict is None:
            self.meta = None
        else:
            self.meta = json.dumps(meta_dict)

    def to_dict(self):
        return {
            'id': self.id,
            'documentId': self.document_id,
            'data': self.data,
            'x': self.x,
            'y': self.y,
            'width': self.width,
            'height': self.height,
            'transform': self.get_transform(),
            'zIndex': self.z_index,
            'meta': self.get_meta(),
            'createdAt': self.created_at.isoformat()
        }

    @classmethod
    def create_new(cls, document_id, data, x=0, y=0, width=200, height=200, transform=None, z_index=0, meta=None):
        """Create a new image with a generated UUID."""
        image_id = str(uuid.uuid4())
        image = cls(
            id=image_id,
            document_id=document_id,
            data=data,
            x=x,
            y=y,
            width=width,
            height=height,
            z_index=z_index
        )
        if transform:
            image.set_transform(transform)
        if meta is not None:
            image.set_meta(meta)
        return image


class Settings(BaseModel):
    """
    Key-value settings storage.
    Used for storing application configuration like API keys.
    """
    key = CharField(primary_key=True, max_length=100)
    value = TextField()
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    def save(self, *args, **kwargs):
        self.updated_at = datetime.utcnow()
        return super().save(*args, **kwargs)

    @classmethod
    def get_value(cls, key: str, default: str = None) -> str:
        """Get a setting value by key."""
        try:
            setting = cls.get_by_id(key)
            return setting.value
        except cls.DoesNotExist:
            return default

    @classmethod
    def set_value(cls, key: str, value: str) -> 'Settings':
        """Set a setting value (create or update)."""
        setting, created = cls.get_or_create(key=key, defaults={'value': value})
        if not created:
            setting.value = value
            setting.save()
        return setting


def init_db():
    """Initialize database tables and run migrations."""
    db.connect(reuse_if_open=True)
    db.create_tables([Document, Stroke, Image, Settings], safe=True)
    
    # Run migrations for existing databases
    _run_migrations()


def _table_columns(table_name):
    """Return the list of column names for a table, or [] if unknown."""
    try:
        cursor = db.execute_sql(f"PRAGMA table_info({table_name})")
        return [row[1] for row in cursor.fetchall()]
    except Exception:
        return []


def _add_column_if_missing(table, column, ddl_type, default_sql='NULL'):
    """Idempotently add a column to a table on either SQLite or PostgreSQL."""
    columns = _table_columns(table)
    if columns and column in columns:
        return
    try:
        logger.info(f"Migrating: Adding {column} column to {table} table")
        db.execute_sql(
            f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type} DEFAULT {default_sql}"
        )
        return
    except Exception as e:
        logger.warning(f"{table}.{column} migration via ALTER failed: {e}")
    try:
        db.execute_sql(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl_type} DEFAULT {default_sql}"
        )
    except Exception:
        pass


def _run_migrations():
    """Run database migrations for schema updates."""
    _add_column_if_missing('stroke', 'z_index', 'REAL', '0')
    _add_column_if_missing('image', 'z_index', 'REAL', '0')

    # Phase 1: change-tracking + render cache + image meta.
    _add_column_if_missing('document', 'version', 'INTEGER', '0')
    _add_column_if_missing('document', 'render_cache', 'TEXT', 'NULL')
    _add_column_if_missing('document', 'render_cache_version', 'INTEGER', 'NULL')
    _add_column_if_missing('image', 'meta', 'TEXT', 'NULL')


def get_or_create_document(doc_id):
    """Get existing document by ID (legacy support)."""
    try:
        return Document.get_by_id(doc_id)
    except Document.DoesNotExist:
        return None


def get_document_by_token(token):
    """Get document by access token."""
    return Document.get_by_token(token)


# =============================================================================
# Connection Management (for request lifecycle)
# =============================================================================

def open_db_connection():
    """
    Open a database connection (for request start).
    For pooled connections, this acquires from the pool.
    """
    if db.is_closed():
        db.connect(reuse_if_open=True)


def close_db_connection():
    """
    Close database connection (for request end).
    For pooled connections, this returns connection to the pool.
    """
    if not db.is_closed():
        db.close()


def get_pool_status():
    """
    Get connection pool status (PostgreSQL only).
    Returns None for SQLite.
    """
    if hasattr(db, '_in_use') and hasattr(db, '_connections'):
        return {
            'in_use': len(db._in_use),
            'available': len(db._connections),
            'max_connections': DB_MAX_CONNECTIONS,
        }
    return None


def is_postgresql():
    """Check if using PostgreSQL."""
    return DATABASE_URL and DATABASE_URL.startswith('postgres')
