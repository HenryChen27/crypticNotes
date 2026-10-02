"""Independent live-screen gate using corroborating map-only UI controls.

Templates are control crops, never map geometry or identity answers.
An unrecognized layout is not allowed to display a live overlay.
"""
from functools import lru_cache
from pathlib import Path
import cv2
import numpy as np


@lru_cache(maxsize=1)
def templates():
    folder = Path(__file__).resolve().parents[1]/'assets/map-ui'
    return {name: cv2.imdecode(np.frombuffer((folder/(name+'.png')).read_bytes(),np.uint8),0)
            for name in ('close','overview')}


def inspect_map_ui(pixels):
    h,w = pixels.shape[:2]
    gray = cv2.cvtColor(pixels[:,:,:3],cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray,(960,max(1,round(h*960/w))),interpolation=cv2.INTER_AREA)
    h,w = gray.shape
    scores = {}
    for name,t in templates().items():
        # Relative vertical placement prevents arbitrary scenery elsewhere
        # on the screen from satisfying the two-control check.
        roi = gray[:int(h*.40),int(w*.65):] if name=='close' else gray[int(h*.65):,int(w*.55):]
        best = 0.
        for scale in (.65,.75,.85,.925,1.,1.075,1.15,1.3,1.5):
            sample = cv2.resize(t,None,fx=scale,fy=scale)
            if min(sample.shape)<3 or any(a>b for a,b in zip(sample.shape,roi.shape)):
                continue
            best = max(best,float(cv2.minMaxLoc(cv2.matchTemplate(roi,sample,cv2.TM_CCOEFF_NORMED))[1]))
        scores[name] = best
    # A single rigid cutoff rejected real desktop maps (e.g. close=.796,
    # overview=.977). Require one strong control and a corroborating second
    # control, rather than allowing either control alone to open the gate.
    visible = min(scores.values()) >= .75 and max(scores.values()) >= .85
    floor_tabs = None
    if not visible and scores['overview'] >= .90:
        # The companion or another window can cover the top-right close icon.
        # A recognized floor-button group with a selected floor independently
        # confirms that the map is open; map geometry itself is not used here.
        from .floor_tabs import inspect_floor_tabs
        floor_tabs = inspect_floor_tabs(pixels)
        visible = floor_tabs.get('floor') is not None
    return dict(visible=visible,scores=scores,floor_tabs=floor_tabs,
                method='corroborated_map_controls_v2')
