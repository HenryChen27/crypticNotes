"""Asymmetric observed-boundary explanation; unseen reference is unpenalized."""
from __future__ import annotations
import cv2
import numpy as np
from .reference import Reference
from .types import Evidence


def observed_points(game: Evidence, limit: int = 1200) -> np.ndarray:
    yy, xx = np.nonzero(game.boundary)
    points = np.column_stack((xx, yy)).astype(np.float32)
    if game.boundary_weights is not None and len(points):
        points = np.repeat(points,game.boundary_weights[yy,xx].astype(int),axis=0)
    return points[np.linspace(0, len(points)-1, min(limit, len(points)), dtype=int)] if len(points) else points


def residuals(pose: np.ndarray, points: np.ndarray, ref: Reference) -> np.ndarray:
    s, tx, ty = pose
    if s <= 0:
        return np.full(len(points), 100., np.float32)
    xy = ((points-[tx, ty])/s).astype(np.float32)
    dist = cv2.remap(ref.distance, xy[:, 0].reshape(-1, 1), xy[:, 1].reshape(-1, 1), cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_CONSTANT, borderValue=1000).ravel()
    return dist*s


def verify(pose: np.ndarray, points: np.ndarray, ref: Reference) -> tuple[float, float]:
    if not len(points):
        return 0., 1.
    distance = residuals(pose, points, ref)
    explained = float(np.exp(-.5*(distance/2.5)**2).mean())
    return explained, float(np.mean(distance > 5))
