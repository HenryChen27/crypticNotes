"""Live presentation policy and raw source rendering (no example/GT access)."""
from dataclasses import dataclass
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


def raw_layer(shape, original, reference, candidate, excluded_boxes=()):
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
    layer[~mask,3] = 0
    for x0,y0,x1,y1 in excluded_boxes:
        layer[max(0,y0):min(h,y1),max(0,x0):min(w,x1),3] = 0
    return layer


def composite(screenshot, layer, opacity=.30):
    alpha = layer[:,:,3:4].astype(np.float32)/255 * opacity
    return np.rint(screenshot*(1-alpha)+layer[:,:,:3]*alpha).clip(0,255).astype(np.uint8)


def match_with_cache(matcher, pixels, cached=None):
    """Try one-map registration first, then reacquire only when it fails.

    The cache is a provisional identity, never an old screen-space transform.
    Require no major degradation from the last displayed geometric fit. This
    remains a heuristic: identical visible topology cannot prove identity.
    """
    import time
    start = time.perf_counter()
    fallback = None
    if cached is not None:
        result = matcher.register_known(pixels,cached.map_id)
        candidate,message = presentation_candidate(result)
        if candidate is not None and (candidate.explained or 0) >= max(.55,(cached.explained or 0)-.05) and candidate.contradiction <= min(.40,(cached.contradiction or 0)+.05):
            result.diagnostics.update(pipeline='cached_registration',cached_map_id=cached.map_id,
                                      identity_search_performed=False)
            return result,candidate,'沿用上次地图 · 已重新对齐'
        fallback = 'cached_alignment_rejected'
    result = matcher.match(pixels)
    candidate,message = presentation_candidate(result)
    result.diagnostics.update(pipeline='recognition_fallback' if cached is not None else 'recognition',
                              identity_search_performed=True,cache_fallback_reason=fallback,
                              pipeline_ms=(time.perf_counter()-start)*1000)
    return result,candidate,message


def worker(connection, root, difficulty, mode):
    """Persistent, event-driven process. Parent can terminate active work."""
    from pathlib import Path
    import time
    from .matcher import MapMatcher
    from .reference import read_image
    cv2.setNumThreads(1)
    cv2.setRNGSeed(0)
    root = Path(root)
    try:
        index=root/'maps'
        if not (index/'index.json').exists():
            from .reference import build
            build(index)
        matcher = MapMatcher(index, difficulty=difficulty, mode=mode)
        connection.send(('ready', None))
        while True:
            request = connection.recv()
            if request is None:
                return
            generation, pixels, *previous = request
            cached = previous[0] if previous else None
            start = time.perf_counter()
            result,candidate,message = match_with_cache(matcher,pixels,cached)
            layer = None
            if candidate is not None:
                ref = next(r for r in matcher.references if r.map_id == candidate.map_id)
                layer = raw_layer(pixels.shape, read_image(root/ref.source), ref, candidate,
                                  result.diagnostics.get('excluded_panel_boxes',[]))
            connection.send(('result', (generation, layer, message, candidate,
                                       (time.perf_counter()-start)*1000, result.to_dict())))
    except (EOFError, BrokenPipeError):
        pass
    except Exception as error:
        connection.send(('error', str(error)))
    finally:
        connection.close()
