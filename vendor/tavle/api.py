"""
Flask-RESTful API for document and stroke management.
All endpoints require admin API token authentication.
"""
import hashlib
import os
import secrets
from functools import wraps
from flask import Blueprint, Response, request, url_for
from flask_restful import Api, Resource, reqparse
from models import Document, Stroke, Image, get_or_create_document, db
from render import get_or_render_png, render_document_png
from setup import get_admin_token

api_bp = Blueprint('api', __name__, url_prefix='/api')
api = Api(api_bp)

def get_current_admin_token():
    """Get the current admin API token (called per-request to allow config reload)."""
    return get_admin_token()


def require_admin_token(f):
    """Decorator to require admin API token for a method."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return {'error': 'Missing Authorization header'}, 401
        
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return {'error': 'Invalid Authorization header format'}, 401
        
        if parts[1] != get_current_admin_token():
            return {'error': 'Invalid API token'}, 403
        
        return f(*args, **kwargs)
    return decorated


def get_document_or_404(doc_id):
    """Get document by ID or return None."""
    try:
        return Document.get_by_id(doc_id)
    except Document.DoesNotExist:
        return None


class DocumentedResource(Resource):
    """Base Resource that includes documentation metadata."""
    
    url = '/NOT_SET/'

    def __init__(self):
        super().__init__()
        self.parser = reqparse.RequestParser()


# =============================================================================
# Board/Document Resources
# =============================================================================

class BoardsResource(DocumentedResource):
    """
    GET /api/boards - List all boards
    POST /api/boards - Create new board
    """
    
    method_decorators = [require_admin_token]
    desc = 'Manage multiple whiteboards'
    url = '/boards'

    def __init__(self):
        super().__init__()
        self.parser.add_argument('name', type=str, default='Untitled')


    def get(self):
        """List all boards."""
        boards = Document.select().order_by(Document.created_at.desc())
        return {
            'boards': [b.to_dict(include_strokes=False) for b in boards],
            'count': boards.count()
        }, 200
    get.response = {"boards": "List of board objects without strokes/images", "count": "Integer"}
    
    def post(self):
        """Create a new board."""
        parser = reqparse.RequestParser()
        parser.add_argument('name', type=str, default='Untitled')
        args = parser.parse_args()
        
        doc = Document.create_new(name=args['name'])
        
        return {
            'board': doc.to_dict(include_strokes=False),
            'url': url_for('board', token=doc.access_token, _external=True)
        }, 201
    post.response = {"board": "Board object without strokes/images", "url": "Url with correct tokens"}


class BoardResource(DocumentedResource):
    """
    GET /api/boards/<board_id> - Get board details (with strokes/images)
    PATCH /api/boards/<board_id> - Update board
    DELETE /api/boards/<board_id> - Delete board
    """
    
    method_decorators = [require_admin_token]
    desc = 'Manage individual whiteboard'
    url = '/boards/<string:board_id>'

    def __init__(self):
        super().__init__()
        self.parser.add_argument('name', type=str, required=False)
        self.parser.add_argument('is_active', type=bool, required=False)

    def get(self, board_id):
        """Get board details with all strokes and images."""
        doc = get_document_or_404(board_id)
        if not doc:
            return {'error': 'Board not found'}, 404
        
        return {
            'board': doc.to_dict(include_strokes=True),
            'url': url_for('board', token=doc.access_token, _external=True),
            'stroke_count': doc.strokes.count(),
            'image_count': doc.images.count()
        }, 200
    get.response = {"board": 
                    "Board object with strokes/images", 
                    "url": "Url with correct tokens", 
                    "stroke_count": "Integer", "image_count": "Integer"}
    
    def patch(self, board_id):
        """Update board (name, active status)."""
        doc = get_document_or_404(board_id)
        if not doc:
            return {'error': 'Board not found'}, 404
        
        args = self.parser.parse_args()
        
        if args.get('name') is not None:
            doc.name = args['name']
        if args.get('is_active') is not None:
            doc.is_active = args['is_active']
        
        doc.save()
        
        return {'board': doc.to_dict(include_strokes=False)}, 200
    patch.response = {"board": "Board object without strokes/images"}

    def delete(self, board_id):
        """Delete a board and all its contents."""
        doc = get_document_or_404(board_id)
        if not doc:
            return {'error': 'Board not found'}, 404
        
        # Delete related strokes and images
        Stroke.delete().where(Stroke.document == doc).execute()
        Image.delete().where(Image.document == doc).execute()
        doc.delete_instance()
        
        return {'deleted': board_id}, 200
    delete.response = {"deleted": "Board ID"}


class BoardTokenResource(DocumentedResource):
    """POST /api/boards/<board_id>/regenerate-token - Regenerate access token."""
    
    method_decorators = [require_admin_token]
    url = '/boards/<string:board_id>/regenerate-token'

    def post(self, board_id):
        """Regenerate access token for a board (invalidates old links)."""
        doc = get_document_or_404(board_id)
        if not doc:
            return {'error': 'Board not found'}, 404
        
        doc.access_token = secrets.token_urlsafe(32)
        doc.save()
        
        return {
            'board': doc.to_dict(include_strokes=False),
            'url': url_for('board', token=doc.access_token, _external=True)
        }, 200
    post.response = {"board": "Board object without strokes/images", "url": "Url with correct tokens"}

# =============================================================================
# Board Render Resource (PNG rasterization)
# =============================================================================

def _to_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class BoardRenderResource(DocumentedResource):
    """
    GET /api/boards/<board_id>/render - Server-rendered PNG of the board.

    Query parameters:
        max_width: Maximum output width in pixels (default 1024, max 4096).
        bg:        'white' (default) or 'transparent'.

    Responds with ``image/png`` and ``ETag`` keyed on the board ``version``
    so callers can do cheap ``If-None-Match`` revalidation.
    """

    method_decorators = [require_admin_token]
    desc = 'Render a board to a PNG'
    url = '/boards/<string:board_id>/render'

    def get(self, board_id):
        doc = get_document_or_404(board_id)
        if not doc:
            return {'error': 'Board not found'}, 404

        max_width = _to_int(request.args.get('max_width'), 1024)
        bg = (request.args.get('bg') or 'white').strip().lower()
        if bg not in ('white', 'transparent'):
            bg = 'white'

        version = int(getattr(doc, 'version', 0) or 0)
        etag = f'W/"board-{doc.id}-v{version}-{max_width}-{bg}"'
        if_none_match = request.headers.get('If-None-Match', '')
        if if_none_match and etag in if_none_match:
            resp = Response(status=304)
            resp.headers['ETag'] = etag
            resp.headers['Cache-Control'] = 'private, max-age=15'
            return resp

        png = get_or_render_png(doc, max_width=max_width, background=bg)
        resp = Response(png, mimetype='image/png')
        resp.headers['ETag'] = etag
        resp.headers['Cache-Control'] = 'private, max-age=15'
        resp.headers['X-Board-Version'] = str(version)
        return resp


# =============================================================================
# Stroke Resources
# =============================================================================

class StrokesResource(DocumentedResource):
    """
    POST /api/boards/<board_id>/strokes - Create new stroke
    DELETE /api/boards/<board_id>/strokes - Clear all strokes
    """
    
    method_decorators = [require_admin_token]
    url = '/boards/<string:board_id>/strokes'

    def __init__(self):
        super().__init__()
        self.parser.add_argument('id', type=str, required=False)
        self.parser.add_argument('points', type=list, location='json', required=True)
        self.parser.add_argument('color', type=str, default='#000000')
        self.parser.add_argument('strokeWidth', type=float, default=4.0)
        self.parser.add_argument('transform', type=dict, location='json', required=False)
    
    def post(self, board_id):
        args = self.parser.parse_args()
        doc = get_document_or_404(board_id)
        if not doc:
            return {'error': 'Board not found'}, 404
        
        stroke = Stroke.create_new(
            document_id=doc.id,
            points=args['points'],
            color=args['color'],
            stroke_width=args['strokeWidth'],
            transform=args.get('transform')
        )
        
        # If client provided an ID, use it
        if args.get('id'):
            stroke.id = args['id']
        
        stroke.save(force_insert=True)
        doc.bump_version()  # invalidate render cache + notify integrators
        
        return stroke.to_dict(), 201
    post.response = {"stroke": "Stroke object"}
   
    def delete(self, board_id):
        """Clear all strokes from board."""
        doc = get_document_or_404(board_id)
        if not doc:
            return {'error': 'Board not found'}, 404
        
        deleted_count = Stroke.delete().where(Stroke.document == doc).execute()
        doc.bump_version()
        
        return {'deleted': deleted_count}, 200
    delete.response = {"deleted": "Integer count"}


class StrokeResource(DocumentedResource):
    """
    GET /api/boards/<board_id>/strokes/<stroke_id> - Get single stroke
    PUT /api/boards/<board_id>/strokes/<stroke_id> - Update stroke
    DELETE /api/boards/<board_id>/strokes/<stroke_id> - Delete stroke
    """
    
    method_decorators = [require_admin_token]
    url = '/boards/<string:board_id>/strokes/<string:stroke_id>'

    def __init__(self):
        super().__init__()
        self.parser.add_argument('transform', type=dict, location='json', required=False)
        self.parser.add_argument('points', type=list, location='json', required=False)
        self.parser.add_argument('color', type=str, required=False)
        self.parser.add_argument('strokeWidth', type=float, required=False)
    
    def get(self, board_id, stroke_id):
        try:
            stroke = Stroke.get((Stroke.id == stroke_id) & (Stroke.document_id == board_id))
            return stroke.to_dict(), 200
        except Stroke.DoesNotExist:
            return {'error': 'Stroke not found'}, 404
    get.response = {"stroke": "Stroke object"}

    def put(self, board_id, stroke_id):
        args = self.parser.parse_args()
        
        try:
            stroke = Stroke.get((Stroke.id == stroke_id) & (Stroke.document_id == board_id))
        except Stroke.DoesNotExist:
            return {'error': 'Stroke not found'}, 404
        
        # Update fields if provided
        if args.get('transform'):
            stroke.set_transform(args['transform'])
        if args.get('points'):
            stroke.set_points(args['points'])
        if args.get('color'):
            stroke.color = args['color']
        if args.get('strokeWidth'):
            stroke.stroke_width = args['strokeWidth']
        
        stroke.save()
        Document.get_by_id(board_id).bump_version()

        return stroke.to_dict(), 200
    put.response = {"stroke": "Stroke object"}
    
    def delete(self, board_id, stroke_id):
        try:
            stroke = Stroke.get((Stroke.id == stroke_id) & (Stroke.document_id == board_id))
            stroke.delete_instance()
            Document.get_by_id(board_id).bump_version()

            return {'deleted': stroke_id}, 200
        except Stroke.DoesNotExist:
            return {'error': 'Stroke not found'}, 404
    delete.response = {
        "200": {"deleted": "Stroke ID"},
        "404": {"error": "Error message if not found"}
    }
# =============================================================================
# Image Resources
# =============================================================================

class ImagesResource(DocumentedResource):
    """
    GET    /api/boards/<board_id>/images - List images (with optional meta filter)
    POST   /api/boards/<board_id>/images - Create new image
    DELETE /api/boards/<board_id>/images - Clear all images (or by meta filter)
    """
    
    method_decorators = [require_admin_token]
    url = '/boards/<string:board_id>/images'

    def __init__(self):
        super().__init__()
        self.parser.add_argument('id', type=str, required=False)
        self.parser.add_argument('data', type=str, required=True)  # Base64 image data
        self.parser.add_argument('x', type=float, default=0)
        self.parser.add_argument('y', type=float, default=0)
        self.parser.add_argument('width', type=float, default=200)
        self.parser.add_argument('height', type=float, default=200)
        self.parser.add_argument('transform', type=dict, location='json', required=False)
        self.parser.add_argument('meta', type=dict, location='json', required=False)
    
    @staticmethod
    def _meta_matches(image_meta, filter_meta):
        """Shallow equality match for meta filter (all filter keys must match)."""
        if not filter_meta:
            return True
        for key, value in filter_meta.items():
            if image_meta.get(key) != value:
                return False
        return True

    def get(self, board_id):
        """List images on the board, optionally filtered by meta key/value(s).

        Filter via repeated ``meta_key=...&meta_val=...`` pairs *or*
        a single ``meta.<key>=<value>`` query arg. We keep this simple
        (string equality only) since the common case is finding all
        integrator-inserted images by ``meta.source=my_app`` (or similar).
        """
        doc = get_document_or_404(board_id)
        if not doc:
            return {'error': 'Board not found'}, 404

        filter_meta = {}
        for key, value in request.args.items():
            if key.startswith('meta.'):
                filter_meta[key[len('meta.'):]] = value

        images = list(Image.select().where(Image.document == doc))
        if filter_meta:
            images = [img for img in images if self._meta_matches(img.get_meta(), filter_meta)]
        return {
            'images': [img.to_dict() for img in images],
            'count': len(images),
        }, 200
    get.response = {"images": "List of image objects", "count": "Integer"}

    def post(self, board_id):
        args = self.parser.parse_args()
        doc = get_document_or_404(board_id)
        if not doc:
            return {'error': 'Board not found'}, 404
        
        image = Image.create_new(
            document_id=doc.id,
            data=args['data'],
            x=args['x'],
            y=args['y'],
            width=args['width'],
            height=args['height'],
            transform=args.get('transform'),
            meta=args.get('meta'),
        )
        
        # If client provided an ID, use it
        if args.get('id'):
            image.id = args['id']
        
        image.save(force_insert=True)
        doc.bump_version()
        
        return image.to_dict(), 201
    post.response = {"image": "Image object"}

    def delete(self, board_id):
        """Clear all images from board, or only those matching a meta filter."""
        doc = get_document_or_404(board_id)
        if not doc:
            return {'error': 'Board not found'}, 404

        filter_meta = {}
        for key, value in request.args.items():
            if key.startswith('meta.'):
                filter_meta[key[len('meta.'):]] = value

        if filter_meta:
            # Filtered delete: iterate so we can match parsed JSON meta.
            ids_to_delete = [
                img.id for img in Image.select().where(Image.document == doc)
                if self._meta_matches(img.get_meta(), filter_meta)
            ]
            if not ids_to_delete:
                return {'deleted': 0}, 200
            deleted_count = Image.delete().where(Image.id.in_(ids_to_delete)).execute()
        else:
            deleted_count = Image.delete().where(Image.document == doc).execute()

        doc.bump_version()
        return {'deleted': deleted_count}, 200
    delete.response = {"deleted": "Integer count"}

class ImageResource(DocumentedResource):
    """
    GET /api/boards/<board_id>/images/<image_id> - Get single image
    PUT /api/boards/<board_id>/images/<image_id> - Update image
    DELETE /api/boards/<board_id>/images/<image_id> - Delete image
    """
    
    method_decorators = [require_admin_token]
    url = '/boards/<string:board_id>/images/<string:image_id>'

    def __init__(self):
        super().__init__()
        self.parser.add_argument('transform', type=dict, location='json', required=False)
        self.parser.add_argument('x', type=float, required=False)
        self.parser.add_argument('y', type=float, required=False)
        self.parser.add_argument('width', type=float, required=False)
        self.parser.add_argument('height', type=float, required=False)
        self.parser.add_argument('meta', type=dict, location='json', required=False)

    def get(self, board_id, image_id):
        try:
            image = Image.get((Image.id == image_id) & (Image.document_id == board_id))
            return image.to_dict(), 200
        except Image.DoesNotExist:
            return {'error': 'Image not found'}, 404
    get.response = {"image": "Image object"}

    def put(self, board_id, image_id):
        args = self.parser.parse_args()
        
        try:
            image = Image.get((Image.id == image_id) & (Image.document_id == board_id))
        except Image.DoesNotExist:
            return {'error': 'Image not found'}, 404
        
        # Update fields if provided
        if args.get('transform'):
            image.set_transform(args['transform'])
        if args.get('x') is not None:
            image.x = args['x']
        if args.get('y') is not None:
            image.y = args['y']
        if args.get('width') is not None:
            image.width = args['width']
        if args.get('height') is not None:
            image.height = args['height']
        if args.get('meta') is not None:
            image.set_meta(args['meta'])
        
        image.save()
        Document.get_by_id(board_id).bump_version()

        return image.to_dict(), 200
    put.response = {"image": "Image object"}

    def delete(self, board_id, image_id):
        try:
            image = Image.get((Image.id == image_id) & (Image.document_id == board_id))
            image.delete_instance()
            Document.get_by_id(board_id).bump_version()

            return {'deleted': image_id}, 200
        except Image.DoesNotExist:
            return {'error': 'Image not found'}, 404


# =============================================================================
# Register all resources
# =============================================================================


# Board resources
api.add_resource(BoardsResource, BoardsResource.url)
api.add_resource(BoardResource, BoardResource.url)
api.add_resource(BoardTokenResource, BoardTokenResource.url)
api.add_resource(BoardRenderResource, BoardRenderResource.url)

# Stroke resources
api.add_resource(StrokesResource, StrokesResource.url)
api.add_resource(StrokeResource, StrokeResource.url)
# Image resources
api.add_resource(ImagesResource, ImagesResource.url)
api.add_resource(ImageResource, ImageResource.url)

