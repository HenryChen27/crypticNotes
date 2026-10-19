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


def cached_alignment_candidate(result):
    """Pose gate for an identity that was already accepted this session.

    A sparse viewport may contain only corridors and therefore has a lower
    retrieval score than initial recognition.  It can update the pose of the
    remembered map, but can never establish or switch map identity.
    """
    if not result.candidates:
        return None, '当前区域线索不足，已保留上次地图'
    c=result.candidates[0]
    if (c.pose is None or c.floor is None or (c.explained or 0) < .50
            or c.contradiction is None or c.contradiction > .45
            or c.retrieval_score < 2):
        return None, '当前区域线索不足，已保留上次地图'
    return c, '沿用上次地图 · 已重新对齐'


def raw_layer(shape, original, reference, candidate, excluded_boxes=(), *, full_view=False):
    """BGRA original colors at full alpha; UI applies user opacity once.

    Only the identified floor is used. No recoloring, inpainting or substitute
    drawing. Only atlas floor boundaries and source exclusions are masked.
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
    # Evidence extraction excludes HUD clutter, but those exclusions must not
    # clip the displayed floor. The screen edge is the only output boundary.
    return layer


def centered_floor_layer(shape, original, reference, floor, margin=.10, scale=None):
    """Show a known floor centered when screen geometry is too sparse to align.

    This is deliberately a presentation fallback: identity comes from the
    cached map and the floor comes from the latest recognition result.  It
    never invents a screen-space pose or updates the alignment cache.
    """
    region = next((r for r in reference.regions if r['floor'] == floor), None)
    if region is None:
        return None
    x0, y0, x1, y1 = map(int, region['bbox'])
    # Atlas floor boxes can include wide blank margins and HUD labels. Center
    # the actual floor geometry, rather than that editing/annotation rectangle.
    evidence = getattr(reference, 'evidence', None)
    if evidence is not None:
        factor = evidence.image_factor
        mask = evidence.mask.copy()
        yy, xx = np.indices(mask.shape)
        mask *= ((xx >= x0*factor) & (xx < x1*factor)
                 & (yy >= y0*factor) & (yy < y1*factor))
        ys, xs = np.nonzero(mask)
        if len(xs):
            x0, y0, x1, y1 = xs.min()/factor, ys.min()/factor, (xs.max()+1)/factor, (ys.max()+1)/factor
    if scale is not None:
        h,w=shape[:2]
        from .types import Candidate, Pose
        candidate=Candidate(reference.map_id,reference.difficulty,reference.mode,0,
            Pose(scale,w/2-scale*(x0+x1)/2,h/2-scale*(y0+y1)/2),floor=floor)
        return raw_layer(shape,original,reference,candidate,full_view=True)
    x0,y0,x1,y1=map(round,(x0,y0,x1,y1))
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


def match_with_cache(matcher, pixels, cached=None, *, require_map_ui=False, floor_hint=None):
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
    from .matcher import MapMatcher
    from .floor_tabs import inspect_floor_tabs
    floor_reading = inspect_floor_tabs(pixels) if floor_hint is None else dict(floor=floor_hint, reason='caller_floor_tabs')
    if hasattr(matcher, 'floor_hint'):
        matcher.floor_hint = floor_reading['floor']
        if isinstance(matcher, MultiplayerFallback):
            matcher.primary.floor_hint = matcher.floor_hint
            if matcher.solo is not None:
                matcher.solo.floor_hint = matcher.floor_hint
    fallback = None
    if cached is not None:
        result = matcher.register_known(pixels,cached.map_id)
        result.diagnostics['floor_tabs'] = floor_reading
        if visibility is not None:
            result.diagnostics['map_ui'] = visibility
        candidate,message = cached_alignment_candidate(result)
        # A different floor/viewport has different visible evidence. A strong
        # current fit need not match the previous frame's near-perfect score.
        strong_current = candidate is not None and candidate.explained >= .75 and candidate.contradiction <= .20
        comparable_fit = candidate is not None and (candidate.explained or 0) >= max(.55,(cached.explained or 0)-.05) and candidate.contradiction <= min(.40,(cached.contradiction or 0)+.05)
        if strong_current or comparable_fit:
            result.diagnostics.update(pipeline='cached_registration',cached_map_id=cached.map_id,
                                      identity_search_performed=False)
            return result,candidate,'沿用上次地图 · 已重新对齐'
        fallback = 'cached_alignment_rejected'
    result = matcher.match(pixels)
    result.diagnostics['floor_tabs'] = floor_reading
    if visibility is not None:
        result.diagnostics['map_ui'] = visibility
    candidate,message = presentation_candidate(result)
    if cached is not None and candidate is not None and candidate.map_id != cached.map_id:
        rivals = [c for c in result.candidates if c.map_id != candidate.map_id]
        margin = candidate.explained - max((c.explained or 0 for c in rivals), default=0)
        if candidate.explained < .75 or candidate.contradiction > .20 or margin < .06:
            result.diagnostics['map_switch_rejected'] = candidate.map_id
            candidate = None
            message = '暂时无法对齐，已记住上次地图；请增加可见线索'
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
        self.floor_hint = None

    @property
    def references(self):
        return self.primary.references + (self.solo.references if self.solo else [])

    def match(self, pixels):
        result = self.primary.match(pixels)
        if presentation_candidate(result)[0] is not None:
            return result
        if self.solo is None:
            self.solo = (self.primary.alternate if isinstance(self.primary, SharedTerrainMatcher)
                         and self.primary.alternate is not None else self.solo_factory())
        self.solo.floor_hint = self.floor_hint
        # Shared terrain support has already searched this exact frame in the
        # solo atlas. Reuse only this request's result, never a previous frame.
        support = self.primary.last_support if isinstance(self.primary, SharedTerrainMatcher) else None
        solo_result = support if support is not None else self.solo.match(pixels)
        if presentation_candidate(solo_result)[0] is not None:
            solo_result.diagnostics['multiplayer_solo_fallback'] = True
            return solo_result
        # Do not use a rejected solo candidate to infer the cached duo floor.
        return result

    def register_manual_floor(self, pixels, map_id, floor):
        if map_id.startswith('nightmare/solo/'):
            if self.solo is None:
                self.solo=self.solo_factory()
            return self.solo.register_manual_floor(pixels,map_id,floor)
        return self.primary.register_manual_floor(pixels,map_id,floor)

    def register_known(self, pixels, map_id):
        if map_id.startswith('nightmare/solo/'):
            if self.solo is None:
                self.solo = self.solo_factory()
            self.solo.floor_hint = self.floor_hint
            result = self.solo.register_known(pixels, map_id)
            result.diagnostics['multiplayer_solo_fallback'] = True
            return result
        return self.primary.register_known(pixels, map_id)


class SharedTerrainMatcher:
    """Use an explicitly paired route atlas as independent identity evidence.

    Poses always come from the selected route's own image, never from the
    supporting atlas (which can have completely different pixel coordinates).
    """
    def __init__(self, primary, alternate_factory):
        self.primary = primary
        self.alternate_factory = alternate_factory
        self.alternate = None
        self.last_support = None
        self.floor_hint = None

    @property
    def references(self):
        return self.primary.references

    def register_manual_floor(self, pixels, map_id, floor):
        return self.primary.register_manual_floor(pixels,map_id,floor)

    def register_known(self, pixels, map_id):
        self.primary.floor_hint = self.floor_hint
        return self.primary.register_known(pixels, map_id)

    def match(self, pixels):
        self.last_support = None
        self.primary.floor_hint = self.floor_hint
        initial = self.primary._match_view(pixels)
        if presentation_candidate(initial)[0] is not None:
            return initial
        if not any(r.terrain_id for r in self.primary.references):
            return self.primary.match(pixels)
        if self.alternate is None:
            self.alternate = self.alternate_factory()
        self.alternate.floor_hint = self.floor_hint
        support = self.alternate.match(pixels)
        self.last_support = support
        accepted = presentation_candidate(support)[0]
        if accepted is not None:
            ref = next(r for r in self.alternate.references if r.map_id == accepted.map_id)
            paired = [r for r in self.primary.references
                      if ref.terrain_id and r.terrain_id == ref.terrain_id]
            if len(paired) == 1:
                aligned = self.primary.register_known(pixels, paired[0].map_id)
                route = cached_alignment_candidate(aligned)[0]
                if (route is not None and route.floor == accepted.floor
                        and route.explained >= .65 and route.contradiction <= .25
                        and route.retrieval_score >= 4):
                    aligned.candidates = [route]
                    aligned.diagnostics['terrain_support'] = dict(
                        map_id=accepted.map_id, terrain_id=ref.terrain_id,
                        selected_route=route.map_id, candidates=support.to_dict()['candidates'])
                    return aligned
        return self.primary.match(pixels)


def worker(connection, root, difficulty, mode):
    """Persistent, event-driven process. Parent can terminate active work."""
    from pathlib import Path
    import time
    from .matcher import MapMatcher
    from .reference import read_image
    from .ui_trace import enable_crash_logging
    enable_crash_logging('matcher')
    cv2.setNumThreads(1)
    cv2.setRNGSeed(0)
    from functools import lru_cache
    read_source=lru_cache(maxsize=1)(read_image)
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
        if difficulty == 'nightmare':
            other_mode = 'duo' if mode == 'solo' else 'solo'
            matcher = SharedTerrainMatcher(matcher,
                lambda: MapMatcher(index, difficulty='nightmare', mode=other_mode))
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
            if options.get('force_floor') is not None and options.get('confirmed_candidate') is not None:
                from .matcher import MatchResult
                result=MatchResult(reason='manual_alignment_pending')
                candidate=None
                message='画面或楼层已变化，请重新识别后确认'
            else:
                result,candidate,message = match_with_cache(matcher,pixels,cached,
                    require_map_ui=options.get('source') == 'screen')
            centered_offer = None
            confirmed=options.get('confirmed_candidate')
            if confirmed is not None and options.get('force_floor') is None:
                from .manual_alignment import blank_floor_offer, automatic_cross_floor_reliable
                cross_offer=blank_floor_offer(pixels,confirmed,result.to_dict())
                if cross_offer is not None and (candidate is None or
                        not automatic_cross_floor_reliable(candidate,confirmed,result)):
                    result.diagnostics['cross_floor_auto_rejected']=True
                    candidate=None
                    message='当前楼层线索不足，请确认是否直接叠图'
            if (candidate is None or options.get('force_floor') is not None) and options.get('confirmed_candidate') is not None:
                from .manual_alignment import cross_floor_candidate, blank_floor_offer
                offer = blank_floor_offer(pixels,options['confirmed_candidate'],result.to_dict())
                if options.get('force_floor') is not None:
                    candidate=None
                if offer is not None:
                    ref=next((r for r in matcher.references if r.map_id == offer['map_id']),None)
                    if ref is None:
                        # A fresh duo worker may not have loaded the remembered solo atlas yet.
                        matcher.register_known(pixels,offer['map_id'])
                        ref=next((r for r in matcher.references if r.map_id == offer['map_id']),None)
                    if ref is None or not any(r['floor'] == offer['floor'] for r in ref.regions):
                        offer=None
                if offer is not None:
                    wanted = options.get('force_floor')
                    if wanted == offer['floor']:
                        forced, registration = cross_floor_candidate(
                            matcher, pixels, options['confirmed_candidate'], result.to_dict())
                        if forced is not None:
                            result, candidate = registration, forced
                        else:
                            centered_offer=offer
                            candidate=replace(options['confirmed_candidate'],floor=offer['floor'],pose=None)
                        result.diagnostics['manual_alignment'] = True
                        result.diagnostics['map_ui'] = dict(visible=True, reason='manual_verified_floor_panel')
                        message = ('手动居中显示 · 空白楼层位置未校准' if centered_offer else
                                   '手动沿用已确认地图 · 请核对对齐位置')
                    else:
                        result.diagnostics['manual_offer'] = offer
            layer = None
            if centered_offer is not None:
                ref=next((r for r in matcher.references if r.map_id == candidate.map_id),None)
                if ref is not None:
                    layer=centered_floor_layer(pixels.shape,read_source(root/ref.source),ref,candidate.floor,
                                               scale=options['confirmed_candidate'].pose.scale)
                result.diagnostics['manual_centered'] = True
            elif candidate is not None:
                ref = next(r for r in matcher.references if r.map_id == candidate.map_id)
                layer = raw_layer(pixels.shape, read_source(root/ref.source), ref, candidate,
                                  result.diagnostics.get('excluded_panel_boxes',[]),
                                  full_view=result.diagnostics.get('full_view',False))
            # Centering is allowed ONLY after this request's explicit consent,
            # reliable other-floor history and independent UI/floor validation.
            # It never establishes identity or becomes an automatic cached pose.
            if layer is not None and mode == 'duo' and candidate.mode == 'solo':
                message = '多人暂无专用路线'
                result.diagnostics['multiplayer_solo_fallback'] = True
            if options.get('record_failures'):
                from .failure_records import FailureRecorder
                from ..paths import DATA_ROOT
                directory = Path(options.get('records_directory') or DATA_ROOT/'failure-records')
                if recorder is None or recorder.directory != directory:
                    recorder = FailureRecorder(directory, root)
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
                directory = Path(options.get('records_directory') or DATA_ROOT/'failure-records')
                if recorder is None or recorder.directory != directory:
                    recorder = FailureRecorder(directory, root)
                recorder.save(pixels, {}, dict(difficulty=difficulty, mode=mode),
                              '匹配程序异常', error=str(error))
            except Exception:
                pass
        connection.send(('error', str(error)))
    finally:
        connection.close()
