"""Android adapter: pixel transport and session state; core scoring unchanged."""
import json
from pathlib import Path
import cv2
import numpy as np
from mapmatching.src.matcher import MapMatcher
from mapmatching.src.live import match_with_cache, raw_layer, MultiplayerFallback
from mapmatching.src.reference import read_image
from mobile_gate import inspect_map_ui

_matcher = None
_cached = None
_root = None
_names = {}

def initialize(root, difficulty, mode):
    global _matcher, _cached, _root, _names
    cv2.setNumThreads(1)
    cv2.setRNGSeed(0)
    _root = Path(root)
    _cached = None
    _matcher = MapMatcher(_root/'maps',difficulty=difficulty,mode=mode if difficulty=='nightmare' else None)
    if difficulty=='nightmare' and mode=='duo':
        _matcher = MultiplayerFallback(_matcher,lambda:MapMatcher(_root/'maps',difficulty='nightmare',mode='solo'))
    # Display names for the on-screen status strip; `map_id` alone is not readable.
    manifest=json.loads((_root/'maps/floors.json').read_text(encoding='utf-8'))
    _names={e['map_id']:e.get('name') or e['map_id'].rsplit('/',1)[-1] for e in manifest['references']}
    return len(_matcher.references)

def _label(map_id):
    return _names.get(map_id) or map_id.rsplit('/',1)[-1]

def decode(data):
    return cv2.imdecode(np.frombuffer(bytes(data),np.uint8),cv2.IMREAD_COLOR)

def inspect(data, excluded=None):
    pixels=decode(data)
    return json.dumps(inspect_map_ui(pixels, excluded))

def match(data, output, gated=False):
    """Register the open map. `gated=True` when the caller already ran the
    map-panel gate on this exact frame, which saves a second decode and a
    second gate pass (~40-80ms) on the hot re-registration path."""
    global _cached
    pixels=decode(data)
    if not gated:
        visibility=inspect_map_ui(pixels)
        if not visibility['visible']:
            return json.dumps(dict(ok=False,message='未确认地图展开',details=visibility))
    # Phone HUD and live 3-D scene remain visible to the left of the map.
    # Keep coordinates unchanged, but exclude them from geometric evidence.
    h,w=pixels.shape[:2]
    y,Y=int(.12*h),int(.87*h)
    x,X=int(.41*w),int(.86*w)
    map_pixels=np.zeros_like(pixels)
    map_pixels[y:Y,x:X]=pixels[y:Y,x:X]
    result,candidate,message=match_with_cache(_matcher,map_pixels,_cached,require_map_ui=False)
    if candidate is None:
        return json.dumps(dict(ok=False,message=message,details=result.to_dict()),default=str)
    reference=next(r for r in _matcher.references if r.map_id==candidate.map_id)
    layer=raw_layer(pixels.shape,read_image(_root/reference.source),reference,candidate,full_view=True)
    clip=np.zeros((h,w),bool);clip[y:Y,x:X]=True
    layer[~clip,3]=0
    ok,encoded=cv2.imencode('.png',layer)
    if not ok:raise ValueError('Overlay encoding failed')
    Path(output).write_bytes(encoded.tobytes())
    _cached=candidate
    if candidate.mode=='solo' and _matcher.__class__ is MultiplayerFallback:
        message='多人暂无专用路线'
    return json.dumps(dict(ok=True,message=message,map_id=candidate.map_id,
                           name=_label(candidate.map_id),floor=candidate.floor))
