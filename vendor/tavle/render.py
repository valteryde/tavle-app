"""Server-side rasterization of a whiteboard document to a PNG.

We render strokes (polylines of pressure-sensitive points) and pasted images
into a single bitmap so external consumers (previews, AI vision, exports)
can treat a board as a simple image.

Design notes:
- Pure-Python via Pillow; no headless browser, no Cairo. The board doesn't
  need pixel-perfect visual parity with the live canvas (which uses
  perfect-freehand); a faithful polyline approximation is good enough for
  thumbnails and vision models.
- Viewport is derived from the bounding box of all geometry, padded so
  edges aren't clipped. Output is downscaled to honour ``max_width`` while
  preserving aspect ratio.
- A solid white background is the default since most AI vision models read
  ink better against white than transparent.
"""

from __future__ import annotations

import base64
import io
import logging
import re
from dataclasses import dataclass
from typing import Iterable

from PIL import Image as PILImage
from PIL import ImageDraw

logger = logging.getLogger(__name__)


# A fully empty board would otherwise produce a 0x0 image; pad to a small
# placeholder so consumers always get a valid PNG.
_MIN_LOGICAL_WIDTH = 200.0
_MIN_LOGICAL_HEIGHT = 200.0
_PADDING_LOGICAL = 40.0
_MAX_OUTPUT_PIXELS = 4096
_DEFAULT_MAX_WIDTH = 1024
_DEFAULT_BG = (255, 255, 255, 255)
_TRANSPARENT_BG = (255, 255, 255, 0)

_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


@dataclass
class _Bounds:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y


def _parse_color(value, default=(0, 0, 0)) -> tuple[int, int, int]:
    """Parse ``#rgb``/``#rrggbb`` into an RGB tuple."""
    if not isinstance(value, str):
        return default
    value = value.strip()
    if not _HEX_RE.match(value):
        return default
    hex_part = value[1:]
    if len(hex_part) == 3:
        hex_part = "".join(c * 2 for c in hex_part)
    try:
        return (
            int(hex_part[0:2], 16),
            int(hex_part[2:4], 16),
            int(hex_part[4:6], 16),
        )
    except ValueError:
        return default


def _decode_data_url(data_url: str) -> PILImage.Image | None:
    """Decode a base64 ``data:image/...`` URL into a PIL image."""
    if not isinstance(data_url, str) or "," not in data_url:
        return None
    try:
        header, b64 = data_url.split(",", 1)
        if "base64" not in header:
            return None
        raw = base64.b64decode(b64, validate=False)
        return PILImage.open(io.BytesIO(raw))
    except Exception as exc:
        logger.debug(f"Skipping undecodable image data: {exc}")
        return None


def _stroke_points(stroke) -> list[tuple[float, float]]:
    """Return effective (x, y) points for a stroke after its transform."""
    raw_points = stroke.get_points()
    transform = stroke.get_transform() or {}
    tx = float(transform.get("x", 0) or 0)
    ty = float(transform.get("y", 0) or 0)
    scale = float(transform.get("scale", 1) or 1) or 1.0
    out: list[tuple[float, float]] = []
    for p in raw_points:
        if not isinstance(p, dict):
            continue
        try:
            x = float(p.get("x", 0)) * scale + tx
            y = float(p.get("y", 0)) * scale + ty
        except (TypeError, ValueError):
            continue
        out.append((x, y))
    return out


def _image_box(img) -> tuple[float, float, float, float] | None:
    """Compute world-space bounding box for an image after its transform."""
    try:
        x = float(img.x or 0)
        y = float(img.y or 0)
        w = float(img.width or 0)
        h = float(img.height or 0)
    except (TypeError, ValueError):
        return None
    transform = img.get_transform() or {}
    try:
        tx = float(transform.get("x", 0) or 0)
        ty = float(transform.get("y", 0) or 0)
        scale = float(transform.get("scale", 1) or 1) or 1.0
    except (TypeError, ValueError):
        tx, ty, scale = 0.0, 0.0, 1.0
    left = x * scale + tx
    top = y * scale + ty
    right = left + w * scale
    bottom = top + h * scale
    return left, top, right, bottom


def _compute_bounds(strokes, images) -> _Bounds:
    has_geometry = False
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")

    for stroke in strokes:
        for x, y in _stroke_points(stroke):
            has_geometry = True
            if x < min_x:
                min_x = x
            if y < min_y:
                min_y = y
            if x > max_x:
                max_x = x
            if y > max_y:
                max_y = y

    for img in images:
        box = _image_box(img)
        if not box:
            continue
        has_geometry = True
        left, top, right, bottom = box
        if left < min_x:
            min_x = left
        if top < min_y:
            min_y = top
        if right > max_x:
            max_x = right
        if bottom > max_y:
            max_y = bottom

    if not has_geometry:
        return _Bounds(0.0, 0.0, _MIN_LOGICAL_WIDTH, _MIN_LOGICAL_HEIGHT)

    # Enforce a minimum logical size so single-dot boards still render
    # at a sensible aspect ratio rather than as a 1x1 strip.
    if max_x - min_x < _MIN_LOGICAL_WIDTH:
        extra = (_MIN_LOGICAL_WIDTH - (max_x - min_x)) / 2
        min_x -= extra
        max_x += extra
    if max_y - min_y < _MIN_LOGICAL_HEIGHT:
        extra = (_MIN_LOGICAL_HEIGHT - (max_y - min_y)) / 2
        min_y -= extra
        max_y += extra

    return _Bounds(
        min_x - _PADDING_LOGICAL,
        min_y - _PADDING_LOGICAL,
        max_x + _PADDING_LOGICAL,
        max_y + _PADDING_LOGICAL,
    )


def _all_layers_in_z_order(strokes, images) -> Iterable[tuple[float, str, object]]:
    """Yield (z, kind, obj) tuples ordered by z then creation order."""
    items: list[tuple[float, int, str, object]] = []
    for idx, s in enumerate(strokes):
        items.append((float(getattr(s, "z_index", 0) or 0), idx, "stroke", s))
    for idx, img in enumerate(images):
        items.append((float(getattr(img, "z_index", 0) or 0), idx + 100000, "image", img))
    items.sort(key=lambda row: (row[0], row[1]))
    return ((z, kind, obj) for z, _, kind, obj in items)


def render_document_png(
    document,
    *,
    max_width: int | None = None,
    background: str = "white",
) -> bytes:
    """Rasterize a Document's strokes + images into a PNG ``bytes`` blob.

    Parameters
    ----------
    document:
        Peewee ``Document`` instance with `strokes` and `images` related sets.
    max_width:
        Maximum output width in pixels. Output is downscaled (preserving
        aspect ratio) but never upscaled. Defaults to a sensible thumbnail
        size; clamped to ``_MAX_OUTPUT_PIXELS``.
    background:
        ``"white"`` (default) or ``"transparent"``.

    Notes
    -----
    Returns a valid PNG even for empty boards (a blank placeholder canvas).
    Logs and skips individual strokes/images that fail to parse rather than
    aborting the whole render.
    """
    max_w = max(64, min(int(max_width or _DEFAULT_MAX_WIDTH), _MAX_OUTPUT_PIXELS))

    strokes = list(document.strokes)
    images = list(document.images)
    bounds = _compute_bounds(strokes, images)

    logical_w = max(bounds.width, 1.0)
    logical_h = max(bounds.height, 1.0)

    # Scale to fit max_width; preserve aspect ratio. Also clamp pixel size.
    scale = min(max_w / logical_w, _MAX_OUTPUT_PIXELS / logical_h)
    if scale <= 0:
        scale = 1.0
    out_w = max(1, int(round(logical_w * scale)))
    out_h = max(1, int(round(logical_h * scale)))

    bg = _TRANSPARENT_BG if str(background).lower() == "transparent" else _DEFAULT_BG
    canvas = PILImage.new("RGBA", (out_w, out_h), bg)
    draw = ImageDraw.Draw(canvas, "RGBA")

    def world_to_pixel(x: float, y: float) -> tuple[float, float]:
        return ((x - bounds.min_x) * scale, (y - bounds.min_y) * scale)

    for z, kind, obj in _all_layers_in_z_order(strokes, images):
        if kind == "stroke":
            _draw_stroke(draw, obj, world_to_pixel, scale)
        elif kind == "image":
            _paste_image(canvas, obj, world_to_pixel, scale)

    buf = io.BytesIO()
    # Use ``PNG`` directly; ``optimize=True`` is slow on large boards, so we
    # accept the slightly larger file in exchange for fast thumbnails.
    canvas.save(buf, format="PNG")
    return buf.getvalue()


def _draw_stroke(draw: ImageDraw.ImageDraw, stroke, world_to_pixel, scale: float) -> None:
    points = _stroke_points(stroke)
    if not points:
        return
    color = _parse_color(getattr(stroke, "color", "#000000"))
    width = max(1, int(round(float(getattr(stroke, "stroke_width", 4) or 4) * scale)))
    pixel_points = [world_to_pixel(x, y) for x, y in points]
    if len(pixel_points) == 1:
        # Draw a filled dot for single-point strokes.
        px, py = pixel_points[0]
        r = max(1, width // 2)
        draw.ellipse([px - r, py - r, px + r, py + r], fill=color + (255,))
        return
    draw.line(pixel_points, fill=color + (255,), width=width, joint="curve")


def _paste_image(canvas: PILImage.Image, img, world_to_pixel, scale: float) -> None:
    pil = _decode_data_url(getattr(img, "data", ""))
    if pil is None:
        return
    box = _image_box(img)
    if not box:
        return
    left, top, right, bottom = box
    px_left, px_top = world_to_pixel(left, top)
    px_right, px_bottom = world_to_pixel(right, bottom)
    target_w = max(1, int(round(px_right - px_left)))
    target_h = max(1, int(round(px_bottom - px_top)))
    try:
        resized = pil.convert("RGBA").resize((target_w, target_h), PILImage.LANCZOS)
    except Exception as exc:
        logger.debug(f"Skipping image {getattr(img, 'id', '?')}: resize failed: {exc}")
        return
    try:
        canvas.alpha_composite(resized, (int(round(px_left)), int(round(px_top))))
    except Exception as exc:
        logger.debug(f"Skipping image {getattr(img, 'id', '?')}: composite failed: {exc}")


def get_or_render_png(document, *, max_width: int | None = None, background: str = "white") -> bytes:
    """Return a cached PNG render if fresh, otherwise render and cache.

    The cache key is the document `version`; cache is invalidated by
    :meth:`Document.bump_version` on any stroke/image write. We only cache
    the default-sized white-background render; other sizes/backgrounds are
    re-rendered each call (they're rare and don't justify per-variant
    cache columns).
    """
    is_default_variant = (max_width in (None, _DEFAULT_MAX_WIDTH)) and (
        str(background).lower() == "white"
    )
    if is_default_variant:
        try:
            current_version = int(document.version or 0)
            cached_version = int(document.render_cache_version) if document.render_cache_version is not None else None
        except (TypeError, ValueError):
            current_version, cached_version = 0, None
        if document.render_cache and cached_version == current_version:
            try:
                return base64.b64decode(document.render_cache)
            except Exception:
                document.render_cache = None
                document.render_cache_version = None

    png = render_document_png(document, max_width=max_width, background=background)

    if is_default_variant:
        try:
            document.render_cache = base64.b64encode(png).decode("ascii")
            document.render_cache_version = int(document.version or 0)
            document.save()
        except Exception as exc:
            logger.warning(f"Failed to persist render cache: {exc}")

    return png
