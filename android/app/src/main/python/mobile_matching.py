"""Conservative phone-only matching policy; desktop thresholds stay unchanged."""
import time
import numpy as np
from mapmatching.src.matcher import MapMatcher, MatchResult
from mapmatching.src.evidence import extract
from mapmatching.src.retrieval import retrieve
from mapmatching.src.registration import register


def selected_floor(pixels):
    from mapmatching.src.floor_tabs import inspect_floor_tabs
    return inspect_floor_tabs(pixels)['floor']


def reject_reason(candidates, known=False, floor_confirmed=False):
    if not candidates:
        return 'insufficient_visible_structure'
    best = candidates[0]
    # Use the same geometric floor as the shared presentation policy. The old
    # phone-only .58/.35 gate rejected valid compressed mobile frames after the
    # shared matcher already had enough evidence. Identity ambiguity remains a
    # separate gate below, so this does not turn sparse exploration into a
    # forced match.
    if (best.pose is None or best.floor is None or (best.explained or 0) < .55
            or best.contradiction is None or best.contradiction > .40
            or best.retrieval_score < 4):
        return 'mobile_fit_not_reliable'
    # A high fit against one repetitive room is not an identity decision.
    rivals = [c for c in candidates[1:]
              if (c.map_id, c.floor) != (best.map_id, best.floor)]
    margin = .02 if known else (.025 if floor_confirmed else .04)
    if rivals and (best.explained or 0)-(rivals[0].explained or 0) < margin:
        return 'mobile_identity_ambiguous'
    return None


class MobileMatcher(MapMatcher):
    floor_hint = None

    def match(self, screenshot):
        return self._mobile_match(screenshot)

    def register_known(self, screenshot, map_id):
        return self._mobile_match(screenshot, map_id)

    def _mobile_match(self, screenshot, map_id=None):
        start = time.perf_counter()
        # The adapter already masks the phone viewport. Desktop's first crop
        # loses its upper/lower edges and can trigger a second complete search.
        evidence = extract(screenshot, full_view=True)
        unique = len(np.unique(evidence.corners, axis=0))
        diagnostics = {**evidence.diagnostics, 'unique_corners': unique,
                       'floor_hint': self.floor_hint, 'mobile_policy': 'conservative_v1'}
        # Only the geometric solver's minimum, NOT an exploration quota.
        # A small distinctive junction can identify a map; a large repetitive
        # corridor can still be ambiguous. Decide by fit and competing maps.
        if len(evidence.corners) < 4:
            return MatchResult(reason='insufficient_visible_structure', diagnostics=diagnostics)
        # Retrieval forms pairs of local anchors. Cap its quadratic work on
        # mobile, sampling across the entire discovered shape, not one corner.
        if len(evidence.corners) > 192:
            indices = np.linspace(0, len(evidence.corners)-1, 192, dtype=int)
            evidence.corners = evidence.corners[indices]
            evidence.descriptors = evidence.descriptors[indices]
            evidence.radii = evidence.radii[indices]
        diagnostics['retrieval_anchors'] = len(evidence.corners)
        all_references = [r for r in self.floor_references
                          if map_id is None or r.map_id == map_id]
        references = [r for r in all_references
                      if self.floor_hint is None or any(
                          region['floor'] == self.floor_hint for region in r.regions)]
        extracted = time.perf_counter()
        retrieved = retrieve(evidence, references)
        ranked = time.perf_counter()
        candidates = sorted([register(evidence, r) for r in retrieved[:10]],
                            key=lambda c: -(c.explained or 0))
        reason = reject_reason(candidates, known=map_id is not None,
                               floor_confirmed=self.floor_hint is not None)
        if reason and self.floor_hint in (-1, 1, 2):
            # Treat the tab as an optimization, not a hard gate. A false tab
            # reading must not make a well-explored map impossible to match.
            retrieved = retrieve(evidence, all_references)
            ranked = time.perf_counter()
            candidates = sorted([register(evidence, r) for r in retrieved[:10]],
                                key=lambda c: -(c.explained or 0))
            retry_reason = reject_reason(candidates, known=map_id is not None,
                                         floor_confirmed=False)
            if retry_reason is None:
                diagnostics['rejected_floor_hint'] = self.floor_hint
                diagnostics['all_floors_retry'] = True
                reason = None
        diagnostics['timing_ms'] = dict(extraction=(extracted-start)*1000,
                                       retrieval=(ranked-extracted)*1000,
                                       registration=(time.perf_counter()-ranked)*1000)
        diagnostics['rejected_candidates'] = [dict(map_id=c.map_id, floor=c.floor,
            explained=c.explained, contradiction=c.contradiction,
            retrieval_score=c.retrieval_score) for c in candidates[:3]] if reason else []
        return MatchResult(candidates=[] if reason else candidates,
                           reason=reason or 'mobile_geometry_accepted', diagnostics=diagnostics)
