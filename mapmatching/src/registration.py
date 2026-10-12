from __future__ import annotations
import numpy as np
from scipy.optimize import minimize
from .retrieval import Retrieved
from .types import Candidate, Evidence, Pose
from .verification import observed_points, verify, residuals


def register(game: Evidence, retrieved: Retrieved, *, scale_bounds=None, refinement_radius=8, refinement_candidates=3) -> Candidate:
    ref = retrieved.reference
    result = Candidate(ref.map_id, ref.difficulty, ref.mode, retrieved.score)
    points = observed_points(game)
    # Work in normalized image coordinates so resolution and atlas pixel size
    # do not change the gate. Reject collapsed whole-floor hypotheses BEFORE
    # scoring, allowing a valid larger hypothesis to win instead.
    low,high=.45,4.0
    if scale_bounds is not None:
        factor=game.image_factor/ref.evidence.image_factor
        low=max(low,scale_bounds[0]*factor)
        high=min(high,scale_bounds[1]*factor)
    hypotheses=np.asarray(retrieved.hypotheses)
    if len(hypotheses):
        hypotheses=hypotheses[(hypotheses[:,0]>=low)&(hypotheses[:,0]<=high)]
    if not len(points) or not len(hypotheses):
        return result
    ranked = sorted(hypotheses, key=lambda p: -verify(p, points, ref)[0])
    best, best_score = ranked[0], -1.
    for initial in ranked[:refinement_candidates]:
        # Bounded local refinement, never a whole-map translation search.
        s, tx, ty = initial
        def objective(p: np.ndarray) -> float:
            return float(np.minimum(residuals(p, points, ref), 10).mean())
        fit = minimize(objective, initial, method='Powell', bounds=[(max(low,s*.9), min(high,s*1.1)), (tx-refinement_radius, tx+refinement_radius), (ty-refinement_radius, ty+refinement_radius)], options={'maxiter': 12, 'xtol': .02, 'ftol': .001})
        for pose in (initial, fit.x):
            score, contradiction = verify(pose, points, ref)
            if score > best_score:
                best, best_score, result.contradiction = pose, score, contradiction
    s, tx, ty = best
    result.pose = Pose(float(s*ref.evidence.image_factor/game.image_factor), float(tx/game.image_factor), float(ty/game.image_factor))
    result.explained = best_score
    # Floor votes come only from boundary points explained by this pose. HUD
    # outliers must not overturn the floor of the geometrically aligned region.
    aligned_points = points[residuals(best, points, ref) < 5]
    original_xy = (aligned_points-np.array([tx,ty]))/s/ref.evidence.image_factor
    for region in ref.regions:
        x0,y0,x1,y1 = region['bbox']
        supported = (original_xy[:,0]>=x0)&(original_xy[:,0]<x1)&(original_xy[:,1]>=y0)&(original_xy[:,1]<y1)
        for ex0,ey0,ex1,ey1 in ref.exclusions:
            supported &= ~((original_xy[:,0]>=ex0)&(original_xy[:,0]<ex1)&(original_xy[:,1]>=ey0)&(original_xy[:,1]<ey1))
        if len(supported) >= 20 and np.mean(supported) >= .95:
            result.floor = region['floor']
            break
    return result
