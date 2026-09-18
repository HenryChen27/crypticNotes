"""Pixel-only research API. Candidate scores are not identity probabilities."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from pathlib import Path
import time
import numpy as np
import cv2
from dataclasses import replace
from .evidence import extract
from .reference import load
from .retrieval import retrieve
from .registration import register
from .types import Candidate
from .context import SessionContext


@dataclass
class MatchResult:
    status: str = 'UNKNOWN'
    map_id: str | None = None
    floor: int | None = None
    scale: float | None = None
    tx: float | None = None
    ty: float | None = None
    confidence: float | None = None
    scale_uncertainty: float | None = None
    reason: str = 'uncalibrated_research_baseline'
    candidates: list[Candidate] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class MapMatcher:
    def __init__(self, index: Path, *, difficulty: str, mode: str | None = None):
        self.context = SessionContext(difficulty, mode)
        self.references = load(index, difficulty=difficulty, mode=mode)
        if not self.references:
            raise ValueError('No references satisfy the supplied hints')
        self.floor_references = []
        for ref in self.references:
            for region in ref.regions:
                ev = ref.evidence
                x,y,X,Y = np.array(region['bbox']) * ev.image_factor
                inside = ((ev.corners[:,0]>=x)&(ev.corners[:,0]<X)&
                          (ev.corners[:,1]>=y)&(ev.corners[:,1]<Y))
                yy,xx = np.indices(ev.boundary.shape)
                keep = (xx>=x)&(xx<X)&(yy>=y)&(yy<Y)
                boundary = (ev.boundary*keep).astype(np.uint8)
                if not boundary.any() or inside.sum()<2:
                    continue
                evidence = replace(ev,mask=(ev.mask*keep).astype(np.uint8),boundary=boundary,
                                   corners=ev.corners[inside],descriptors=ev.descriptors[inside],
                                   radii=ev.radii[inside])
                distance = cv2.distanceTransform(1-boundary,cv2.DIST_L2,5)
                self.floor_references.append(replace(ref,evidence=evidence,distance=distance,regions=[region]))

    def match(self, screenshot: np.ndarray) -> MatchResult:
        from .live import presentation_candidate
        initial = self._match_view(screenshot)
        if presentation_candidate(initial)[0] is not None:
            return initial
        expanded = self._match_view(screenshot,full_view=True)
        recovered = presentation_candidate(expanded)[0]
        # Expanded frames include more HUD/desktop clutter: require stronger
        # evidence, rather than loosening the normal acceptance threshold.
        if recovered is not None and recovered.explained >= .65 and recovered.contradiction <= .25:
            expanded.diagnostics['pipeline_view'] = 'expanded_view_retry'
            return expanded
        initial.diagnostics['expanded_view_rejected'] = True
        return initial

    def _match_view(self, screenshot: np.ndarray, full_view=False) -> MatchResult:
        """Accept BGR pixels only; never paths, example IDs, paired maps or GT."""
        start = time.perf_counter()
        evidence = extract(screenshot,full_view=full_view)
        extracted = time.perf_counter()
        if len(evidence.corners) < 4:
            return MatchResult(reason='insufficient_visible_structure', diagnostics=evidence.diagnostics)
        retrieved = retrieve(evidence, self.floor_references)
        ranked = time.perf_counter()
        candidates = sorted([register(evidence, r) for r in retrieved[:10]], key=lambda c: -(c.explained or 0))
        end = time.perf_counter()
        return MatchResult(candidates=candidates, diagnostics={**evidence.diagnostics,
                           'session_context': asdict(self.context),
                           'reference_count': len(self.references), 'full_view': full_view,
                           'retrieval_top5': [{'map_id': r.reference.map_id, 'score': r.score} for r in retrieved[:5]],
                           'timing_ms': {'extraction': (extracted-start)*1000,
                                         'retrieval': (ranked-extracted)*1000,
                                         'registration': (end-ranked)*1000,
                                         'total': (end-start)*1000},
                           'coordinate_system': 'original reference -> original full screenshot',
                           'rotation': 0,
                           'confidence_calibrated': False})

    def register_known(self, screenshot: np.ndarray, map_id: str) -> MatchResult:
        """Re-estimate scale, translation and floor against ONE remembered map.

        Sparse correspondences here are used only to locate that map, not to
        search identities in the library. Every call uses the current pixels.
        """
        start = time.perf_counter()
        refs = [r for r in self.floor_references if r.map_id == map_id]
        if not refs:
            return MatchResult(reason='cached_map_outside_context')
        evidence = extract(screenshot)
        candidates = []
        if len(evidence.corners) >= 4:
            candidates = sorted([register(evidence,r) for r in retrieve(evidence,refs)],
                                key=lambda c: -(c.explained or 0))
        return MatchResult(candidates=candidates, diagnostics={**evidence.diagnostics,
                           'reference_count': 1, 'identity_search_performed': False,
                           'confidence_calibrated': False,
                           'timing_ms': {'total': (time.perf_counter()-start)*1000}})


class MatchSession:
    """Explicit rematch/unlock lifecycle, no automatic retries or map switches.

    This baseline cannot emit MATCHED, so it cannot enter LOCK. The lifecycle
    already preserves accepted results for a future validated decision module.
    """
    def __init__(self, matcher: MapMatcher):
        self.matcher = matcher
        self._locked: MatchResult | None = None

    def match(self, screenshot: np.ndarray) -> MatchResult:
        if self._locked is not None:
            return self._locked
        result = self.matcher.match(screenshot)
        if result.status == 'MATCHED':
            self._locked = result
        return result

    def unlock(self) -> None:
        self._locked = None

    def rematch(self, screenshot: np.ndarray) -> MatchResult:
        self.unlock()
        return self.match(screenshot)
