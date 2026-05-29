"""
SocketIO event handlers for real-time collaboration.
Security-hardened with input validation, server-side sessions, and rate limiting.
"""
import time
import logging
from collections import defaultdict
from flask import request
from flask_socketio import join_room, leave_room, emit

from models import get_document_by_token, Document, Stroke, Image
from validators import (
    validate_join_event,
    validate_stroke_point_event,
    validate_stroke_complete_event,
    validate_stroke_update_event,
    validate_stroke_delete_event,
    validate_image_add_event,
    validate_image_update_event,
    validate_image_delete_event,
    validate_cursor_move_event,
    MAX_STROKES_PER_BOARD,
    MAX_IMAGES_PER_BOARD,
)

# =============================================================================
# Logging
# =============================================================================

logger = logging.getLogger(__name__)
security_logger = logging.getLogger('security')

# =============================================================================
# WebSocket Rate Limiter
# =============================================================================

class SocketRateLimiter:
    """Rate limiter for WebSocket events."""
    
    def __init__(self):
        self.events = defaultdict(lambda: {'count': 0, 'reset_time': time.time()})
        # (max_events, window_seconds)
        # Limits are designed to stop abuse, not restrict power users
        self.limits = {
            'stroke-point': (1000, 1),     # 1000 per second (smooth drawing)
            'stroke-complete': (500, 1),   # 500 per second
            'stroke-update': (5000, 1),    # 5000 per second (bulk move operations)
            'stroke-delete': (1000, 1),    # 1000 per second (bulk delete)
            'cursor-move': (60, 1),        # 60 per second
            'image-add': (50, 60),         # 50 per minute
            'image-update': (1000, 1),     # 1000 per second (bulk move)
            'image-delete': (500, 1),      # 500 per second (bulk delete)
            'clear': (5, 60),              # 5 per minute
            'join': (60, 60),              # 60 per minute
            'leave': (60, 60),             # 60 per minute
            'default': (200, 1)            # 200 per second default
        }
    
    def is_allowed(self, sid: str, event: str) -> bool:
        """Check if event is allowed under rate limit."""
        # Use IP address instead of sid for rate limiting to prevent multiple tab abuse
        # Fallback to sid if remote_addr is not available (e.g. testing)
        identifier = request.remote_addr or sid
        
        limit, window = self.limits.get(event, self.limits['default'])
        key = f"{identifier}:{event}"
        now = time.time()
        
        entry = self.events[key]
        if now > entry['reset_time'] + window:
            entry['count'] = 0
            entry['reset_time'] = now
        
        entry['count'] += 1
        return entry['count'] <= limit
    
    def cleanup_stale(self, max_age: float = 300):
        """Remove entries older than max_age seconds."""
        now = time.time()
        stale_keys = [k for k, v in self.events.items() if now > v['reset_time'] + max_age]
        for key in stale_keys:
            del self.events[key]


socket_rate_limiter = SocketRateLimiter()

# =============================================================================
# Server-Side Session Management
# =============================================================================

# Stores session data for each connected socket: sid -> {token, user_id, user_name, doc_id}
socket_sessions = {}


def get_session(sid: str = None) -> dict:
    """Get session data for a socket connection."""
    sid = sid or request.sid
    return socket_sessions.get(sid, {})


def get_session_token(sid: str = None) -> str:
    """Get the authorized token for a socket session."""
    return get_session(sid).get('token')


def rate_limit_check(event: str) -> bool:
    """Check rate limit for current socket. Returns False if exceeded."""
    sid = request.sid
    if not socket_rate_limiter.is_allowed(sid, event):
        security_logger.warning(
            f"Rate limit exceeded: sid={sid}, event={event}, "
            f"ip={request.remote_addr}"
        )
        emit('error', {'message': 'Rate limit exceeded', 'event': event, 'code': 'RATE_LIMITED'})
        return False
    return True


def require_session(func):
    """Decorator to require valid session for socket events."""
    def wrapper(*args, **kwargs):
        token = get_session_token()
        if not token:
            # Log at DEBUG level for high-frequency events to reduce noise
            high_freq_events = {'handle_cursor_move', 'handle_stroke_point'}
            if func.__name__ in high_freq_events:
                logger.debug(
                    f"Unauthenticated access attempt: sid={request.sid}, "
                    f"event={func.__name__}, ip={request.remote_addr}"
                )
            else:
                security_logger.warning(
                    f"Unauthenticated access attempt: sid={request.sid}, "
                    f"event={func.__name__}, ip={request.remote_addr}"
                )
            emit('error', {'message': 'Not authenticated. Please rejoin the room.', 'code': 'AUTH_REQUIRED'})
            return
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


# =============================================================================
# Helper Functions
# =============================================================================

def get_doc_from_token(token):
    """Helper to get document from token, returns (doc, doc_id) or (None, None)."""
    if not token:
        return None, None
    doc = get_document_by_token(token)
    if not doc:
        return None, None
    return doc, doc.id


def _bump_doc_version_silently(doc_id):
    """Increment the document version counter without raising.

    Called from socket event handlers on every successful mutation. We
    swallow errors deliberately - failing to bump the cache invalidator
    shouldn't drop a stroke / image that's already been persisted.
    """
    if not doc_id:
        return
    try:
        doc = Document.get_by_id(doc_id)
        doc.bump_version()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f'Failed to bump version for doc {doc_id}: {exc}')


# =============================================================================
# Register Socket Event Handlers
# =============================================================================

def register_socketio_handlers(socketio):
    """Register all SocketIO event handlers with the given socketio instance."""
    
    @socketio.on('connect')
    def handle_connect():
        """Handle client connection."""
        socket_sessions[request.sid] = {}
        logger.info(f'Client connected: {request.sid}')

    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection."""
        session = socket_sessions.pop(request.sid, None)
        if session and session.get('token'):
            # Notify others that user left
            emit('user-left', {'userId': session.get('user_id')}, 
                 to=session['token'], include_self=False)
        logger.info(f'Client disconnected: {request.sid}')
        
        # Periodic cleanup of rate limiter
        socket_rate_limiter.cleanup_stale()

    @socketio.on('join')
    def handle_join(data):
        """
        Join a document room for real-time collaboration.
        data: { tokenId: string, userId: string, userName: string }
        """
        # Rate limit check
        if not rate_limit_check('join'):
            return
        
        # Validate input
        is_valid, validated, error = validate_join_event(data)
        if not is_valid:
            security_logger.warning(f'Invalid join data from {request.sid}: {error}')
            emit('error', {'message': f'Invalid data: {error}'})
            return
        
        token = validated['tokenId']
        user_id = validated['userId']
        user_name = validated['userName']
        
        # Verify token is valid
        doc, doc_id = get_doc_from_token(token)
        if not doc:
            security_logger.warning(
                f"Invalid token attempt: sid={request.sid}, "
                f"token={token[:10]}..., ip={request.remote_addr}"
            )
            emit('error', {'message': 'Invalid token'})
            return
        
        # Store session data server-side (this is the key security fix)
        socket_sessions[request.sid] = {
            'token': token,
            'user_id': user_id,
            'user_name': user_name,
            'doc_id': doc_id
        }
        
        # Use token as room ID
        join_room(token)
        emit('joined', {'tokenId': token, 'message': 'Joined room'})
        logger.info(f'Client {user_name} ({user_id}) joined room: {token[:10]}...')
        
        # Notify others that a user joined
        if user_id:
            emit('user-joined', {
                'userId': user_id,
                'userName': user_name
            }, to=token, include_self=False)

    @socketio.on('leave')
    def handle_leave(data):
        """
        Leave a document room.
        data: { tokenId: string, userId: string }
        """
        if not rate_limit_check('leave'):
            return
        
        # Use server-side session token, not client-provided
        session = get_session()
        token = session.get('token')
        user_id = session.get('user_id')
        
        if token:
            leave_room(token)
            logger.info(f'Client {user_id} left room: {token[:10]}...')
            
            # Notify others that a user left
            if user_id:
                emit('user-left', {'userId': user_id}, to=token, include_self=False)
        
        # Clear session
        socket_sessions.pop(request.sid, None)

    @socketio.on('cursor-move')
    @require_session
    def handle_cursor_move(data):
        """
        Broadcast cursor position to other users in the room.
        data: { cursor: {x, y} }
        """
        if not rate_limit_check('cursor-move'):
            return
        
        # Validate input
        is_valid, validated, error = validate_cursor_move_event(data)
        if not is_valid:
            return  # Silently drop invalid cursor moves (high frequency event)
        
        # Use server-side session data
        session = get_session()
        token = session.get('token')
        
        # Broadcast with server-verified data
        emit('remote-cursor', {
            'userId': session.get('user_id'),
            'userName': session.get('user_name'),
            'cursor': validated['cursor']
        }, to=token, include_self=False)

    @socketio.on('stroke-point')
    @require_session
    def handle_stroke_point(data):
        """
        Broadcast a stroke point to other users in the room.
        data: { point: {x, y, pressure}, color, strokeWidth, strokeId }
        """
        if not rate_limit_check('stroke-point'):
            return
        
        # Validate input
        is_valid, validated, error = validate_stroke_point_event(data)
        if not is_valid:
            return  # Silently drop invalid points (high frequency event)
        
        # Use server-side session token
        token = get_session_token()
        
        # Broadcast validated data
        emit('remote-stroke-point', {
            'strokeId': validated['strokeId'],
            'point': validated['point'],
            'color': validated['color'],
            'strokeWidth': validated['strokeWidth']
        }, to=token, include_self=False)

    @socketio.on('stroke-complete')
    @require_session
    def handle_stroke_complete(data):
        """
        Broadcast completed stroke and persist to database.
        data: { strokeId, points: [{x, y, pressure}], color, strokeWidth, transform }
        """
        if not rate_limit_check('stroke-complete'):
            return
        
        # Validate input
        is_valid, validated, error = validate_stroke_complete_event(data)
        if not is_valid:
            security_logger.warning(f'Invalid stroke-complete from {request.sid}: {error}')
            emit('error', {'message': f'Invalid stroke data: {error}'})
            return
        
        # Use server-side session
        session = get_session()
        token = session.get('token')
        doc_id = session.get('doc_id')
        
        doc, _ = get_doc_from_token(token)
        if not doc:
            emit('error', {'message': 'Session expired'})
            return
        
        # Check board limits
        stroke_count = Stroke.select().where(Stroke.document_id == doc_id).count()
        if stroke_count >= MAX_STROKES_PER_BOARD:
            emit('error', {'message': f'Board stroke limit reached ({MAX_STROKES_PER_BOARD})'})
            return
        
        # Persist stroke to database with validated data
        try:
            stroke = Stroke.create_new(
                document_id=doc_id,
                points=validated['points'],
                color=validated['color'],
                stroke_width=validated['strokeWidth'],
                transform=validated['transform'],
                z_index=validated['zIndex']
            )
            stroke.id = validated['strokeId']
            stroke.save(force_insert=True)
            doc.bump_version()
        except Exception as e:
            logger.error(f'Error saving stroke: {e}')
            emit('error', {'message': 'Failed to save stroke'})
            return
        
        # Broadcast validated data to others
        emit('remote-stroke-complete', {
            'strokeId': validated['strokeId'],
            'points': validated['points'],
            'color': validated['color'],
            'strokeWidth': validated['strokeWidth'],
            'transform': validated['transform'],
            'zIndex': validated['zIndex']
        }, to=token, include_self=False)

    @socketio.on('stroke-update')
    @require_session
    def handle_stroke_update(data):
        """
        Broadcast stroke update (move/transform) and persist.
        data: { strokeId, transform: {x, y, scale} }
        """
        if not rate_limit_check('stroke-update'):
            return
        
        # Validate input
        is_valid, validated, error = validate_stroke_update_event(data)
        if not is_valid:
            emit('error', {'message': f'Invalid data: {error}'})
            return
        
        # Use server-side session
        session = get_session()
        token = session.get('token')
        doc_id = session.get('doc_id')
        
        stroke_id = validated['strokeId']
        
        # Update in database
        try:
            stroke = Stroke.get((Stroke.id == stroke_id) & (Stroke.document_id == doc_id))
            stroke.set_transform(validated['transform'])
            stroke.save()
            _bump_doc_version_silently(doc_id)
        except Stroke.DoesNotExist:
            logger.warning(f'Stroke not found: {stroke_id}')
            return  # Silently ignore - may be deleted by another user
        except Exception as e:
            logger.error(f'Error updating stroke: {e}')
            return
        
        # Broadcast validated data to others
        emit('remote-stroke-update', {
            'strokeId': stroke_id,
            'transform': validated['transform']
        }, to=token, include_self=False)

    @socketio.on('stroke-delete')
    @require_session
    def handle_stroke_delete(data):
        """
        Broadcast stroke deletion and remove from database.
        data: { strokeId } or { strokeIds: [] }
        """
        if not rate_limit_check('stroke-delete'):
            return
        
        # Validate input
        is_valid, validated, error = validate_stroke_delete_event(data)
        if not is_valid:
            emit('error', {'message': f'Invalid data: {error}'})
            return
        
        # Use server-side session
        session = get_session()
        token = session.get('token')
        doc_id = session.get('doc_id')
        
        stroke_ids = validated['strokeIds']
        
        # Delete from database
        try:
            deleted = Stroke.delete().where(
                (Stroke.id.in_(stroke_ids)) & (Stroke.document_id == doc_id)
            ).execute()
            if deleted:
                _bump_doc_version_silently(doc_id)
            logger.info(f'Deleted {deleted} strokes from doc {doc_id[:8]}...')
        except Exception as e:
            logger.error(f'Error deleting strokes: {e}')
            return
        
        # Broadcast to others
        emit('remote-stroke-delete', {'strokeIds': stroke_ids}, to=token, include_self=False)

    @socketio.on('clear')
    @require_session
    def handle_clear(data):
        """
        Clear all strokes and images from a document.
        data: {}
        """
        if not rate_limit_check('clear'):
            return
        
        # Use server-side session
        session = get_session()
        token = session.get('token')
        doc_id = session.get('doc_id')
        user_name = session.get('user_name', 'Unknown')
        
        # Clear from database
        try:
            stroke_count = Stroke.delete().where(Stroke.document_id == doc_id).execute()
            image_count = Image.delete().where(Image.document_id == doc_id).execute()
            if stroke_count or image_count:
                _bump_doc_version_silently(doc_id)
            
            # Log this destructive action to security log
            security_logger.warning(
                f"Board cleared: user={user_name}, doc={doc_id[:8]}..., "
                f"strokes={stroke_count}, images={image_count}, "
                f"sid={request.sid}, ip={request.remote_addr}"
            )
            logger.info(f'Cleared {stroke_count} strokes and {image_count} images from doc {doc_id[:8]}...')
        except Exception as e:
            logger.error(f'Error clearing board: {e}')
            emit('error', {'message': 'Failed to clear board'})
            return
        
        # Broadcast to others
        emit('remote-clear', {}, to=token, include_self=False)

    @socketio.on('image-add')
    @require_session
    def handle_image_add(data):
        """
        Broadcast image addition and persist to database.
        data: { imageId, data, x, y, width, height, transform }
        """
        image_id = data.get('imageId') if isinstance(data, dict) else None

        def emit_image_add_error(message):
            emit('error', {
                'code': 'IMAGE_ADD_FAILED',
                'imageId': image_id,
                'message': message
            })

        if not rate_limit_check('image-add'):
            return
        
        # Validate input
        is_valid, validated, error = validate_image_add_event(data)
        if not is_valid:
            security_logger.warning(f'Invalid image-add from {request.sid}: {error}')
            emit_image_add_error(f'Invalid image data: {error}')
            return
        
        # Use server-side session
        session = get_session()
        token = session.get('token')
        doc_id = session.get('doc_id')
        
        doc, _ = get_doc_from_token(token)
        if not doc:
            emit_image_add_error('Session expired')
            return
        
        image_id = validated['imageId']

        # Check board limits
        image_count = Image.select().where(Image.document_id == doc_id).count()
        if image_count >= MAX_IMAGES_PER_BOARD:
            emit_image_add_error(f'Board image limit reached ({MAX_IMAGES_PER_BOARD})')
            return
        
        # Persist image to database with validated data
        try:
            image = Image.create_new(
                document_id=doc_id,
                data=validated['data'],
                x=validated['x'],
                y=validated['y'],
                width=validated['width'],
                height=validated['height'],
                transform=validated['transform'],
                z_index=validated['zIndex']
            )
            image.id = validated['imageId']
            image.save(force_insert=True)
            doc.bump_version()
        except Exception as e:
            logger.error(f'Error saving image: {e}')
            emit_image_add_error('Failed to save image')
            return
        
        # Broadcast validated data to others
        emit('remote-image-add', {
            'imageId': validated['imageId'],
            'data': validated['data'],
            'x': validated['x'],
            'y': validated['y'],
            'width': validated['width'],
            'height': validated['height'],
            'transform': validated['transform'],
            'zIndex': validated['zIndex']
        }, to=token, include_self=False)

    @socketio.on('image-update')
    @require_session
    def handle_image_update(data):
        """
        Broadcast image update (move/transform) and persist.
        data: { imageId, transform: {x, y, scale}, x, y, width, height }
        """
        if not rate_limit_check('image-update'):
            return
        
        # Validate input
        is_valid, validated, error = validate_image_update_event(data)
        if not is_valid:
            emit('error', {'message': f'Invalid data: {error}'})
            return
        
        # Use server-side session
        session = get_session()
        token = session.get('token')
        doc_id = session.get('doc_id')
        
        image_id = validated['imageId']
        
        # Update in database
        try:
            image = Image.get((Image.id == image_id) & (Image.document_id == doc_id))
            if 'transform' in validated:
                image.set_transform(validated['transform'])
            if 'x' in validated:
                image.x = validated['x']
            if 'y' in validated:
                image.y = validated['y']
            if 'width' in validated:
                image.width = validated['width']
            if 'height' in validated:
                image.height = validated['height']
            image.save()
            _bump_doc_version_silently(doc_id)
        except Image.DoesNotExist:
            logger.warning(f'Image not found: {image_id}')
            return  # Silently ignore - may be deleted by another user
        except Exception as e:
            logger.error(f'Error updating image: {e}')
            return
        
        # Broadcast validated data to others
        emit('remote-image-update', validated, to=token, include_self=False)

    @socketio.on('image-delete')
    @require_session
    def handle_image_delete(data):
        """
        Broadcast image deletion and remove from database.
        data: { imageId } or { imageIds: [] }
        """
        if not rate_limit_check('image-delete'):
            return
        
        # Validate input
        is_valid, validated, error = validate_image_delete_event(data)
        if not is_valid:
            emit('error', {'message': f'Invalid data: {error}'})
            return
        
        # Use server-side session
        session = get_session()
        token = session.get('token')
        doc_id = session.get('doc_id')
        
        image_ids = validated['imageIds']
        
        # Delete from database
        try:
            deleted = Image.delete().where(
                (Image.id.in_(image_ids)) & (Image.document_id == doc_id)
            ).execute()
            if deleted:
                _bump_doc_version_silently(doc_id)
            logger.info(f'Deleted {deleted} images from doc {doc_id[:8]}...')
        except Exception as e:
            logger.error(f'Error deleting images: {e}')
            return
        
        # Broadcast to others
        emit('remote-image-delete', {'imageIds': image_ids}, to=token, include_self=False)
    
    logger.info('SocketIO handlers registered')
