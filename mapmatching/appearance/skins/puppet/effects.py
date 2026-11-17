"""What the 守财木偶 shows instead of saying: whistled notes while it sneaks
and plays innocent, sweat while it runs, stars while it lies there, tears
once its sack has been emptied. All of it is a function of the seconds a mood
has been playing, drawn in canvas units inside the body's transform.
"""
import math
from PySide6 import QtCore as C, QtGui as G
from . import rig

INK = G.QColor(246, 240, 226)
INK_EDGE = G.QColor(40, 32, 28, 210)
TEAR = G.QColor(120, 200, 255)
STAR = G.QColor(255, 222, 110)


def note_path(double=False):
    """A hand-sized quaver (or a beamed pair), about 40 canvas px tall."""
    path = G.QPainterPath()
    path.addEllipse(C.QRectF(-12, -6, 16, 12))
    path.addRect(C.QRectF(2, -40, 3.5, 40))
    if double:
        path.addEllipse(C.QRectF(12, -12, 16, 12))
        path.addRect(C.QRectF(26, -46, 3.5, 40))
        beam = G.QPolygonF([C.QPointF(2, -40), C.QPointF(29.5, -46), C.QPointF(29.5, -37), C.QPointF(2, -31)])
        path.addPolygon(beam)
    else:
        flag = G.QPainterPath(C.QPointF(5.5, -40))
        flag.cubicTo(20, -34, 20, -22, 12, -14)
        flag.cubicTo(16, -24, 12, -30, 5.5, -31)
        path.addPath(flag)
    path.setFillRule(C.Qt.WindingFill)
    return path


def star_path(radius=10.):
    path = G.QPainterPath()
    for i in range(10):
        r = radius if i % 2 == 0 else radius*.42
        angle = -math.pi/2+i*math.pi/5
        point = C.QPointF(r*math.cos(angle), r*math.sin(angle))
        path.lineTo(point) if i else path.moveTo(point)
    path.closeSubpath()
    return path


def drop_path(size=9.):
    path = G.QPainterPath(C.QPointF(0, -size*1.5))
    path.cubicTo(size*.2, -size*.6, size, 0, size*.7, size*.55)
    path.cubicTo(size*.4, size, -size*.4, size, -size*.7, size*.55)
    path.cubicTo(-size, 0, -size*.2, -size*.6, 0, -size*1.5)
    return path


_NOTE, _NOTES, _STAR, _DROP = note_path(), note_path(True), star_path(), drop_path()


def _inked(p, path, fill, alpha):
    p.setOpacity(alpha)
    p.setPen(G.QPen(INK_EDGE, 3.2, C.Qt.SolidLine, C.Qt.RoundCap, C.Qt.RoundJoin))
    p.setBrush(fill)
    p.drawPath(path)


def paint_notes(p, seconds, count=3, gap=.7, life=1.6, origin=rig.MOUTH):
    """Whistled notes drifting up and forward from the mouth."""
    base = p.opacity()
    for i in range(count):
        age = ((seconds-i*gap) % (count*gap))/life
        if not 0 < age < 1 or seconds < i*gap:
            continue
        p.save()
        p.translate(origin[0]-26-70*age+10*math.sin(age*7+i), origin[1]-14-120*age)
        p.rotate(-12+16*math.sin(age*5+i*2))
        size = .9+.35*age
        p.scale(size, size)
        _inked(p, _NOTES if i % 2 else _NOTE, INK, base*min(1., age/.15)*(1-age)**.8)
        p.restore()
    p.setOpacity(base)


TEAR_PERIOD = .95        # seconds from welling up to hitting the ground


def tear_position(age, side, stream=1.):
    """Where a tear is, `age` 0..1 through its fall: thrown up and out from
    the eye, then down along a parabola to the ground."""
    ex, ey = rig.EYE
    return (ex+14+side*(22+64*age)*stream, ey+12-76*age+(rig.GROUND_Y-ey-12+76)*age*age)


def paint_tears(p, seconds, stream=1.):
    """One big tear at a time, left eye then right: the next one only wells
    up once the last has hit the ground."""
    base = p.opacity()
    index = int(seconds/TEAR_PERIOD)
    age = seconds/TEAR_PERIOD-index
    side = -1 if index % 2 else 1
    x, y = tear_position(age, side, stream)
    ahead = tear_position(min(1., age+.02), side, stream)
    p.save()
    p.translate(x, y)
    # The point of the drop trails behind it along the path.
    p.rotate(math.degrees(math.atan2(y-ahead[1], x-ahead[0]))+90)
    size = 1.5*min(1., .35+age*4)
    p.scale(size, size)
    p.setOpacity(base*min(1., age/.08)*min(1., (1-age)/.06))
    p.setPen(G.QPen(G.QColor(30, 80, 130, 190), 2.4))
    p.setBrush(TEAR)
    p.drawPath(_DROP)
    p.restore()
    if age > .9:
        # ... and a small splash where it lands.
        spread = (age-.9)/.1
        p.setOpacity(base*(1-spread))
        p.setPen(G.QPen(TEAR, 3.))
        p.setBrush(C.Qt.NoBrush)
        gx, gy = tear_position(1., side, stream)
        p.drawArc(C.QRectF(gx-16*spread, gy-7*spread, 32*spread, 14*spread), 0, 180*16)
    p.setOpacity(base)


def paint_sweat(p, seconds):
    """Beads flying off behind the head while it runs."""
    base = p.opacity()
    hx, hy = rig.HAT_TIP
    for i in range(3):
        age = ((seconds*2.2+i/3.) % 1.)
        p.save()
        p.translate(hx+10+46*age+i*14, hy+26-70*age-i*10)
        p.rotate(24)
        p.scale(.8, .8)
        p.setOpacity(base*(1-age))
        p.setPen(G.QPen(G.QColor(30, 80, 130, 170), 2.2))
        p.setBrush(G.QColor(190, 228, 255))
        p.drawPath(_DROP)
        p.restore()
    p.setOpacity(base)


def paint_stars(p, seconds):
    """Three stars circling the head of a puppet that just went down."""
    base = p.opacity()
    hx, hy = 0., 0.
    for i in range(3):
        angle = seconds*4.2+i*math.tau/3
        depth = math.sin(angle)
        p.save()
        p.translate(hx+62*math.cos(angle), hy+16*depth)
        p.rotate(seconds*200+i*40)
        size = 1.15+.3*depth
        p.scale(size, size)
        _inked(p, _STAR, STAR, base*(.65+.35*depth))
        p.restore()
    p.setOpacity(base)


def paint_extras(p, mood, seconds):
    """Everything that floats around the body for the mood being played."""
    if mood == 'freeze':
        paint_notes(p, seconds)
    elif mood == 'sneak':
        paint_notes(p, seconds)
    elif mood == 'run':
        paint_sweat(p, seconds)
    elif mood in ('cry', 'hit'):
        paint_tears(p, seconds)
    elif mood == 'sulk':
        paint_tears(p, seconds, stream=.55)
    elif mood == 'matching':
        paint_notes(p, seconds, count=2, gap=1.5, life=1.4)
