"""Baseline hypothesis: low-saturation filled floor geometry survives both domains.

Thresholds are fixed research settings, not learned from map identity. The game
viewport exclusion is explicitly a layout prior and is evaluated by ablation.
Dark/occluded pixels never supply negative evidence to verification.
"""
from __future__ import annotations
import cv2
import numpy as np
from mapmatching.config import DEFAULT
from .types import Evidence
from .occlusion import control_panels, sharp_boundary


def extract(image: np.ndarray, *, reference: bool = False,
            remove_annotations: bool = True, exclude_hud: bool = True,
            max_side: int = DEFAULT.max_side, exclude_regions: list[list[int]] | None = None,
            screenshot_cleanup: bool = True) -> Evidence:
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] not in (3, 4) or min(image.shape[:2]) < 3:
        raise ValueError('Expected nonempty uint8 BGR/BGRA image of at least 3x3 pixels')
    factor = min(1., max_side / max(image.shape[:2]))
    bgr = cv2.resize(image[:, :, :3], None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, w = bgr.shape[:2]
    # Blue-grey corridors and muted brown room fills. V excludes dark backdrop.
    mask = ((hsv[:, :, 2] >= DEFAULT.value_min) & (hsv[:, :, 2] <= DEFAULT.value_max) & (hsv[:, :, 1] <= DEFAULT.saturation_max)).astype(np.uint8)
    panels = control_panels(bgr) if not reference and exclude_hud and screenshot_cleanup else []
    for x0,y0,x1,y1 in panels:
        mask[y0:y1,x0:x1] = 0
    for box in exclude_regions or []:
        x0,y0,x1,y1 = np.rint(np.array(box)*factor).astype(int)
        mask[max(0,y0):min(h,y1), max(0,x0):min(w,x1)] = 0
    roi = None
    if not reference and exclude_hud:
        roi = (int(.25*w), int(.18*h), int(.91*w), int(.82*h))
        keep = np.zeros_like(mask)
        x0, y0, x1, y1 = roi
        keep[y0:y1, x0:x1] = 1
        mask &= keep
    if remove_annotations:
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    keep_ids = np.flatnonzero(stats[:, cv2.CC_STAT_AREA] >= DEFAULT.min_component_area)
    keep_ids = keep_ids[keep_ids != 0]
    mask = np.isin(labels, keep_ids).astype(np.uint8)
    # Patch internal text/icon holes, but retain large holes in the topology.
    if remove_annotations:
        n, holes, hs, _ = cv2.connectedComponentsWithStats(1-mask, 8)
        for i in range(1, n):
            if hs[i, cv2.CC_STAT_AREA] <= 35:
                mask[holes == i] = 1
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    boundary = np.zeros_like(mask)
    cv2.drawContours(boundary, contours, -1, 1, 1)
    boundary_weights = None
    weak_boundary_count = 0
    if not reference and screenshot_cleanup:
        sharp = sharp_boundary(bgr,boundary)
        # Soft fog edges still carry some evidence. Do not discard faint real
        # walls wholesale: visible sharp edges get twice the sampling weight.
        boundary_weights = boundary + sharp
        weak_boundary_count = int((boundary-sharp).sum())
    corners, descs, radii = [], [], []
    float_mask = mask.astype(np.float32)
    for contour in contours:
        poly = cv2.approxPolyDP(contour, 2., True).reshape(-1, 2).astype(float)
        if len(poly) < 3:
            continue
        for j, p in enumerate(poly):
            a, b = poly[j-1]-p, poly[(j+1) % len(poly)]-p
            la, lb = np.linalg.norm(a), np.linalg.norm(b)
            if min(la, lb) < 5 or abs(np.dot(a, b)/(la*lb)) > .45:
                continue
            radius = float(np.clip(min(la, lb), 7, 60))
            # Fixed orientation, normalized local occupancy at two radii.
            for multiplier in (.75, 1.5):
                r = radius * multiplier
                grid = np.linspace(-r, r, 12, dtype=np.float32)
                xx, yy = np.meshgrid(grid+p[0], grid+p[1])
                patch = cv2.remap(float_mask, xx.astype(np.float32), yy.astype(np.float32), cv2.INTER_LINEAR)
                corners.append(p)
                descs.append(patch.ravel())
                radii.append(r)
    total_anchors = len(corners)
    limit = DEFAULT.max_reference_descriptors if reference else DEFAULT.max_anchor_descriptors
    selection = np.linspace(0, total_anchors-1, min(limit, total_anchors), dtype=int)
    return Evidence(mask, boundary, np.asarray(corners, np.float32).reshape(-1, 2)[selection],
                    np.asarray(descs, np.float32).reshape(-1, 144)[selection],
                    np.asarray(radii, np.float32)[selection], factor, roi,
                    {'foreground_pixels': int(mask.sum()), 'anchors': len(selection), 'anchors_before_cap': total_anchors,
                     'roi_method': 'fixed_normalized_layout_prior' if roi else 'full_image',
                     'excluded_panel_boxes': (np.rint(np.array(panels).reshape(-1,4)/factor).astype(int).tolist()),
                     'weak_boundary_pixels_downweighted': weak_boundary_count,
                     'fog_mask_available': False}, boundary_weights)
