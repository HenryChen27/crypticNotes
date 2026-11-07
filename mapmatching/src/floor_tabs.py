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
        negative_digits = []
        for index in range(1, count):
            x,y,bw,bh,area = stats[index]
            if not (8 <= bh <= 55 and .10 <= bw/bh <= .85 and area >= 12):
                continue
            glyph = cv2.resize((labels[y:y+bh,x:x+bw]==index).astype(np.uint8),
                                (20,32), interpolation=cv2.INTER_NEAREST)>0
            scores = {i: float(np.logical_and(glyph,t).sum()/max(1,np.logical_or(glyph,t).sum()))
                      for i,t in _templates().items()}
            digit = max(scores, key=scores.get)
            # A highlighted basement digit can lose thin edge pixels to the
            # textured button. Only allow this weaker glyph as the EXTRA left
            # digit: the normal 1/2 pair, minus bar and spacing remain required.
            if digit==1 and scores[1]>=.60 and scores[1]-scores[2]>=.12:
                negative_digits.append((digit,x,y,bw,bh,scores[1]))
            if scores[digit] < .67 or scores[digit]-scores[3-digit] < .12:
                continue
            digits.append((digit,x,y,bw,bh,scores[digit]))
        for one in negative_digits:
            _,x,y,bw,bh,score = one
            cx = x+bw/2
            for two in (d for d in digits if d[0]==2):
                _,tx,ty,tw,th,ts = two
                step = tx+tw/2-cx
                if not (1.8*bh <= step <= 3.3*bh and abs(ty-y)<.22*bh and .8< th/bh <1.25):
                    continue
                centers = [cx, tx+tw/2]
                floors = [1,2]
                strong_negative_support = False
                # The extra left-hand '1' must also have a horizontal minus.
                for neg in (d for d in negative_digits if d[1]<x):
                    _,nx,ny,nw,nh,ns = neg
                    if abs(ny-y)>.22*bh or abs((nx+nw/2)-(cx-step+.20*bh))>.4*bh:
                        continue
                    bars = [s for s in stats[1:] if .25*bh<=s[2]<=.85*bh
                            and 1<=s[3]<=.24*bh and .07*bh < nx-(s[0]+s[2]) < .5*bh
                            and abs(s[1]+s[3]/2-(ny+.55*nh))<.23*bh
                            and s[4]/(s[2]*s[3])>.5]
                    if bars:
                        strong_negative_support = ns >= .67
                        centers.insert(0,cx-step);floors.insert(0,-1)
                        break
                # A worn ordinary 1 needs a separately strong -1 glyph, its
                # minus bar and the strong 2; never weaken the two-button case.
                if score < .67 and not strong_negative_support:
                    continue
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


BASEMENT_TABS = 4   # 磷光症 shows −1 … −4; a column with another count is not read.


def hide_floor_column(pixels, reading=None, pad=6):
    """Black out the basement button column so its bright highlighted square
    is not taken for map terrain. The column sits inside the phone map
    viewport (unlike the 1/2 pair of 厄运之女, which is above it), and its
    square alone yields enough corners for a bogus fit on an empty floor.
    Returns the input untouched when no column was read."""
    if reading is None:
        reading = inspect_basement_tabs(pixels)
    bbox = reading.get('bbox') if reading.get('reader') == 'basement' else None
    if not bbox:
        return pixels
    x0, y0, x1, y1 = bbox
    out = pixels.copy()
    out[max(0, y0-pad):y1+pad, max(0, x0-pad):x1+pad] = 0
    return out


def inspect_basement_tabs(pixels):
    """Read the vertical basement column of 磷光症 (−1 … −4 stacked on the right).

    The viewed button is a bright square with a dark label; the others are
    dim labels on the dark panel. The floor is the position of the bright
    square in that column. Every row must share one x-centre and one pitch,
    the column must be complete (``BASEMENT_TABS`` rows), and the dim rows
    must carry a minus bar or a glyph, so an unrelated bright square (an item
    slot, a dialog) never reads as a floor, and a row lost to downscaling
    yields no reading rather than the wrong floor. This never reads the 1/2
    pair of 厄运之女: that row is horizontal and has no minus bars.
    """
    unknown = lambda reason: dict(floor=None, reason=reason, reader='basement')
    if pixels is None or pixels.ndim != 3:
        return unknown('invalid_frame')
    height, width = pixels.shape[:2]
    if width <= height:
        return unknown('portrait')
    gray = cv2.cvtColor(pixels[:,:,:3], cv2.COLOR_BGR2GRAY)
    ox, oy = int(.74*width), int(.06*height)
    roi = gray[oy:int(.60*height), ox:int(.96*width)]
    if roi.size == 0:
        return unknown('invalid_frame')
    background = float(np.median(roi))
    if background > 90:
        return unknown('no_dark_panel')
    # The panel may be tinted dark (damage flash): scale the step by contrast,
    # but cap it, or white text in the corner (a PC client's ESC hint, a video
    # watermark) lifts the step above the highlighted square itself.
    contrast = float(np.percentile(roi, 99.5))-background
    bright = (roi > background+max(22., min(50., .45*contrast))).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(bright, 8)
    boxes, marks = [], []
    for index in range(1, count):
        x, y, bw, bh, area = (int(v) for v in stats[index])
        if (.05*height <= bh <= .12*height and .5 <= bw/bh <= 1.15 and area >= .7*bw*bh
                and x > 0 and y > 0 and x+bw < roi.shape[1] and y+bh < roi.shape[0]):
            boxes.append((x, y, bw, bh))
        elif bh <= .04*height and bw <= .03*height:
            marks.append((x+bw/2, y+bh/2))          # glyph strokes and minus bars
    if len(boxes) != 1:
        return unknown('no_single_highlight' if boxes else 'no_highlight')
    x, y, bw, bh = boxes[0]
    cy = y+bh/2
    # The bright square must carry its own dark label (digit, maybe fused
    # with its minus bar); an empty bright square is not a floor button.
    inner = roi[y:y+bh, x:x+bw]
    dark = (inner < np.median(inner)-.35*(np.median(inner)-background)).astype(np.uint8)
    n, _, inner_stats, _ = cv2.connectedComponentsWithStats(dark, 8)
    if not any(.18*bh <= s[3] <= .45*bh and s[2] <= .6*bh for s in inner_stats[1:]):
        return unknown('highlight_without_label')
    # Dim rows: brightness bumps of the column strip under the square, which
    # survive downscaling better than the individual strokes of a thin 1.
    strip = roi[:, x:x+bw].astype(np.float32)
    profile = cv2.blur(strip.mean(axis=1).reshape(-1, 1), (1, max(3, int(.012*height)))).ravel()
    base = float(np.median(profile))
    lit = profile > base+max(3., min(7., .08*contrast))
    lit[max(0, int(y-.1*bh)):int(y+1.1*bh)] = False
    rows, start = [], None
    for index, on in enumerate(list(lit)+[False]):
        if on and start is None:
            start = index
        if not on and start is not None:
            if .08*bh <= index-start <= .6*bh:
                rows.append((start+index)/2)
            start = None
    rows = [r for r in rows if any(abs(my-r) <= .3*bh and x-.2*bw <= mx <= x+1.2*bw for mx, my in marks)]
    # Only rows on the button lattice (one, two or three cells from the
    # square); a caption or watermark above the column is not a row.
    rows = [r for r in rows if any(k*.95*bh <= abs(r-cy) <= k*1.2*bh for k in (1, 2, 3))]
    centres = sorted(rows+[cy])
    if len(centres) != BASEMENT_TABS:
        return unknown('incomplete_column' if len(centres) < BASEMENT_TABS else 'too_many_rows')
    steps = np.diff(centres)
    pitch = float(np.median(steps))
    if not (.85*bh <= pitch <= 1.5*bh) or np.any(np.abs(steps-pitch) > .15*pitch):
        return unknown('irregular_column')
    floor = -(sum(1 for c in rows if c < cy)+1)
    return dict(floor=floor, buttons=[-(i+1) for i in range(BASEMENT_TABS)], pitch=pitch,
                reader='basement', reason='basement_column_highlight',
                bbox=[int(ox+x), int(oy+centres[0]-bh/2), int(ox+x+bw), int(oy+centres[-1]+bh/2)])
