"""The lantern's two tricks, drawn on a click-through stage over the desktop,
plus the hand-drawn symbols it shares with the doll.

Layer stacks follow the usual real-time VFX recipe. Ghost fire: ground pool,
violet veil, smoke, three noisy tongues (violet → blue → white), a glowing
heart, embers with motion trails. Laser: a charging sphere fed by converging
streaks, a release shockwave, then core + halo + violet/cyan fringe + energy
dashes flowing along the beam, an impact flare with sparks and rings, and
scorch marks fading along the swept path.

Everything is a deterministic function of the mood's progress: no per-frame
randomness, so a replayed frame always looks the same.
"""
import math
from functools import lru_cache
from pathlib import Path
import numpy as np
from PySide6 import QtCore as C, QtGui as G


@lru_cache(maxsize=4)
def artwork(kind):
    """The lantern's own cold-inked '!', '?' and 'z' (re-inked from the doll's strokes)."""
    names = {'angry': '!.png', 'puzzled': 'question.png', 'sleep': 'z.png'}
    if kind not in names:
        return None
    image = G.QImage(str(Path(__file__).with_name(names[kind])))
    if image.isNull():
        return None
    image = image.convertToFormat(G.QImage.Format_RGBA8888)
    pixels = np.frombuffer(image.constBits(), np.uint8).reshape(image.height(), image.bytesPerLine()//4, 4)
    y, x = np.where(pixels[:, :image.width(), 3] > 8)
    if not len(x):
        return None
    return image.copy(int(x.min()), int(y.min()), int(x.max()-x.min()+1), int(y.max()-y.min()+1))

STAGE_MOODS = ('angry', 'heart', 'happy')
LASER_LENGTH = 170.
FIRE_OFFSET = 104.
FIRE_RAISE = 24.        # the fire hangs this far above the lens, never down at the ground
RISE_END = .16          # the lamp climbs first; the fire is spat here
SPIT_END = .30          # ... and has arced out to its hanging place by here
FIRE_HEIGHT = 66.
CHARGE_END = .16        # the beam leaves the lens here
BEAM_END = .86

BLUE = (46, 168, 255)
ICE = (168, 232, 255)
WHITE = (240, 250, 255)
VIOLET = (150, 90, 255)
MAGENTA = (212, 120, 255)
DEEP = (70, 40, 190)

PLUS = G.QPainter.CompositionMode_Plus
OVER = G.QPainter.CompositionMode_SourceOver


def _rgba(color, alpha):
    return G.QColor(color[0], color[1], color[2], max(0, min(255, int(alpha*255))))


def _smooth(value):
    x = max(0., min(1., value))
    return x*x*(3-2*x)


def _mix(a, b, u):
    u = max(0., min(1., u))
    return tuple(int(a[i]+(b[i]-a[i])*u) for i in range(3))


def _radial(p, centre, radius, stops, mode=PLUS):
    """Soft disc: `stops` is a list of (position, color, alpha)."""
    grad = G.QRadialGradient(C.QPointF(*centre), radius)
    for pos, color, alpha in stops:
        grad.setColorAt(pos, _rgba(color, alpha))
    p.save()
    p.setCompositionMode(mode)
    p.setPen(C.Qt.NoPen)
    p.setBrush(grad)
    p.drawEllipse(C.QPointF(*centre), radius, radius)
    p.restore()


def _spark(p, origin, angle, length, width, colour, alpha, droop=0., head=True):
    """A flying spark: bright at its head, tapering to nothing at the tail,
    bending down a little under its own weight."""
    ox, oy = origin
    dx, dy = math.cos(angle), math.sin(angle)
    nx, ny = -dy, dx
    mid = (ox+dx*length*.5+nx*droop*.5, oy+dy*length*.5+ny*droop*.5)
    tip = (ox+dx*length+nx*droop, oy+dy*length+ny*droop)
    path = G.QPainterPath()
    path.moveTo(ox+nx*width*.5, oy+ny*width*.5)
    path.quadTo(mid[0]+nx*width*.22, mid[1]+ny*width*.22, tip[0], tip[1])
    path.quadTo(mid[0]-nx*width*.22, mid[1]-ny*width*.22, ox-nx*width*.5, oy-ny*width*.5)
    path.closeSubpath()
    p.save()
    p.setCompositionMode(PLUS)
    p.setPen(C.Qt.NoPen)
    grad = G.QLinearGradient(ox, oy, tip[0], tip[1])
    grad.setColorAt(0, _rgba(WHITE, alpha))
    grad.setColorAt(.35, _rgba(colour, alpha*.85))
    grad.setColorAt(1, _rgba(colour, 0))
    p.setBrush(grad)
    p.drawPath(path)
    p.restore()
    if head:
        _radial(p, origin, width*1.6, [(0, WHITE, alpha), (.5, colour, alpha*.5), (1, colour, 0)])


def stage_rect(eye, ground, scale, side):
    """Global rectangle large enough for the beam fan and the fire, anchored
    on the ground point so it does not move while the lamp flies."""
    reach = (LASER_LENGTH+70)*scale
    left = ground[0]-reach
    right = ground[0]+reach
    top = ground[1]-480*scale
    bottom = ground[1]+(LASER_LENGTH+40)*scale
    return C.QRect(int(left), int(top), int(right-left)+1, int(bottom-top)+1)


def laser_angle(t, room_left, room_right):
    """Beam direction in screen degrees (90 = straight down) for progress t.

    One sweep out and back across the half-plane below the lamp, kept on the
    side of the screen that has room, with a fine tremor: it is being fired,
    not drawn with a ruler.
    """
    start = 162. if room_left else 100.
    end = 18. if room_right else 80.
    u = (t-CHARGE_END)/(BEAM_END-CHARGE_END)
    u = max(0., min(1., u))
    path = _smooth(u*2) if u < .5 else 1-_smooth((u-.5)*2)
    return start+(end-start)*path+1.4*math.sin(t*140)


def laser_strength(t):
    """0 while charging, 1 while firing, back to 0 at the end."""
    return _smooth((t-CHARGE_END)/.05)*(1-_smooth((t-BEAM_END)/.09))


def fire_position(t, eye, ground, scale, side):
    """Where the ghost fire is at progress t and how big it is (0..1).

    The lamp climbs first with the fire still inside (``rising``); at
    ``RISE_END`` it spits the fire, which arcs out and hangs beside the lamp a
    little above the lens, burns there and finally shrinks away. It never
    drops to the ground: that is where the settings panel opens, and a fire
    down there was hidden behind it. `eye` is the lens as it is now (already
    lifted), so the fire follows the lamp up.
    """
    direction = -1 if side == 'left' else 1
    hang = (eye[0]+direction*FIRE_OFFSET*scale, eye[1]-FIRE_RAISE*scale)
    if t < RISE_END:
        return eye, 0., 'rising'
    if t < SPIT_END:
        u = _smooth((t-RISE_END)/(SPIT_END-RISE_END))
        x = eye[0]+(hang[0]-eye[0])*u
        y = eye[1]+(hang[1]-eye[1])*u-40*scale*4*u*(1-u)
        return (x, y), .35+.25*u, 'flight'
    if t < .9:
        return hang, 1., 'burning'
    return hang, 1-_smooth((t-.9)/.1), 'dying'


# ── ghost fire ──────────────────────────────────────────────────
def _tongue(cx, base_y, height, width, sway, seconds, seed, nick):
    """A noisy flame silhouette: a teardrop whose edges ripple upward."""
    path = G.QPainterPath()
    left, right = [], []
    steps = 22
    for i in range(steps+1):
        v = i/steps                      # 0 base … 1 tip
        taper = math.sqrt(max(0., 1-v))*(1-.25*v)
        ripple = (math.sin(7.*v+9.*seconds+seed)+.5*math.sin(13.*v-15.*seconds+seed*1.7)
                  +.3*math.sin(21.*v+6.*seconds+seed*.6))/1.8
        w = width*(taper+.28*ripple*v*(1-v*.4))
        w = max(w, width*.04*(1-v))
        centre = cx+sway*v*v+width*.18*math.sin(5.*v+6.*seconds+seed)*v
        y = base_y-height*v+height*.05*nick*math.sin(9.*v+4.*seconds)
        left.append(C.QPointF(centre-w, y))
        right.append(C.QPointF(centre+w, y))
    tip = C.QPointF(cx+sway+width*.12*math.sin(11*seconds+seed), base_y-height*(1.02+.03*math.sin(17*seconds+seed)))
    path.moveTo(left[0])
    for q in left[1:]:
        path.lineTo(q)
    path.lineTo(tip)
    for q in reversed(right[1:]):
        path.lineTo(q)
    path.cubicTo(right[0].x(), base_y+width*.5, left[0].x(), base_y+width*.5, left[0].x(), left[0].y())
    return path


def _fill_tongue(p, path, base_y, height, bottom, top, alpha, mode=OVER):
    grad = G.QLinearGradient(0, base_y, 0, base_y-height)
    grad.setColorAt(0, _rgba(bottom, alpha))
    grad.setColorAt(.55, _rgba(_mix(bottom, top, .5), alpha))
    grad.setColorAt(1, _rgba(top, alpha*.85))
    p.save()
    p.setCompositionMode(mode)
    p.setPen(C.Qt.NoPen)
    p.setBrush(grad)
    p.drawPath(path)
    p.restore()


def paint_fire(p, seconds, position, size, phase, scale):
    x, y = position
    s = scale*size
    if phase == 'flight':
        # A comet: the ball with a fading tail of its last positions.
        for k in range(5):
            lag = k*.028
            tail = (x+lag*120*scale*(1 if k else 0)*math.copysign(1, 1), y+lag*60*scale)
            _radial(p, tail, (13-2*k)*s, [(0, WHITE, .6*(1-k/5)), (.5, ICE, .35*(1-k/5)), (1, VIOLET, 0)])
        _radial(p, (x, y), 22*s, [(0, WHITE, .95), (.3, ICE, .75), (.7, VIOLET, .3), (1, DEEP, 0)])
        for i in range(4):
            a = seconds*17+i*1.6
            sx, sy = x+math.cos(a)*14*s, y+math.sin(a)*14*s
            _radial(p, (sx, sy), 3*s, [(0, WHITE, .9), (1, MAGENTA, 0)])
        return
    flick = (math.sin(seconds*21)+math.sin(seconds*13.7+1.)*.6+math.sin(seconds*34.3+2.)*.3)/1.9
    sway = (math.sin(seconds*9.1)+math.sin(seconds*5.3+.7)*.5)/1.5
    H = FIRE_HEIGHT*s
    # Ground pool and the violet veil around the whole flame.
    pool = G.QRadialGradient(C.QPointF(x, y+2*s), 36*s)
    pool.setColorAt(0, _rgba(BLUE, .42))
    pool.setColorAt(.5, _rgba(VIOLET, .2))
    pool.setColorAt(1, _rgba(DEEP, 0))
    p.save(); p.setPen(C.Qt.NoPen); p.setBrush(pool)
    p.drawEllipse(C.QPointF(x, y+2*s), 36*s, 9*s); p.restore()
    _radial(p, (x, y-H*.4), H*1.15, [(0, VIOLET, .26*(1+.2*flick)), (.5, DEEP, .12), (1, DEEP, 0)])
    # Smoke: three violet wisps peeling off the tip and fading as they rise.
    for i in range(3):
        life = (seconds*.55+i*.33) % 1.
        sx = x+sway*10*s+(8+6*i)*s*math.sin(seconds*2.3+i*2.1)*(.3+life)
        sy = y-H*(.9+.9*life)
        r = (8+12*life)*s
        _radial(p, (sx, sy), r, [(0, VIOLET, .3*(1-life)*(1-life)), (.6, DEEP, .1*(1-life)), (1, DEEP, 0)])
    # Three nested tongues, violet outside, white inside.
    tongues = ((1., 1., DEEP, VIOLET, .5, 0., OVER), (.78, .7, BLUE, MAGENTA, .8, 1.3, OVER),
               (.56, .45, ICE, BLUE, .9, 2.6, OVER), (.34, .26, WHITE, ICE, .95, 3.9, PLUS))
    for k, (hk, wk, bottom, top, alpha, seed, mode) in enumerate(tongues):
        h = H*hk*(1+.15*flick*(1+k*.25))
        w = 22*s*wk*(1+.07*math.sin(seconds*17+k))
        path = _tongue(x, y, h, w, 9*s*sway*(1+k*.35), seconds, seed, .12*math.sin(seconds*25+k*2))
        _fill_tongue(p, path, y, h, bottom, top, alpha, mode)
    # The wisp's heart and two small side flames licking at the base.
    _radial(p, (x+2*s*sway, y-H*.26), 15*s, [(0, WHITE, .95), (.45, ICE, .5), (1, BLUE, 0)])
    for side in (-1, 1):
        h = H*.3*(1+.3*math.sin(seconds*19+side))
        path = _tongue(x+side*14*s, y+1*s, h, 7*s, side*3*s, seconds, 5+side, .2)
        _fill_tongue(p, path, y, h, VIOLET, MAGENTA, .55)
    # Embers: fixed phases, each with a short motion trail; blue near the
    # flame, violet as they cool.
    for i in range(10):
        life = (seconds*(.42+.09*(i % 4))+i*.23) % 1.
        ex = x+(8+5*(i % 3))*s*math.sin(seconds*3+i*1.7)*(.3+life)
        ey = y-H*(.25+1.1*life)
        colour = _mix(ICE, MAGENTA, life)
        r = (2.6-1.6*life)*s
        fade = (1-life)*math.sin(math.pi*min(1., life*4))*size
        p.save(); p.setCompositionMode(PLUS)
        p.setPen(G.QPen(_rgba(colour, .45*fade), r*1.2, C.Qt.SolidLine, C.Qt.RoundCap))
        p.drawLine(C.QPointF(ex, ey), C.QPointF(ex-1.5*s*math.sin(seconds*3+i*1.7), ey+6*s))
        p.restore()
        _radial(p, (ex, ey), r*2.2, [(0, WHITE, .9*fade), (.4, colour, .6*fade), (1, colour, 0)])


# ── laser ───────────────────────────────────────────────────────
def paint_laser(p, t, seconds, eye, scale, room_left, room_right):
    ex, ey = eye
    strength = laser_strength(t)
    charge = _smooth(t/CHARGE_END)
    alive = 1-_smooth((t-BEAM_END)/.1)
    # Charging sphere, fed by streaks converging on the lens.
    if t < CHARGE_END+.08:
        # Motes of light drawn in from all around, each a comet pointing at
        # the lens with its tail trailing outward.
        pull = min(1., charge*1.2)*(1-_smooth((t-CHARGE_END)/.08))
        for i in range(14):
            a = i*math.pi*2/14+seconds*1.1+.4*math.sin(i)
            cycle = (seconds*2.4+i*.13) % 1.
            dist = (70-62*cycle)*scale
            head = (ex+math.cos(a)*dist, ey+math.sin(a)*dist)
            _spark(p, head, a, (10+16*cycle)*scale, 2.2*scale, ICE if i % 3 else MAGENTA, .7*pull*(1-cycle*.5))
        ring = (40-30*charge)*scale
        p.save(); p.setCompositionMode(PLUS)
        p.setPen(G.QPen(_rgba(VIOLET, .5*charge), 2*scale)); p.setBrush(C.Qt.NoBrush)
        p.drawEllipse(C.QPointF(ex, ey), ring, ring); p.restore()
    sphere = (8+16*charge)*scale*(.6+.4*alive)*(1+.08*math.sin(seconds*50))
    _radial(p, (ex, ey), sphere*2.2, [(0, WHITE, .9*charge*alive), (.3, ICE, .55*charge*alive), (.7, VIOLET, .2*charge*alive), (1, DEEP, 0)])
    # Release: a shockwave ring and a flash.
    wave = (t-CHARGE_END)/.14
    if 0 < wave < 1:
        r = (12+90*_smooth(wave))*scale
        p.save(); p.setCompositionMode(PLUS); p.setBrush(C.Qt.NoBrush)
        for width, colour, a in ((6, VIOLET, .35), (2.5, ICE, .8)):
            p.setPen(G.QPen(_rgba(colour, a*(1-wave)), width*scale*(1-wave*.6)))
            p.drawEllipse(C.QPointF(ex, ey), r, r*.78)
        p.restore()
        _radial(p, (ex, ey), 60*scale*(1-wave), [(0, WHITE, .6*(1-wave)), (1, ICE, 0)])
    if strength <= 0:
        return
    shimmer = .88+.12*math.sin(seconds*60)
    length = LASER_LENGTH*scale*(1-.06*(1-alive))
    # Scorch marks: the impact point leaves glowing dots that cool off.
    for k in range(1, 9):
        lag = k*.032
        if t-lag <= CHARGE_END:
            break
        angle = math.radians(laser_angle(t-lag, room_left, room_right))
        mark = (ex+math.cos(angle)*length, ey+math.sin(angle)*length)
        cool = 1-k/9
        _radial(p, mark, (6+8*(1-cool))*scale, [(0, _mix(ICE, VIOLET, 1-cool), .5*cool*strength), (1, DEEP, 0)])
    # Afterglow: the last few directions fade behind the live beam.
    for lag, alpha in ((.05, .1), (.033, .2), (.016, .38), (0, 1.)):
        angle = math.radians(laser_angle(t-lag, room_left, room_right))
        dx, dy = math.cos(angle), math.sin(angle)
        tip = C.QPointF(ex+dx*length, ey+dy*length)
        start = C.QPointF(ex, ey)
        level = strength*alpha*shimmer
        p.save(); p.setCompositionMode(PLUS)
        for width, colour, a in ((30, DEEP, .16), (16, VIOLET, .3), (8, BLUE, .6), (3.2, ICE, .9), (1.4, WHITE, 1.)):
            p.setPen(G.QPen(_rgba(colour, a*level), width*scale, C.Qt.SolidLine, C.Qt.RoundCap))
            p.drawLine(start, tip)
        if lag == 0:
            # Chromatic fringe either side of the core, and energy dashes
            # streaming down the beam.
            nx, ny = -dy*4.2*scale, dx*4.2*scale
            for sign, colour in ((1, MAGENTA), (-1, ICE)):
                p.setPen(G.QPen(_rgba(colour, .45*level), 1.3*scale))
                p.drawLine(C.QPointF(ex+nx*sign, ey+ny*sign), C.QPointF(tip.x()+nx*sign, tip.y()+ny*sign))
            dash = G.QPen(_rgba(WHITE, .7*level), 2.2*scale, C.Qt.CustomDashLine, C.Qt.RoundCap)
            dash.setDashPattern([3., 9.])
            dash.setDashOffset(-seconds*38)
            p.setPen(dash)
            p.drawLine(start, tip)
        p.restore()
        if lag == 0:
            # Impact: flare, rings and sparks skittering off the surface.
            _radial(p, (tip.x(), tip.y()), 30*scale, [(0, WHITE, .95*level), (.35, ICE, .55*level), (.7, VIOLET, .25*level), (1, DEEP, 0)])
            p.save(); p.setCompositionMode(PLUS); p.setBrush(C.Qt.NoBrush)
            for i in range(2):
                ring = ((seconds*2.6+i*.5) % 1.)
                p.setPen(G.QPen(_rgba(ICE if i else MAGENTA, .6*(1-ring)*level), 1.6*scale))
                p.drawEllipse(tip, (6+22*ring)*scale, (4+14*ring)*scale)
            p.restore()
            # Sparks skittering off the surface: each lives a few frames,
            # flies out along its own line and droops as it slows.
            for i in range(11):
                life = (seconds*(3.2+.4*(i % 3))+i*.29) % 1.
                spark = angle+math.pi+math.radians(-85+17*i+12*math.sin(i*2.3+int(seconds*3)))
                reach = (10+26*(.5+.5*math.sin(i*1.9)))*scale*life
                origin = (tip.x()+math.cos(spark)*reach, tip.y()+math.sin(spark)*reach)
                colour = MAGENTA if i % 3 == 0 else ICE
                _spark(p, origin, spark, (6+14*(1-life))*scale, (1.2+1.6*(1-life))*scale, colour,
                       .95*level*(1-life*life), droop=3*scale*life*life)


def paint_stage(p, mood, t, seconds, eye, ground, scale, side, room_left, room_right):
    """Draw the mood's effect in global coordinates (the painter is already
    translated to the stage window)."""
    p.setRenderHint(G.QPainter.Antialiasing)
    if mood == 'angry':
        paint_laser(p, t, seconds, eye, scale, room_left, room_right)
    elif mood in ('heart', 'happy'):
        position, size, phase = fire_position(t, eye, ground, scale, side)
        if RISE_END <= t < RISE_END+.05:
            # Spitting it out: a small shockwave at the lens.
            wave = (t-RISE_END)/.05
            p.save(); p.setCompositionMode(PLUS); p.setBrush(C.Qt.NoBrush)
            p.setPen(G.QPen(_rgba(ICE, .7*(1-wave)), 2*scale))
            p.drawEllipse(C.QPointF(*eye), (8+30*wave)*scale, (6+22*wave)*scale)
            p.restore()
        if size > 0:
            paint_fire(p, seconds, position, size, phase, scale)


SYMBOL_ANCHOR = (396, 92)   # just above the right crystal cluster, canvas units


def paint_effects(p, mood, t, duration):
    """Symbols rising from the top-right corner of the lamp: '!' while it
    fires, '?' while puzzled, 'z' asleep. Drawn in canvas coordinates inside
    the body transform, so they tilt and fly with the lamp."""
    if mood not in ('angry', 'puzzled', 'sleep') or not 0 < t < 1:
        return
    image = artwork(mood)
    if image is None:
        return
    seconds = t*duration/1000
    ax, ay = SYMBOL_ANCHOR
    for i in range(2):
        age = (seconds-i*.45)/1.15
        if not 0 < age < 1:
            continue
        fade = min(1, age/.15)*(1-age)**.7*min(1, (1-t)/.12)
        p.save()
        p.translate(ax+(-18 if i else 14)+12*math.sin(age*4+i), ay-90*age)
        p.rotate((-13 if i % 2 else 11)+5*math.sin(age*5))
        p.scale(2.8, 2.8)
        p.setOpacity(p.opacity()*fade)
        size = image.size().scaled(32, 32, C.Qt.KeepAspectRatio)
        # A breath of light under the ink, pulsing with the age of the symbol.
        _radial(p, (0, -size.height()/2+6), size.height()*.8,
                [(0, ICE, .35+.15*math.sin(age*14)), (1, VIOLET, 0)])
        p.drawImage(C.QRectF(-size.width()/2, -size.height()+6, size.width(), size.height()), image)
        p.restore()


# ── details on the lamp itself ──────────────────────────────────
GLINTS = ((78, 70), (150, 118), (112, 160), (366, 92), (340, 160), (382, 200), (320, 320), (60, 150))


def paint_glints(p, seconds, period=3.):
    """Starry glints wandering over the ice; each fires once per period."""
    p.save()
    p.setCompositionMode(PLUS)
    for i, (gx, gy) in enumerate(GLINTS):
        phase = ((seconds/period)+i*.37) % 1.
        pulse = max(0., 1-abs(phase-.5)/.09)
        if pulse <= 0:
            continue
        size = (10+6*pulse)
        p.setPen(G.QPen(_rgba(WHITE, .85*pulse), 2.2, C.Qt.SolidLine, C.Qt.RoundCap))
        p.drawLine(C.QPointF(gx-size, gy), C.QPointF(gx+size, gy))
        p.drawLine(C.QPointF(gx, gy-size), C.QPointF(gx, gy+size))
        p.setPen(G.QPen(_rgba(ICE, .5*pulse), 1.2, C.Qt.SolidLine, C.Qt.RoundCap))
        p.drawLine(C.QPointF(gx-size*.45, gy-size*.45), C.QPointF(gx+size*.45, gy+size*.45))
        p.drawLine(C.QPointF(gx-size*.45, gy+size*.45), C.QPointF(gx+size*.45, gy-size*.45))
        _radial(p, (gx, gy), 9, [(0, WHITE, .7*pulse), (1, ICE, 0)])
    p.restore()


def paint_motes(p, seconds, glow, period=3.):
    """Frost motes drifting up around the lamp, brighter when it is."""
    p.save()
    p.setCompositionMode(PLUS)
    for i in range(9):
        life = ((seconds/period)*(1 if i % 3 else 2)+i*.11) % 1.
        mx = 90+300*((i*.618) % 1.)+18*math.sin(life*6.3+i)
        my = 430-380*life
        fade = math.sin(math.pi*life)*(.35+.4*glow)
        colour = (ICE, MAGENTA, WHITE)[i % 3]
        _radial(p, (mx, my), (3.5+1.5*(i % 2)), [(0, colour, .9*fade), (1, colour, 0)])
    p.restore()
