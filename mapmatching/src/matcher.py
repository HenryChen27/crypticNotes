"""Pixel-only research API. Candidate scores are not identity probabilities."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from pathlib import Path
import time
import numpy as np
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

    def match(self, screenshot: np.ndarray) -> MatchResult:
        """Accept BGR pixels only; never paths, example IDs, paired maps or GT."""
        start = time.perf_counter()
        evidence = extract(screenshot)
        extracted = time.perf_counter()
        if len(evidence.corners) < 4:
            return MatchResult(reason='insufficient_visible_structure', diagnostics=evidence.diagnostics)
        retrieved = retrieve(evidence, self.references)
        ranked = time.perf_counter()
        candidates = sorted([register(evidence, r) for r in retrieved[:5]], key=lambda c: -(c.explained or 0))
        end = time.perf_counter()
        return MatchResult(candidates=candidates, diagnostics={**evidence.diagnostics,
                           'session_context': asdict(self.context),
                           'reference_count': len(self.references),
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
        ref = next((r for r in self.references if r.map_id == map_id), None)
        if ref is None:
            return MatchResult(reason='cached_map_outside_context')
        evidence = extract(screenshot)
        candidates = []
        if len(evidence.corners) >= 4:
            candidates = [register(evidence, retrieve(evidence,[ref])[0])]
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
