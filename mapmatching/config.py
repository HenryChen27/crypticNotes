"""Fixed, reviewable research parameters; no example/map-specific overrides."""
from dataclasses import asdict, dataclass
import hashlib
import json


@dataclass(frozen=True)
class EvidenceConfig:
    max_side: int = 1000
    value_min: int = 78
    value_max: int = 170
    saturation_max: int = 80
    min_component_area: int = 45
    max_anchor_descriptors: int = 512
    max_reference_descriptors: int = 2048


DEFAULT = EvidenceConfig()


def fingerprint() -> str:
    return hashlib.sha256(json.dumps(asdict(DEFAULT), sort_keys=True).encode()).hexdigest()
