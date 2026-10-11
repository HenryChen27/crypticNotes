"""Explicit cross-floor fallback; never changes automatic acceptance gates."""
import math


def manual_floor_reading(pixels):
    """Keep normal recognition untouched; dark damage tint needs two agreeing readings."""
    import numpy as np
    from .floor_tabs import inspect_floor_tabs
    original=inspect_floor_tabs(pixels)
    if original['floor'] is not None or original.get('reason') == 'conflicting_tabs':
        return original
    readings=[inspect_floor_tabs(np.clip(pixels.astype(np.float32)*gain,0,255).astype(np.uint8))
              for gain in (1.75,2.0)]
    if readings[0]['floor'] is not None and readings[0]['floor'] == readings[1]['floor']:
        return dict(readings[0],reason='manual_dark_tabs_consensus')
    return original


def reliable_memory(candidate, details):
    if candidate is None or details.get('diagnostics', {}).get('manual_alignment'):
        return False
    return (getattr(candidate,'floor',None) is not None and getattr(candidate,'pose',None) is not None
            and candidate.retrieval_score >= 4
            and (candidate.explained or 0) >= .55
            and candidate.contradiction is not None and candidate.contradiction <= .40)


def automatic_cross_floor_reliable(candidate, confirmed, result):
    """Sparse cached fits cannot silently establish another floor's pose."""
    if not reliable_memory(candidate, result.to_dict()):
        return False
    ratio=candidate.pose.scale/confirmed.pose.scale
    if not .6 <= ratio <= 1.65:
        return False
    rivals=[c for c in result.candidates if c.map_id != candidate.map_id]
    return (candidate.explained-max((c.explained or 0 for c in rivals),default=0)) >= .06


def cross_floor_candidate(matcher, pixels, confirmed, details):
    """Return a fresh geometric pose only for a visible, independently read floor."""
    from .floor_tabs import inspect_floor_tabs
    from .map_visibility import inspect_map_ui
    if confirmed is None or not reliable_memory(confirmed, {}):
        return None, None
    if details.get('reason') == 'map_ui_not_confirmed' or not inspect_map_ui(pixels)['visible']:
        return None, None
    floor = manual_floor_reading(pixels)['floor']
    if floor is None or floor == confirmed.floor:
        return None, None
    matcher.floor_hint = floor
    if hasattr(matcher, 'primary'):
        matcher.primary.floor_hint = floor
    # Constrain the actual search, rather than accepting a tiny high-score fit
    # and only then rejecting it. The setting applies to this one request.
    nodes=[matcher]
    for node in nodes:
        for name in ('primary','solo'):
            child=vars(node).get(name)
            if child is not None and all(child is not n for n in nodes):
                nodes.append(child)
    previous=[getattr(node,'manual_scale_bounds',None) for node in nodes]
    for node in nodes:
        node.manual_scale_bounds=(confirmed.pose.scale*.6,confirmed.pose.scale*1.65)
    try:
        result = matcher.register_manual_floor(pixels, confirmed.map_id, floor)
    finally:
        for node,bounds in zip(nodes,previous):
            node.manual_scale_bounds=bounds
    for candidate in result.candidates:
        pose = candidate.pose
        if (candidate.map_id != confirmed.map_id or candidate.floor != floor or pose is None
                or not all(math.isfinite(x) for x in (pose.scale, pose.tx, pose.ty))
                or pose.scale <= 0 or candidate.retrieval_score < 1
                or not .6 <= pose.scale/confirmed.pose.scale <= 1.65
                or (candidate.explained or 0) < .25
                or candidate.contradiction is None or candidate.contradiction > .75):
            continue
        return candidate, result
    return None, None


def blank_floor_offer(pixels, confirmed, details):
    from .floor_tabs import inspect_floor_tabs
    from .map_visibility import inspect_map_ui
    if confirmed is None or not reliable_memory(confirmed, {}):
        return None
    if not inspect_map_ui(pixels)['visible']:
        return None
    floor=manual_floor_reading(pixels)['floor']
    if floor is None or floor == confirmed.floor:
        return None
    return dict(map_id=confirmed.map_id, floor=floor)
