"""参考图库的对外门面。真正的读写全在 `mapstore` 里 —— 这个文件只剩
`build` / `load` 两个薄包装，因为 `live.py`、`__main__.py`、benchmarks
都从 `reference` 拿入口，换掉名字的收益抵不上改二十处调用点。

索引的位置变了：不再是 `reference/index/`，而是 `maps/`（见 `mapstore`）。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import cv2
import numpy as np
from .types import Evidence
from . import mapstore

VERSION = mapstore.VERSION


def read_image(path: Path) -> np.ndarray:
    image = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f'Cannot decode image: {path}')
    return image


@dataclass
class Reference:
    map_id: str
    difficulty: str
    mode: str | None
    source: str
    evidence: Evidence
    distance: np.ndarray
    regions: list[dict] = field(default_factory=list)
    exclusions: list[list[int]] = field(default_factory=list)


def build(maps: Path, remove_annotations: bool = True) -> None:
    """全量重建。**只认 `maps/floors.json` 里登记过的图** —— `maps/` 下多出来的
    文件（比如用户直接粘贴进去的、或者躺在 `_unindexed/` 的）被安静忽略。

    原来的 `startswith(('加页手记地图', '凉哈皮'))` 前缀扫描没了：难度和人数现在
    直接从 `maps/<难度>/[<人数>/]` 的路径读，不再靠中文文件夹名猜。
    """
    if remove_annotations != mapstore.REMOVE_ANNOTATIONS:
        raise ValueError('remove_annotations 已固定为模块级常量，改它会让旧特征全部作废')
    if not mapstore.live_entries(maps):
        raise ValueError('No original reference collections found')
    mapstore.build_index(maps, force=True)


def load(directory: Path, *, difficulty: str | None = None, mode: str | None = None) -> list[Reference]:
    return mapstore.load_references(directory, difficulty=difficulty, mode=mode)
