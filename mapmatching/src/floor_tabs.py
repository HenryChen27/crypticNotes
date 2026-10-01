"""Read game floor tabs by digit shape, group geometry and background contrast.

Only a clearly selected button returns a floor. This detects the VIEWED floor,
not the character's floor, and does not itself prove the map panel is open.
"""
from functools import lru_cache
from pathlib import Path
import cv2
import numpy as np


@lru_cache(maxsize=1)
def _templates():
    root = Path(__file__).resolve().parents[1]/'assets/map-ui'
    return {i: cv2.resize(cv2.imdecode(np.frombuffer((root/f'floor-{i}.png').read_bytes(),
                np.uint8), 0), (20, 32), interpolation=cv2.INTER_NEAREST)>0 for i in (1, 2)}


def inspect_floor_tabs(pixels):
    if pixels is None or pixels.ndim != 3:
        return dict(floor=None, reason='invalid_frame')
    height, width = pixels.shape[:2]
    if width <= height:
        return dict(floor=None, reason='portrait')
    factor = min(1., 1280/width)
    gray = cv2.resize(cv2.cvtColor(pixels[:,:,:3], cv2.COLOR_BGR2GRAY),
                      None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
    h,w = gray.shape
    ox,oy = int(.55*w), int(.015*h)
    roi = gray[oy:int(.25*h), ox:int(.94*w)]
    readings = []
    for threshold in (105, 130, 155, 180):
        mask = (roi > threshold).astype(np.uint8)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
        digits = []
        for index in range(1, count):
            x,y,bw,bh,area = stats[index]
            if not (8 <= bh <= 55 and .10 <= bw/bh <= .85 and area >= 12):
                continue
            glyph = cv2.resize((labels[y:y+bh,x:x+bw]==index).astype(np.uint8),
                                (20,32), interpolation=cv2.INTER_NEAREST)>0
            scores = {i: float(np.logical_and(glyph,t).sum()/max(1,np.logical_or(glyph,t).sum()))
                      for i,t in _templates().items()}
            digit = max(scores, key=scores.get)
            if scores[digit] < .67 or scores[digit]-scores[3-digit] < .12:
                continue
            digits.append((digit,x,y,bw,bh,scores[digit]))
        for one in (d for d in digits if d[0]==1):
            _,x,y,bw,bh,score = one
            cx = x+bw/2
            for two in (d for d in digits if d[0]==2):
                _,tx,ty,tw,th,ts = two
                step = tx+tw/2-cx
                if not (1.8*bh <= step <= 3.3*bh and abs(ty-y)<.22*bh and .8< th/bh <1.25):
                    continue
                centers = [cx, tx+tw/2]
                floors = [1,2]
                # The extra left-hand '1' must also have a horizontal minus.
                for neg in (d for d in digits if d[0]==1 and d[1]<x):
                    _,nx,ny,nw,nh,ns = neg
                    if abs(ny-y)>.22*bh or abs((nx+nw/2)-(cx-step+.20*bh))>.4*bh:
                        continue
                    bars = [s for s in stats[1:] if .25*bh<=s[2]<=.85*bh
                            and 1<=s[3]<=.24*bh and .07*bh < nx-(s[0]+s[2]) < .5*bh
                            and abs(s[1]+s[3]/2-(ny+.55*nh))<.23*bh
                            and s[4]/(s[2]*s[3])>.5]
                    if bars:
                        centers.insert(0,cx-step);floors.insert(0,-1)
                        break
                values=[]
                for center in centers:
                    a,b=int(center-step*.42),int(center+step*.42)
                    top,bottom=int(y-.22*bh),int(y+1.2*bh)
                    if a<0 or top<0 or b>roi.shape[1] or bottom>roi.shape[0]:
                        values=[];break
                    values.append(float(np.median(roi[top:bottom,a:b])))
                if not values: continue
                order=np.argsort(values)
                if values[order[-1]]<55 or values[order[-1]]-values[order[-2]]<18:
                    continue
                readings.append(dict(floor=floors[order[-1]],
                    buttons=floors, brightness=values, digit_score=min(score,ts),
                    bbox=[int((ox+centers[0]-step/2)/factor),int((oy+y-.3*bh)/factor),
                          int((ox+centers[-1]+step/2)/factor),int((oy+y+1.3*bh)/factor)]))
    if not readings:
        return dict(floor=None, reason='tabs_not_clear')
    if len({r['floor'] for r in readings}) != 1:
        return dict(floor=None, reason='conflicting_tabs')
    best=max(readings,key=lambda r:r['digit_score'])
    return dict(**best, reason='digit_group_and_highlight')
