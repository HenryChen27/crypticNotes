"""Android transport/cache with mobile-only acceptance and retrieval policy."""
import json
from pathlib import Path
import cv2
import numpy as np
from mobile_matching import MobileMatcher as MapMatcher, selected_floor
from mapmatching.src.live import match_with_cache, raw_layer, MultiplayerFallback
from mobile_images import read_image
from mobile_cancellation import checkpoint, request_scope, Superseded
from mapmatching.src.manual_alignment import reliable_memory, automatic_cross_floor_reliable
from mapmatching.src.live import centered_floor_layer
from dataclasses import replace
from mobile_gate import inspect_map_ui

_matcher = None
_cached = None
_confirmed = None
_pending_candidate = None
_root = None
_names = {}
_originals = {}

def initialize(root, difficulty, mode, provider='lianghapi'):
    global _matcher, _cached, _confirmed, _root, _names, _pending_candidate
    cv2.setNumThreads(1)
    cv2.setRNGSeed(0)
    _root = Path(root)
    _cached = None
    _confirmed = None
    _pending_candidate = None
    _originals.clear()
    if provider=='zhanshi' and difficulty=='nightmare':
        from mapmatching.src.author_matcher import LazyAuthorAtlas
        _matcher=LazyAuthorAtlas(_root/'maps',MapMatcher,difficulty=difficulty,mode=mode,provider=provider)
    else:
        _matcher = MapMatcher(_root/'maps',difficulty=difficulty,mode=mode if difficulty=='nightmare' or provider=='zhanshi' else None,provider=provider)
    if provider=='zhanshi' and difficulty=='nightmare':
        from mapmatching.src.author_matcher import AuthorRouteMatcher,terrain_recognizer
        recognizer=terrain_recognizer(_root/'maps',MapMatcher)
        _matcher=AuthorRouteMatcher(_matcher,recognizer)
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

def read_floor_header(data, width, height):
    """Read native-resolution HUD independently of the reduced matching image."""
    header=decode(data)
    if header is None or width<=0 or height<=0 or width>8192 or height>8192:
        return 0
    left=int(.55*width)
    if header.shape[0]>height or header.shape[1]>width-left:
        return 0
    pixels=np.zeros((height,width,3),np.uint8)
    pixels[:header.shape[0],left:left+header.shape[1]]=header
    return selected_floor(pixels) or 0


def commit_match(token):
    global _cached, _confirmed, _pending_candidate
    if _pending_candidate is not None and _pending_candidate[0] == token:
        _cached = _pending_candidate[1]
        if reliable_memory(_cached,{}):
            _confirmed=_cached
        elif _confirmed is not None and getattr(_cached,'map_id',None) != _confirmed.map_id:
            _confirmed=None
        _pending_candidate = None
        return True
    return False


def match(data, output, gated=False, remember=True, token=None, force_floor=0, viewed_floor=0,
          request_counter=None, request_serial=0):
    try:
        with request_scope(request_counter, request_serial):
            return _match(data, output, gated, remember, token, force_floor, viewed_floor)
    except Superseded:
        return json.dumps(dict(ok=False, cancelled=True, message='正在重新识别…'))


def _match(data, output, gated=False, remember=True, token=None, force_floor=0, viewed_floor=0):
    """Register the open map. `gated=True` when the caller already ran the
    map-panel gate on this exact frame, which saves a second decode and a
    second gate pass (~40-80ms) on the hot re-registration path."""
    global _cached, _confirmed, _pending_candidate
    checkpoint()
    pixels=decode(data)
    checkpoint()
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
    floor = int(viewed_floor) if viewed_floor in (-1,1,2) else selected_floor(pixels)
    if isinstance(_matcher, MultiplayerFallback):
        _matcher.primary.floor_hint = floor
        # Ensure the lazily created solo matcher gets this frame's floor too.
        if _matcher.solo is None:
            _matcher.solo = _matcher.solo_factory()
        _matcher.solo.floor_hint = floor
    else:
        _matcher.floor_hint = floor
    offer=None
    if _confirmed is not None and floor is not None and floor != _confirmed.floor:
        ref=next((r for r in _matcher.references if r.map_id==_confirmed.map_id),None)
        if ref is not None and any(r['floor']==floor for r in ref.regions):
            offer=dict(map_id=_confirmed.map_id,floor=floor)
    centered=False
    if force_floor:
        if offer is None or force_floor != floor:
            return json.dumps(dict(ok=False,message='楼层已变化，请重新识别'))
        primary=_matcher.solo if isinstance(_matcher,MultiplayerFallback) and _confirmed.map_id.startswith('nightmare/solo/') else getattr(_matcher,'primary',_matcher)
        previous=getattr(primary,'manual_scale_bounds',None)
        primary.manual_scale_bounds=(_confirmed.pose.scale*.6,_confirmed.pose.scale*1.65)
        try:
            result=primary.register_manual_floor(map_pixels,_confirmed.map_id,floor)
        finally:
            primary.manual_scale_bounds=previous
        # A blank floor is a presentation request, not a pose inferred from HUD.
        from mapmatching.src.evidence import extract
        evidence=extract(map_pixels)
        empty_floor=len(evidence.corners)<4 or evidence.mask.sum()<80
        candidate=next((c for c in result.candidates if c.pose is not None
            and np.isfinite([c.pose.scale,c.pose.tx,c.pose.ty]).all()
            and c.floor==floor and c.retrieval_score>=1 and (c.explained or 0)>=.25
            and c.contradiction is not None and c.contradiction<=.75
            and .6<=c.pose.scale/_confirmed.pose.scale<=1.65),None)
        if empty_floor:
            candidate=None
        centered=candidate is None
        if centered:
            candidate=replace(_confirmed,floor=floor,pose=None)
        message='手动居中显示，位置未校准' if centered else '直接叠图，请核对位置'
    else:
        result,candidate,message=match_with_cache(_matcher,map_pixels,_cached,require_map_ui=False,floor_hint=floor)
        if offer is not None and (candidate is None or candidate.floor != floor or not automatic_cross_floor_reliable(candidate,_confirmed,result)):
            return json.dumps(dict(ok=False,message='是否需要直接叠图？',manual_offer=offer,details=result.to_dict()),default=str)
    checkpoint()
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
    checkpoint()
    layer=(centered_floor_layer(pixels.shape,_originals[reference.source],reference,floor,scale=_confirmed.pose.scale)
           if centered else raw_layer(pixels.shape,_originals[reference.source],reference,candidate,full_view=True))
    ok,encoded=cv2.imencode('.png',layer,[cv2.IMWRITE_PNG_COMPRESSION,1])
    if not ok:raise ValueError('Overlay encoding failed')
    checkpoint()
    Path(output).write_bytes(encoded.tobytes())
    checkpoint()
    if force_floor:
        _pending_candidate=None
    elif remember:
        _cached=candidate
        if reliable_memory(candidate,{}):
            _confirmed=candidate
    else:
        _pending_candidate=(token,candidate)
    if candidate.mode=='solo' and _matcher.__class__ is MultiplayerFallback:
        message='多人暂无专用路线'
    return json.dumps(dict(ok=True,message=_phone(message),map_id=candidate.map_id,
                           name=_label(candidate.map_id),floor=candidate.floor))
