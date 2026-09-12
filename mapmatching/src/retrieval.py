"""Local occupancy descriptors -> sparse geometric votes, no dense XY search."""
from __future__ import annotations
from dataclasses import dataclass
import cv2
import numpy as np
from .reference import Reference
from .types import Evidence


@dataclass
class Retrieved:
    reference: Reference
    score: float
    hypotheses: np.ndarray
    matches: int


def retrieve(game: Evidence, references: list[Reference], spatial: bool = True) -> list[Retrieved]:
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    results = []
    for ref in references:
        r = ref.evidence
        if len(game.corners) < 2 or len(r.corners) < 2:
            results.append(Retrieved(ref, 0., np.empty((0, 3)), 0))
            continue
        matches = matcher.knnMatch(game.descriptors, r.descriptors, k=2)
        # Retain ambiguity: repetitive L corners should not be forced unique.
        matches = [m for group in matches for m in group if m.distance < 5.0]
        if not matches:
            results.append(Retrieved(ref, 0., np.empty((0, 3)), 0))
            continue
        gi = np.array([m.queryIdx for m in matches])
        ri = np.array([m.trainIdx for m in matches])
        gp, rp = game.corners[gi], r.corners[ri]
        # Pairwise anchor geometry proposes uniform scale with zero rotation.
        aa, bb = np.triu_indices(len(matches), 1)
        dg, dr = gp[bb]-gp[aa], rp[bb]-rp[aa]
        rr = (dr*dr).sum(axis=1)
        scales = (dg*dr).sum(axis=1) / np.maximum(rr, 1)
        residual = np.linalg.norm(dg-scales[:, None]*dr, axis=1)
        valid = (rr > 100) & (np.linalg.norm(dg, axis=1)>12) & (scales>.15) & (scales<8) & (residual<3)
        aa, bb, scales = aa[valid], bb[valid], scales[valid]
        xy = (gp[aa]+gp[bb]-scales[:, None]*(rp[aa]+rp[bb])) / 2
        poses = np.column_stack((scales, xy))
        if not len(poses):
            results.append(Retrieved(ref, 0., poses, len(matches)))
            continue
        # Cheap sparse consistency only; boundary registration is top-K only.
        keys = np.column_stack((np.round(np.log(scales)/.12), np.round(xy/8))).astype(int)
        _, first, counts = np.unique(keys, axis=0, return_index=True, return_counts=True)
        order = np.argsort(-counts, kind='stable')[:80]
        poses = poses[first[order]]
        support = []
        for s, tx, ty in poses:
            err = np.linalg.norm(gp - (s*rp+[tx, ty]), axis=1)
            # Count distinct game positions, not duplicated descriptor radii.
            points = np.unique(gp[err < 4].round(1), axis=0)
            support.append(len(points))
        order = np.argsort(-np.asarray(support), kind='stable')
        poses = poses[order[:24]]
        score = float(max(support)) if spatial else float(np.mean([1-m.distance/12 for m in matches]))
        results.append(Retrieved(ref, score, poses, len(matches)))
    return sorted(results, key=lambda x: (-x.score, x.reference.map_id))
