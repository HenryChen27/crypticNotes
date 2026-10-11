"""Conservative verification before reusing a result marked dirty by input."""
import cv2
import numpy as np
from .map_visibility import inspect_map_ui


def unchanged_map(before,after,ignored_rect=None):
    if before is None or before.shape != after.shape:
        return False,{'reason':'capture_changed'}
    ui=inspect_map_ui(after)
    # Only a known companion rectangle can explain an obstructed control.
    # The earlier clean frame plus an unchanged viewport must both corroborate it.
    if not ui['visible'] and not (ignored_rect is not None and inspect_map_ui(before)['visible']):
        return False,{'reason':'map_ui_missing','map_ui':ui}
    h,w=before.shape[:2]
    # Compare the whole map viewport; do not align images here, since any
    # translation or zoom makes the original overlay transform invalid.
    roi=(slice(int(h*.18),int(h*.82)),slice(int(w*.25),int(w*.91)))
    if ignored_rect is not None:
        x,y,rw,rh=ignored_rect
        left,top=max(0,x),max(0,y)
        right,bottom=min(w,x+rw),min(h,y+rh)
        if right>left and bottom>top:
            before=before.copy();after=after.copy()
            before[top:bottom,left:right]=0
            after[top:bottom,left:right]=0
    a=cv2.resize(before[roi],(640,400),interpolation=cv2.INTER_AREA)
    b=cv2.resize(after[roi],(640,400),interpolation=cv2.INTER_AREA)
    delta=np.max(cv2.absdiff(a,b),axis=2)
    changed=float(np.mean(delta>18))
    return changed<.0025,{'reason':'pixel_comparison','changed_fraction':changed}
