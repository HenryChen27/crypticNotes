"""Shared storage policy for imported atlases; geometry follows resized pixels."""
from copy import deepcopy
import cv2
import numpy as np

MAX_SIDE = 2048
WEBP_QUALITY = 90
SMALL_IMAGE_BYTES = 256 * 1024
POLICY = 'webp-2048-q90-v1'


def compact(image, data, suffix, *, max_side=MAX_SIDE, quality=WEBP_QUALITY):
    """Return encoded bytes, suffix, decoded pixels, and actual x/y resize ratios.

    Never enlarge, stretch, or overwrite the caller's original. Small images are
    retained verbatim. Decode the result so feature extraction sees stored pixels.
    """
    h, w = image.shape[:2]
    ratio = min(1., max_side / max(h, w))
    if ratio == 1. and len(data) <= SMALL_IMAGE_BYTES:
        return data, suffix.lower(), image, (1., 1.)
    width, height = max(3, round(w*ratio)), max(3, round(h*ratio))
    resized = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA) if ratio < 1. else image
    ok, encoded = cv2.imencode('.webp', resized, [cv2.IMWRITE_WEBP_QUALITY, quality])
    if not ok:
        raise ValueError('地图压缩失败，请重试')
    encoded = encoded.tobytes()
    if ratio == 1. and len(encoded) >= len(data):
        return data, suffix.lower(), image, (1., 1.)
    decoded = cv2.imdecode(np.frombuffer(encoded, np.uint8), cv2.IMREAD_COLOR)
    if decoded is None or decoded.shape != resized.shape:
        raise ValueError('压缩地图校验失败，请重试')
    return encoded, '.webp', decoded, (width/w, height/h)


def scale_entry_geometry(entry, ratios, size):
    """Scale all floor boxes, polygons and exclusion masks, without mutating input."""
    result = deepcopy(entry)
    sx, sy = ratios
    w, h = size
    def point(p):
        return [min(w, max(0, round(p[0]*sx))), min(h, max(0, round(p[1]*sy)))]
    def box(b):
        return point(b[:2]) + point(b[2:])
    for region in result.get('regions', []):
        region['bbox'] = box(region['bbox'])
        if region.get('polygons'):
            region['polygons'] = [[point(p) for p in poly] for poly in region['polygons']]
    for field in ('include_regions', 'exclude_regions'):
        if field in result:
            result[field] = [box(b) for b in result[field]]
    result['size'] = [w, h]
    return result
