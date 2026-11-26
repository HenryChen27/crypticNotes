from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np


@dataclass
class Evidence:
    mask: np.ndarray
    boundary: np.ndarray
    corners: np.ndarray
    descriptors: np.ndarray
    radii: np.ndarray
    image_factor: float
    roi: tuple[int, int, int, int] | None
    diagnostics: dict = field(default_factory=dict)
    boundary_weights: np.ndarray | None = None


@dataclass(frozen=True)
class Pose:
    """Original reference pixels -> original full screenshot pixels."""
    scale: float
    tx: float
    ty: float


@dataclass(frozen=True)
class LayoutMemory:
    layers: tuple[int, ...]
    anchor: Pose
    frame_size: tuple[int, int]
    platform: str
    frame_key: str | None


@dataclass
class Candidate:
    map_id: str
    difficulty: str
    mode: str | None
    retrieval_score: float
    pose: Pose | None = None
    explained: float | None = None
    contradiction: float | None = None
    floor: int | None = None
    layout_memory: LayoutMemory | None = None
