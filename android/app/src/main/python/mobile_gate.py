"""Mobile map-panel controls, calibrated from supplied 2400x1080 screenshots."""
from functools import lru_cache
from pathlib import Path
import cv2
import numpy as np
import mobile_templates

@lru_cache(maxsize=1)
def templates():
    folder=Path(mobile_templates.__file__).parent
    return {name:cv2.imdecode(np.frombuffer((folder/(name+'.png')).read_bytes(),np.uint8),0)
            for name in ('close','zoom','overview')}

def inspect_map_ui(pixels, excluded=None):
    h,w=pixels.shape[:2]
    if w<=h:return dict(visible=False,reason='portrait')
    gray=cv2.resize(cv2.cvtColor(pixels,cv2.COLOR_BGR2GRAY),(1280,round(h*1280/w)))
    h,w=gray.shape
    regions={'close':(.70,0.,1.,.23),'zoom':(.78,.20,1.,.55),'overview':(.65,.72,1.,1.)}
    scores={}
    obscured=[]
    for name,template in templates().items():
        x,y,X,Y=regions[name];roi=gray[int(y*h):int(Y*h),int(x*w):int(X*w)]
        if excluded is not None:
            a,b,A,B=map(float,excluded)
            if a<X and A>x and b<Y and B>y:
                obscured.append(name)
                continue
        best=0.
        for scale in (.43,.50,.56,.625,.69,.76,.85,1.):
            sample=cv2.resize(template,None,fx=scale,fy=scale)
            if min(sample.shape)<4 or sample.shape[0]>roi.shape[0] or sample.shape[1]>roi.shape[1]:continue
            best=max(best,float(cv2.minMaxLoc(cv2.matchTemplate(roi,sample,cv2.TM_CCOEFF_NORMED))[1]))
        scores[name]=best
    return dict(visible=len(scores)>=2 and all(v>=.78 for v in scores.values()),
                scores=scores,obscured=obscured,method='mobile_controls_occlusion_v2')
