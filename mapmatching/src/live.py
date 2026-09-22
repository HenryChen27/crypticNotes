"""Live presentation policy and raw source rendering (no example/GT access)."""
from dataclasses import dataclass, replace
import cv2
import numpy as np


@dataclass
class ToggleState:
    generation: int = 0
    opened: bool = False

    def close(self):
        self.generation += 1
        self.opened = False

    def open(self):
        self.generation += 1
        self.opened = True
        return self.generation

    def accepts(self, generation):
        return self.opened and generation == self.generation


def presentation_candidate(result):
    """Provisional sanity gates, NOT a calibrated identity/lock decision.

    Scores describe visible boundary coverage, not probabilities. A live
    candidate remains explicitly labelled experimental even when displayed.
    """
    if not result.candidates:
        return None, '没有识别到地图结构，请打开游戏地图后重试'
    c = result.candidates[0]
    if c.pose is None or (c.explained or 0) < .55 or c.contradiction is None or c.contradiction > .40 or c.retrieval_score < 4:
        return None, '没有找到可靠匹配，请增加探索范围后重试'
    if len(result.candidates) > 1 and (c.explained or 0) - (result.candidates[1].explained or 0) < .01:
        return None, '两张地图过于相似，暂不叠图，请增加探索范围'
    if c.floor is None:
        return None, '已找到候选地图，但楼层尚未确认，暂不叠图'
    return c, '试用叠图 · 请核对路口'


def raw_layer(shape, original, reference, candidate, excluded_boxes=(), *, full_view=False):
    """BGRA original colors at full alpha; UI applies user opacity once.

    Only the identified floor is used. No recoloring, inpainting or substitute
    drawing. Masks exclude source thumbnails and the game's HUD viewport.
    """
    if candidate.map_id != reference.map_id or candidate.pose is None:
        raise ValueError('Missing or mismatched pose')
    region = next((r for r in reference.regions if r['floor'] == candidate.floor), None)
    if region is None:
        raise ValueError('楼层区域未验证，无法安全叠图')
    p = candidate.pose
    if not np.isfinite([p.scale, p.tx, p.ty]).all() or p.scale <= 0:
        raise ValueError('Invalid pose')
    alpha = np.zeros(original.shape[:2], np.uint8)
    x0,y0,x1,y1 = region['bbox']
    alpha[y0:y1,x0:x1] = 255
    for x0,y0,x1,y1 in reference.exclusions:
        alpha[y0:y1,x0:x1] = 0
    source = cv2.cvtColor(original, cv2.COLOR_BGR2BGRA)
    source[:,:,3] = alpha
    h,w = shape[:2]
    layer = cv2.warpAffine(source, np.array([[p.scale,0,p.tx],[0,p.scale,p.ty]],float), (w,h))
    # Same normalized viewport used by the evidence extractor.
    mask = np.zeros((h,w),bool)
    mask[int(.18*h):int(.82*h),int(.25*w):int(.91*w)] = True
    if not full_view:
        layer[~mask,3] = 0
    for x0,y0,x1,y1 in excluded_boxes:
        layer[max(0,y0):min(h,y1),max(0,x0):min(w,x1),3] = 0
    return layer


def centered_floor_layer(shape, original, reference, floor, margin=.10):
    """Show a known floor centered when screen geometry is too sparse to align.

    This is deliberately a presentation fallback: identity comes from the
    cached map and the floor comes from the latest recognition result.  It
    never invents a screen-space pose or updates the alignment cache.
    """
    region = next((r for r in reference.regions if r['floor'] == floor), None)
    if region is None:
        return None
    x0, y0, x1, y1 = map(int, region['bbox'])
    crop = original[max(0,y0):min(original.shape[0],y1),
                    max(0,x0):min(original.shape[1],x1)]
    if crop.size == 0:
        return None
    h, w = shape[:2]
    scale = min((w*(1-2*margin))/crop.shape[1], (h*(1-2*margin))/crop.shape[0])
    nw, nh = max(1, int(crop.shape[1]*scale)), max(1, int(crop.shape[0]*scale))
    resized = cv2.resize(crop, (nw, nh), interpolation=cv2.INTER_AREA)
    layer = np.zeros((h,w,4), np.uint8)
    left, top = (w-nw)//2, (h-nh)//2
    layer[top:top+nh, left:left+nw, :3] = cv2.cvtColor(resized, cv2.COLOR_BGR2BGRA)[:,:,:3]
    layer[top:top+nh, left:left+nw, 3] = 255
    return layer


def composite(screenshot, layer, opacity=.30):
    alpha = layer[:,:,3:4].astype(np.float32)/255 * opacity
    return np.rint(screenshot*(1-alpha)+layer[:,:,:3]*alpha).clip(0,255).astype(np.uint8)


def match_with_cache(matcher, pixels, cached=None, *, require_map_ui=False):
    """Try one-map registration first, then reacquire only when it fails.

    The cache is a provisional identity, never an old screen-space transform.
    Require no major degradation from the last displayed geometric fit. This
    remains a heuristic: identical visible topology cannot prove identity.
    """
    import time
    start = time.perf_counter()
    visibility = None
    if require_map_ui:
        from .map_visibility import inspect_map_ui
        from .matcher import MatchResult
        visibility = inspect_map_ui(pixels)
        if not visibility['visible']:
            return (MatchResult(reason='map_ui_not_confirmed',diagnostics=dict(
                map_ui=visibility,identity_search_performed=False,pipeline='screen_gate')),
                None,'未确认地图已展开，已停止叠图')
    fallback = None
    if cached is not None:
        result = matcher.register_known(pixels,cached.map_id)
        if visibility is not None:
            result.diagnostics['map_ui'] = visibility
        candidate,message = presentation_candidate(result)
        if candidate is not None and (candidate.explained or 0) >= max(.55,(cached.explained or 0)-.05) and candidate.contradiction <= min(.40,(cached.contradiction or 0)+.05):
            result.diagnostics.update(pipeline='cached_registration',cached_map_id=cached.map_id,
                                      identity_search_performed=False)
            return result,candidate,'沿用上次地图 · 已重新对齐'
        fallback = 'cached_alignment_rejected'
    result = matcher.match(pixels)
    if visibility is not None:
        result.diagnostics['map_ui'] = visibility
    candidate,message = presentation_candidate(result)
    result.diagnostics.update(pipeline='recognition_fallback' if cached is not None else 'recognition',
                              identity_search_performed=True,cache_fallback_reason=fallback,
                              pipeline_ms=(time.perf_counter()-start)*1000)
    return result,candidate,message


class MultiplayerFallback:
    """Search dedicated duo routes first, loading solo routes only on failure."""

    def __init__(self, primary, solo_factory):
        self.primary = primary
        self.solo_factory = solo_factory
        self.solo = None

    @property
    def references(self):
        return self.primary.references + (self.solo.references if self.solo else [])

    def match(self, pixels):
        result = self.primary.match(pixels)
        if presentation_candidate(result)[0] is not None:
            return result
        if self.solo is None:
            self.solo = self.solo_factory()
        solo_result = self.solo.match(pixels)
        if presentation_candidate(solo_result)[0] is not None:
            solo_result.diagnostics['multiplayer_solo_fallback'] = True
            return solo_result
        # Do not use a rejected solo candidate to infer the cached duo floor.
        return result

    def register_known(self, pixels, map_id):
        if map_id.startswith('nightmare/solo/'):
            if self.solo is None:
                self.solo = self.solo_factory()
            result = self.solo.register_known(pixels, map_id)
            result.diagnostics['multiplayer_solo_fallback'] = True
            return result
        return self.primary.register_known(pixels, map_id)


def worker(connection, root, difficulty, mode):
    """Persistent, event-driven process. Parent can terminate active work."""
    from pathlib import Path
    import time
    from .matcher import MapMatcher
    from .reference import read_image
    cv2.setNumThreads(1)
    cv2.setRNGSeed(0)
    root = Path(root)
    recorder = None
    options = {}
    pixels = None
    try:
        index=root/'maps'
        if not (index/'index.json').exists():
            from .reference import build
            build(index)
        matcher = MapMatcher(index, difficulty=difficulty, mode=mode)
        if difficulty == 'nightmare' and mode == 'duo':
            matcher = MultiplayerFallback(
                matcher, lambda: MapMatcher(index, difficulty='nightmare', mode='solo'))
        connection.send(('ready', None))
        while True:
            request = connection.recv()
            if request is None:
                return
            generation, pixels, *previous = request
            cached = previous[0] if previous else None
            options = previous[1] if len(previous) > 1 else {}
            start = time.perf_counter()
            result,candidate,message = match_with_cache(matcher,pixels,cached,
                require_map_ui=options.get('source') == 'screen')
            layer = None
            if candidate is not None:
                ref = next(r for r in matcher.references if r.map_id == candidate.map_id)
                layer = raw_layer(pixels.shape, read_image(root/ref.source), ref, candidate,
                                  result.diagnostics.get('excluded_panel_boxes',[]),
                                  full_view=result.diagnostics.get('full_view',False))
            # A failed geometric match is not evidence that the map UI is open.
            # Never turn a rejected candidate into a centered overlay: ordinary
            # gameplay can have corners and even a spurious floor assignment.
            # Centered previews require independent map-UI/floor detection,
            # which the current matcher does not provide.
            if layer is not None and mode == 'duo' and candidate.mode == 'solo':
                message = '多人暂无专用路线'
                result.diagnostics['multiplayer_solo_fallback'] = True
            if options.get('record_failures'):
                from .failure_records import FailureRecorder
                from ..paths import DATA_ROOT
                if recorder is None:
                    recorder = FailureRecorder(DATA_ROOT/'failure-records', root)
                result.diagnostics['failure_record'] = recorder.save(
                    pixels, result.to_dict(), dict(difficulty=difficulty, mode=mode,
                    cached_map_id=cached.map_id if cached else None,
                    source=options.get('source'), capture_rect=options.get('capture_rect'),
                    trigger=options.get('trigger','unknown'),
                    map_visibility=result.diagnostics.get('map_ui',{}).get('visible','unknown'), generation=generation),
                    message, success=layer is not None)
            connection.send(('result', (generation, layer, message, candidate,
                                       (time.perf_counter()-start)*1000, result.to_dict())))
    except (EOFError, BrokenPipeError):
        pass
    except Exception as error:
        if options.get('record_failures') and pixels is not None:
            try:
                from .failure_records import FailureRecorder
                from ..paths import DATA_ROOT
                if recorder is None:
                    recorder = FailureRecorder(DATA_ROOT/'failure-records', root)
                recorder.save(pixels, {}, dict(difficulty=difficulty, mode=mode),
                              '匹配程序异常', error=str(error))
            except Exception:
                pass
        connection.send(('error', str(error)))
    finally:
        connection.close()
