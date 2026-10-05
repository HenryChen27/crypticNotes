"""Android transport/cache with mobile-only acceptance and retrieval policy."""
import json
from pathlib import Path
import cv2
import numpy as np
from mobile_matching import MobileMatcher as MapMatcher, selected_floor
from mapmatching.src.live import match_with_cache, raw_layer, MultiplayerFallback
from mapmatching.src.reference import read_image
from mobile_gate import inspect_map_ui

_matcher = None
_cached = None
_pending_candidate = None
_root = None
_names = {}
_originals = {}

def initialize(root, difficulty, mode):
    global _matcher, _cached, _root, _names, _pending_candidate
    cv2.setNumThreads(1)
    cv2.setRNGSeed(0)
    _root = Path(root)
    _cached = None
    _pending_candidate = None
    _originals.clear()
    _matcher = MapMatcher(_root/'maps',difficulty=difficulty,mode=mode if difficulty=='nightmare' else None)
    if difficulty=='nightmare' and mode=='duo':
        _matcher = MultiplayerFallback(_matcher,lambda:MapMatcher(_root/'maps',difficulty='nightmare',mode='solo'))
    # Display names for the on-screen status strip; `map_id` alone is not readable.
    manifest=json.loads((_root/'maps/floors.json').read_text(encoding='utf-8'))
    _names={e['map_id']:e.get('name') or e['map_id'].rsplit('/',1)[-1] for e in manifest['references']}
    return len(_matcher.references)

def _label(map_id):
    return _names.get(map_id) or map_id.rsplit('/',1)[-1]

# The core writes for a desktop window and a log; the phone has one narrow strip
# that has to be read at a glance mid-match. Same meaning, fewer characters --
# the verdicts themselves are untouched, only their wording on this device.
PHONE_TEXT = {
    '没有识别到地图结构，请打开游戏地图后重试': '没看到地图，请打开地图',
    '没有找到可靠匹配，请增加探索范围后重试': '没匹配上，多走几步再试',
    '两张地图过于相似，暂不叠图，请增加探索范围': '两张图太像，多走几步再试',
    '已找到候选地图，但楼层尚未确认，暂不叠图': '楼层未确认，暂不叠图',
    '试用叠图 · 请核对路口': '请核对路口',
    '多人暂无专用路线': '多人暂无路线',
}

def _phone(message):
    return PHONE_TEXT.get(message, message)

def decode(data):
    return cv2.imdecode(np.frombuffer(bytes(data),np.uint8),cv2.IMREAD_COLOR)

def inspect(data, excluded=None):
    pixels=decode(data)
    return json.dumps(inspect_map_ui(pixels, excluded))

def commit_match(token):
    global _cached, _pending_candidate
    if _pending_candidate is not None and _pending_candidate[0] == token:
        _cached = _pending_candidate[1]
        _pending_candidate = None


def match(data, output, gated=False, remember=True, token=None):
    """Register the open map. `gated=True` when the caller already ran the
    map-panel gate on this exact frame, which saves a second decode and a
    second gate pass (~40-80ms) on the hot re-registration path."""
    global _cached, _pending_candidate
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
    floor = selected_floor(pixels)
    if isinstance(_matcher, MultiplayerFallback):
        _matcher.primary.floor_hint = floor
        # Ensure the lazily created solo matcher gets this frame's floor too.
        if _matcher.solo is None:
            _matcher.solo = _matcher.solo_factory()
        _matcher.solo.floor_hint = floor
    else:
        _matcher.floor_hint = floor
    result,candidate,message=match_with_cache(_matcher,map_pixels,_cached,require_map_ui=False,floor_hint=floor)
    if candidate is None:
        failure_text = {
            'insufficient_visible_structure': '可见地图结构太少，请继续探索',
            'mobile_fit_not_reliable': '地图对齐证据不足，请稍微缩放后重试',
            'mobile_identity_ambiguous': '候选地图过于相似，请继续探索',
        }.get(result.reason, _phone(message))
        return json.dumps(dict(ok=False,message=failure_text,details=result.to_dict()),default=str)
    reference=next(r for r in _matcher.references if r.map_id==candidate.map_id)
    if reference.source not in _originals:
        _originals.clear()  # Bound decoded-image memory to the currently used map.
        _originals[reference.source] = read_image(_root/reference.source)
    layer=raw_layer(pixels.shape,_originals[reference.source],reference,candidate,full_view=True)
    clip=np.zeros((h,w),bool);clip[y:Y,x:X]=True
    layer[~clip,3]=0
    ok,encoded=cv2.imencode('.png',layer,[cv2.IMWRITE_PNG_COMPRESSION,1])
    if not ok:raise ValueError('Overlay encoding failed')
    Path(output).write_bytes(encoded.tobytes())
    if remember:
        _cached=candidate
    else:
        _pending_candidate=(token,candidate)
    if candidate.mode=='solo' and _matcher.__class__ is MultiplayerFallback:
        message='多人暂无专用路线'
    return json.dumps(dict(ok=True,message=_phone(message),map_id=candidate.map_id,
                           name=_label(candidate.map_id),floor=candidate.floor))
