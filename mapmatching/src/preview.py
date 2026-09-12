"""Deterministic screenshot compositing; no GUI/game interaction or GT input."""
from __future__ import annotations
from dataclasses import dataclass
import cv2
import numpy as np
from .evidence import extract
from .reference import Reference
from .types import Candidate


@dataclass(frozen=True)
class PreviewStyle:
    fill_alpha: float = .12
    wall_alpha: float = .80
    route_alpha: float = .85
    cyan_bgr: tuple[int, int, int] = (240, 210, 45)


def render_preview(screenshot: np.ndarray, reference_image: np.ndarray,
                   reference: Reference, candidate: Candidate,
                   style: PreviewStyle = PreviewStyle()) -> tuple[np.ndarray, dict]:
    """Render an explicitly requested candidate preview, never approve a LOCK.

    Pose maps ORIGINAL reference coordinates to ORIGINAL screenshot coordinates.
    Pixels outside the evidence viewport are preserved exactly.
    """
    if candidate.map_id != reference.map_id or candidate.pose is None:
        raise ValueError('Candidate/reference identity mismatch or missing pose')
    region = next((r for r in reference.regions if r['floor'] == candidate.floor), None)
    if region is None:
        raise ValueError('Reviewed floor region is required for a preview')
    p = candidate.pose
    if not np.isfinite([p.scale, p.tx, p.ty]).all() or p.scale <= 0:
        raise ValueError('Invalid pose')
    sh, sw = screenshot.shape[:2]
    rh, rw = reference_image.shape[:2]
    valid = np.zeros((rh, rw), np.uint8)
    x0,y0,x1,y1 = region['bbox']
    valid[y0:y1,x0:x1] = 1
    for ex0,ey0,ex1,ey1 in reference.exclusions:
        valid[ey0:ey1,ex0:ex1] = 0
    hsv = cv2.cvtColor(reference_image, cv2.COLOR_BGR2HSV)
    annotations = (((hsv[:,:,1]>115)&(hsv[:,:,2]>120))|((hsv[:,:,1]<55)&(hsv[:,:,2]>180))|((hsv[:,:,1]<40)&(hsv[:,:,2]<35))).astype(np.uint8)
    # Reconstruct beneath thin authored marks for DISPLAY outlines only. The
    # original unmodified RGB supplies route/text colors below.
    cleaned = cv2.inpaint(reference_image, annotations*255, 3, cv2.INPAINT_TELEA)
    structure = extract(cleaned, reference=True, max_side=max(rh,rw), exclude_regions=reference.exclusions).mask
    structure &= valid
    # Display-only cleanup. Small detached text glyphs are not rooms. Enclosed
    # white lettering/black icons are filled for outlines; blue-dark courtyard
    # holes remain holes. This never changes retrieval/registration evidence.
    n,components,stats,_ = cv2.connectedComponentsWithStats(structure,8)
    for i in range(1,n):
        if stats[i,cv2.CC_STAT_AREA] < 500:
            structure[components == i] = 0
    n,holes,stats,_ = cv2.connectedComponentsWithStats(1-structure,8)
    backdrop = (hsv[:,:,0]>=85)&(hsv[:,:,0]<=115)&(hsv[:,:,1]>=60)&(hsv[:,:,2]<78)
    for i in range(1,n):
        if stats[i,cv2.CC_STAT_AREA] < 4000:
            region_pixels = holes == i
            if np.mean(backdrop[region_pixels]) < .6 and np.all(valid[region_pixels]):
                structure[region_pixels] = 1
    # Keep route marks only near structural floor pixels. Long author-drawn
    # inter-floor connectors through blank space are not walking corridors.
    route = ((hsv[:,:,1] > 115)&(hsv[:,:,2] > 120)).astype(np.uint8)
    route &= valid & cv2.dilate(structure, np.ones((9,9), np.uint8))
    lettering = ((hsv[:,:,1]<55)&(hsv[:,:,2]>190)).astype(np.uint8)
    lettering &= valid & structure
    affine = np.array([[p.scale, 0, p.tx], [0, p.scale, p.ty]], np.float64)
    warped_structure = cv2.warpAffine(structure.astype(np.float32), affine, (sw,sh), flags=cv2.INTER_LINEAR)
    warped_routes = cv2.warpAffine(route.astype(np.float32), affine, (sw,sh), flags=cv2.INTER_LINEAR)
    warped_letters = cv2.warpAffine(lettering.astype(np.float32), affine, (sw,sh), flags=cv2.INTER_LINEAR)
    warped_rgb = cv2.warpAffine(reference_image, affine, (sw,sh), flags=cv2.INTER_LINEAR).astype(np.float32)
    outline = cv2.morphologyEx((warped_structure>.5).astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3,3), np.uint8))
    ev = extract(screenshot)
    if ev.roi is None:
        raise ValueError('No reviewed viewport policy')
    x0,y0,x1,y1 = np.rint(np.array(ev.roi)/ev.image_factor).astype(int)
    viewport = np.zeros((sh,sw), np.float32)
    viewport[max(0,y0):min(sh,y1),max(0,x0):min(sw,x1)] = 1
    alpha = np.maximum(style.fill_alpha*warped_structure, style.wall_alpha*outline)*viewport
    result = screenshot[:,:,:3].astype(np.float32)*(1-alpha[:,:,None])+np.array(style.cyan_bgr)*(alpha[:,:,None])
    route_alpha = style.route_alpha*np.maximum(warped_routes,warped_letters)*viewport
    result = result*(1-route_alpha[:,:,None])+warped_rgb*route_alpha[:,:,None]
    result = np.clip(np.rint(result), 0, 255).astype(np.uint8)
    changed = np.any(result != screenshot[:,:,:3], axis=2)
    return result, {'kind': 'candidate_preview_not_lock', 'map_id': candidate.map_id, 'floor': candidate.floor,
                    'pose': {'scale': p.scale, 'tx': p.tx, 'ty': p.ty},
                    'coordinate_system': 'original reference -> original full screenshot',
                    'viewport_xyxy': [int(x0),int(y0),int(x1),int(y1)],
                    'changed_pixels': int(changed.sum()),
                    'outside_viewport_changed_pixels': int(np.sum(changed & (viewport == 0))),
                    'style': {'fill_alpha': style.fill_alpha, 'wall_alpha': style.wall_alpha, 'route_alpha': style.route_alpha},
                    'note': 'Cyan is standard-map structure; original colors are authored route marks. Uncalibrated candidate display, not a validated navigation lock.'}
