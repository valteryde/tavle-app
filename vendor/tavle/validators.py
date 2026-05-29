"""
Input validation for WebSocket events and API requests.
Prevents injection attacks, DoS via large payloads, and data corruption.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

# =============================================================================
# Constants / Limits
# =============================================================================

MAX_POINTS_PER_STROKE = 10000
MAX_COORDINATE = 100000
MIN_COORDINATE = -100000
MAX_STROKE_WIDTH = 100
MIN_STROKE_WIDTH = 0.5
MAX_IMAGE_DATA_SIZE = 20 * 1024 * 1024  # 20MB base64 (approx 15MB image file)
MAX_STROKES_PER_BOARD = 10000
MAX_IMAGES_PER_BOARD = 50
MAX_USER_NAME_LENGTH = 50
MAX_STROKE_IDS_PER_DELETE = 100
MAX_IMAGE_IDS_PER_DELETE = 50
MAX_IMAGE_DIMENSION = 5000
MIN_IMAGE_DIMENSION = 10

# =============================================================================
# Regex Patterns
# =============================================================================

COLOR_PATTERN = re.compile(r'^#[0-9A-Fa-f]{6}$')
UUID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)
# Client-generated IDs: prefix-timestamp-random (e.g., stroke-1704067200000-abc123def)
CLIENT_ID_PATTERN = re.compile(r'^[a-zA-Z]+-\d+-[a-zA-Z0-9]+$')
DATA_URL_PATTERN = re.compile(r'^data:image/(png|jpeg|jpg|gif|webp|svg\+xml);base64,')


# =============================================================================
# Exception
# =============================================================================

class ValidationError(Exception):
    """Raised when validation fails."""
    pass


# =============================================================================
# Basic Validators
# =============================================================================

def validate_color(color: Any) -> str:
    """Validate and sanitize color value. Returns default if invalid."""
    if not isinstance(color, str):
        return '#000000'
    color = color.strip()
    if COLOR_PATTERN.match(color):
        return color.lower()
    return '#000000'


def validate_coordinate(value: Any, default: float = 0.0) -> float:
    """Validate coordinate is a reasonable number."""
    try:
        num = float(value)
        # NaN and Infinity check
        if num != num or num == float('inf') or num == float('-inf'):
            return default
        return max(MIN_COORDINATE, min(MAX_COORDINATE, num))
    except (TypeError, ValueError):
        return default


def validate_stroke_width(value: Any) -> float:
    """Validate stroke width within reasonable bounds."""
    try:
        num = float(value)
        if num != num:  # NaN check
            return 4.0
        return max(MIN_STROKE_WIDTH, min(MAX_STROKE_WIDTH, num))
    except (TypeError, ValueError):
        return 4.0


def validate_scale(value: Any) -> float:
    """Validate scale value."""
    try:
        num = float(value)
        if num != num or num <= 0:
            return 1.0
        return max(0.1, min(10.0, num))
    except (TypeError, ValueError):
        return 1.0


def validate_pressure(value: Any) -> float:
    """Validate pressure value (0.0 to 1.0)."""
    try:
        num = float(value)
        if num != num:
            return 0.5
        return max(0.0, min(1.0, num))
    except (TypeError, ValueError):
        return 0.5


def validate_uuid(value: Any) -> Optional[str]:
    """Validate UUID format. Returns None if invalid."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if UUID_PATTERN.match(value):
        return value.lower()
    return None


def validate_id(value: Any) -> Optional[str]:
    """
    Validate ID format - accepts both UUIDs and client-generated IDs.
    Client IDs are like: stroke-1704067200000-abc123def or image-1704067200000-xyz789
    Returns None if invalid.
    """
    if not isinstance(value, str):
        return None
    value = value.strip()
    
    # Check length limits (prevent extremely long IDs)
    if len(value) < 5 or len(value) > 100:
        return None
    
    # Accept UUID format
    if UUID_PATTERN.match(value):
        return value.lower()
    
    # Accept client-generated format: prefix-timestamp-random
    if CLIENT_ID_PATTERN.match(value):
        return value
    
    return None


def validate_user_name(name: Any) -> str:
    """Validate and sanitize user name."""
    if not isinstance(name, str):
        return 'Anonymous'
    # Remove HTML-like tags (basic XSS prevention)
    name = name.replace('<', '').replace('>', '')
    # Remove non-printable characters and strip
    clean = ''.join(c for c in name if c.isprintable())
    clean = clean.strip()[:MAX_USER_NAME_LENGTH]
    return clean or 'Anonymous'


# =============================================================================
# Complex Validators
# =============================================================================

def validate_point(point: Any) -> Optional[Dict]:
    """Validate a single point {x, y, pressure}."""
    if not isinstance(point, dict):
        return None
    
    return {
        'x': validate_coordinate(point.get('x', 0)),
        'y': validate_coordinate(point.get('y', 0)),
        'pressure': validate_pressure(point.get('pressure', 0.5))
    }


def validate_points(points: Any) -> List[Dict]:
    """Validate points array with size limit."""
    if not isinstance(points, list):
        return []
    
    validated = []
    for point in points[:MAX_POINTS_PER_STROKE]:
        validated_point = validate_point(point)
        if validated_point:
            validated.append(validated_point)
    
    return validated


def validate_transform(transform: Any) -> Dict:
    """Validate transform object {x, y, scale}."""
    default = {'x': 0, 'y': 0, 'scale': 1}
    if not isinstance(transform, dict):
        return default
    
    return {
        'x': validate_coordinate(transform.get('x', 0)),
        'y': validate_coordinate(transform.get('y', 0)),
        'scale': validate_scale(transform.get('scale', 1))
    }


def validate_cursor(cursor: Any) -> Optional[Dict]:
    """Validate cursor position {x, y}."""
    if not isinstance(cursor, dict):
        return None
    
    return {
        'x': validate_coordinate(cursor.get('x', 0)),
        'y': validate_coordinate(cursor.get('y', 0))
    }


def validate_image_data(data: Any) -> Optional[str]:
    """Validate image data URL format and size."""
    if not isinstance(data, str):
        return None
    
    # Check format (must be data URL with image MIME type)
    if not DATA_URL_PATTERN.match(data):
        return None
    
    # Check size
    if len(data) > MAX_IMAGE_DATA_SIZE:
        return None
    
    return data


def validate_image_dimension(value: Any, default: float = 200) -> float:
    """Validate image width/height."""
    try:
        num = float(value)
        if num != num:
            return default
        return max(MIN_IMAGE_DIMENSION, min(MAX_IMAGE_DIMENSION, num))
    except (TypeError, ValueError):
        return default


def validate_stroke_ids(ids: Any) -> List[str]:
    """Validate array of stroke IDs."""
    if not isinstance(ids, list):
        return []
    
    validated = []
    for id_val in ids[:MAX_STROKE_IDS_PER_DELETE]:
        valid_id = validate_id(id_val)
        if valid_id:
            validated.append(valid_id)
    
    return validated


def validate_image_ids(ids: Any) -> List[str]:
    """Validate array of image IDs."""
    if not isinstance(ids, list):
        return []
    
    validated = []
    for id_val in ids[:MAX_IMAGE_IDS_PER_DELETE]:
        valid_id = validate_id(id_val)
        if valid_id:
            validated.append(valid_id)
    
    return validated


# =============================================================================
# Event Validators (return sanitized data or error)
# =============================================================================

def validate_stroke_point_event(data: Dict) -> Tuple[bool, Dict, str]:
    """
    Validate stroke-point event data.
    Returns: (is_valid, sanitized_data, error_message)
    """
    if not isinstance(data, dict):
        return False, {}, 'Invalid data format'
    
    point = validate_point(data.get('point'))
    if not point:
        return False, {}, 'Invalid point data'
    
    stroke_id = validate_id(data.get('strokeId'))
    if not stroke_id:
        return False, {}, 'Invalid strokeId'
    
    return True, {
        'strokeId': stroke_id,
        'point': point,
        'color': validate_color(data.get('color')),
        'strokeWidth': validate_stroke_width(data.get('strokeWidth'))
    }, ''


def validate_stroke_complete_event(data: Dict) -> Tuple[bool, Dict, str]:
    """
    Validate stroke-complete event data.
    Returns: (is_valid, sanitized_data, error_message)
    """
    if not isinstance(data, dict):
        return False, {}, 'Invalid data format'
    
    stroke_id = validate_id(data.get('strokeId'))
    if not stroke_id:
        return False, {}, 'Invalid strokeId'
    
    points = validate_points(data.get('points', []))
    if len(points) < 1:
        return False, {}, 'Stroke must have at least 1 point'
    
    # Validate zIndex (optional, defaults to 0)
    z_index = 0
    if data.get('zIndex') is not None:
        try:
            z_index = float(data.get('zIndex', 0))
            if z_index != z_index:  # NaN check
                z_index = 0
        except (TypeError, ValueError):
            z_index = 0
    
    return True, {
        'strokeId': stroke_id,
        'points': points,
        'color': validate_color(data.get('color')),
        'strokeWidth': validate_stroke_width(data.get('strokeWidth')),
        'transform': validate_transform(data.get('transform')),
        'zIndex': z_index
    }, ''


def validate_stroke_update_event(data: Dict) -> Tuple[bool, Dict, str]:
    """
    Validate stroke-update event data.
    Returns: (is_valid, sanitized_data, error_message)
    """
    if not isinstance(data, dict):
        return False, {}, 'Invalid data format'
    
    stroke_id = validate_id(data.get('strokeId'))
    if not stroke_id:
        return False, {}, 'Invalid strokeId'
    
    return True, {
        'strokeId': stroke_id,
        'transform': validate_transform(data.get('transform'))
    }, ''


def validate_stroke_delete_event(data: Dict) -> Tuple[bool, Dict, str]:
    """
    Validate stroke-delete event data.
    Returns: (is_valid, sanitized_data, error_message)
    """
    if not isinstance(data, dict):
        return False, {}, 'Invalid data format'
    
    # Support both single strokeId and array strokeIds
    stroke_ids = data.get('strokeIds', [])
    if not stroke_ids and data.get('strokeId'):
        single_id = validate_id(data.get('strokeId'))
        stroke_ids = [single_id] if single_id else []
    else:
        stroke_ids = validate_stroke_ids(stroke_ids)
    
    if not stroke_ids:
        return False, {}, 'No valid stroke IDs provided'
    
    return True, {
        'strokeIds': stroke_ids
    }, ''


def validate_image_add_event(data: Dict) -> Tuple[bool, Dict, str]:
    """
    Validate image-add event data.
    Returns: (is_valid, sanitized_data, error_message)
    """
    if not isinstance(data, dict):
        return False, {}, 'Invalid data format'
    
    image_id = validate_id(data.get('imageId'))
    if not image_id:
        return False, {}, 'Invalid imageId'
    
    image_data = validate_image_data(data.get('data'))
    if not image_data:
        return False, {}, 'Invalid or missing image data (must be data URL, max 20MB)'
    
    # Validate zIndex (optional, defaults to 0)
    z_index = 0
    if data.get('zIndex') is not None:
        try:
            z_index = float(data.get('zIndex', 0))
            if z_index != z_index:  # NaN check
                z_index = 0
        except (TypeError, ValueError):
            z_index = 0
    
    return True, {
        'imageId': image_id,
        'data': image_data,
        'x': validate_coordinate(data.get('x', 0)),
        'y': validate_coordinate(data.get('y', 0)),
        'width': validate_image_dimension(data.get('width', 200)),
        'height': validate_image_dimension(data.get('height', 200)),
        'transform': validate_transform(data.get('transform')),
        'zIndex': z_index
    }, ''


def validate_image_update_event(data: Dict) -> Tuple[bool, Dict, str]:
    """
    Validate image-update event data.
    Returns: (is_valid, sanitized_data, error_message)
    """
    if not isinstance(data, dict):
        return False, {}, 'Invalid data format'
    
    image_id = validate_id(data.get('imageId'))
    if not image_id:
        return False, {}, 'Invalid imageId'
    
    result = {'imageId': image_id}
    
    # All fields are optional for update
    if data.get('transform') is not None:
        result['transform'] = validate_transform(data.get('transform'))
    if data.get('x') is not None:
        result['x'] = validate_coordinate(data.get('x'))
    if data.get('y') is not None:
        result['y'] = validate_coordinate(data.get('y'))
    if data.get('width') is not None:
        result['width'] = validate_image_dimension(data.get('width'))
    if data.get('height') is not None:
        result['height'] = validate_image_dimension(data.get('height'))
    
    return True, result, ''


def validate_image_delete_event(data: Dict) -> Tuple[bool, Dict, str]:
    """
    Validate image-delete event data.
    Returns: (is_valid, sanitized_data, error_message)
    """
    if not isinstance(data, dict):
        return False, {}, 'Invalid data format'
    
    # Support both single imageId and array imageIds
    image_ids = data.get('imageIds', [])
    if not image_ids and data.get('imageId'):
        single_id = validate_id(data.get('imageId'))
        image_ids = [single_id] if single_id else []
    else:
        image_ids = validate_image_ids(image_ids)
    
    if not image_ids:
        return False, {}, 'No valid image IDs provided'
    
    return True, {
        'imageIds': image_ids
    }, ''


def validate_cursor_move_event(data: Dict) -> Tuple[bool, Dict, str]:
    """
    Validate cursor-move event data.
    Returns: (is_valid, sanitized_data, error_message)
    """
    if not isinstance(data, dict):
        return False, {}, 'Invalid data format'
    
    cursor = validate_cursor(data.get('cursor'))
    if not cursor:
        return False, {}, 'Invalid cursor data'
    
    return True, {
        'userId': str(data.get('userId', ''))[:100] if data.get('userId') else '',
        'userName': validate_user_name(data.get('userName')),
        'cursor': cursor
    }, ''


def validate_join_event(data: Dict) -> Tuple[bool, Dict, str]:
    """
    Validate join event data.
    Returns: (is_valid, sanitized_data, error_message)
    """
    if not isinstance(data, dict):
        return False, {}, 'Invalid data format'
    
    token = data.get('tokenId')
    if not isinstance(token, str) or len(token) < 20 or len(token) > 100:
        return False, {}, 'Invalid token'
    
    return True, {
        'tokenId': token,
        'userId': str(data.get('userId', ''))[:100] if data.get('userId') else '',
        'userName': validate_user_name(data.get('userName'))
    }, ''
