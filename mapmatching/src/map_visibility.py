"""Independent live-screen gate using two map-only UI controls.

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
    return dict(visible=all(v>=.80 for v in scores.values()),scores=scores,
                method='two_map_controls_v1')
