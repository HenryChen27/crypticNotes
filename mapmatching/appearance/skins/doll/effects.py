"""Deterministic hand-drawn strokes; no font glyphs or per-frame randomness."""
import math
from pathlib import Path
from functools import lru_cache
import numpy as np
from PySide6 import QtCore as C, QtGui as G


@lru_cache(maxsize=4)
def artwork(kind):
    names={'heart':'heart.png','angry':'!.png','puzzled':'question.png','sleep':'z.png'}
    if kind not in names:
        return None
    image=G.QImage(str(Path(__file__).with_name(names[kind])))
    if image.isNull():
        return None
    image=image.convertToFormat(G.QImage.Format_RGBA8888)
    pixels=np.frombuffer(image.constBits(),np.uint8).reshape(image.height(),image.bytesPerLine()//4,4)
    y,x=np.where(pixels[:,:image.width(),3]>8)
    if not len(x):
        return None
    return image.copy(int(x.min()),int(y.min()),int(x.max()-x.min()+1),int(y.max()-y.min()+1))


def symbol(kind):
    path=G.QPainterPath()
    if kind=='heart':
        path.moveTo(0,5)
        path.cubicTo(-5,0,-12,-4,-13,-12)
        path.cubicTo(-15,-24,-6,-24,-3,-15)
        path.lineTo(0,-7)
        path.cubicTo(3,-18,7,-23,11,-21)
        path.cubicTo(19,-18,9,-5,0,5)
        path.closeSubpath()
    elif kind=='angry':
        path.moveTo(-1,-15);path.lineTo(1,-6);path.lineTo(0,-2)
        path.moveTo(0,4);path.lineTo(1,5)
    elif kind=='puzzled':
        path.moveTo(-7,-11);path.cubicTo(-5,-21,12,-18,6,-8)
        path.cubicTo(3,-4,-2,-5,-1,0)
        path.moveTo(-1,5);path.lineTo(0,6)
    elif kind=='sleep':
        path.moveTo(-7,-12);path.lineTo(5,-14);path.lineTo(-4,0);path.lineTo(8,-2)
    else:
        path.moveTo(-5,1);path.lineTo(-4,-14);path.lineTo(5,-17);path.lineTo(6,-1)
        path.addEllipse(C.QRectF(-11,-2,6,4));path.addEllipse(C.QRectF(0,-4,6,4))
    return path


def paint_effects(p,mood,t,duration):
    if mood == 'curious' or not 0<t<1:
        return
    p.save();p.resetTransform()
    heart=mood in ('heart','happy')
    seconds=t*duration/1000
    # Staggered births: several hearts can coexist and fade independently.
    for i in range(9 if heart else 2):
        age=(seconds-i*(.31 if heart else .45))/(.95 if heart else 1.15)
        if not 0<age<1:
            continue
        fade=min(1,age/.15)*(1-age)**.7*min(1,(1-t)/.12)
        p.save()
        p.translate((87 if i%2==0 else 22)+3*math.sin(age*4+i),36-24*age)
        p.rotate((-13 if i%2 else 11)+5*math.sin(age*5))
        scale=(.55+.25*math.sin(math.pi*age)) if heart else .7
        p.scale(scale,scale);p.setOpacity(fade)
        image=artwork('heart' if heart else mood)
        if image is not None:
            size=image.size().scaled(32,32,C.Qt.KeepAspectRatio)
            p.drawImage(C.QRectF(-size.width()/2,-size.height()+6,size.width(),size.height()),image)
            p.restore()
            continue
        path=symbol('heart' if heart else mood)
        if heart:
            p.setBrush(G.QColor('#b70c23'))
            p.setPen(G.QPen(G.QColor('#b70c23'),1.7,C.Qt.SolidLine,C.Qt.RoundCap,C.Qt.RoundJoin))
            p.drawPath(path)
            # Uneven looping pen strokes extend outside the filled lobes.
            scribble=G.QPainterPath()
            scribble.moveTo(0,6)
            scribble.cubicTo(-15,-3,-21,-25,-12,-21)
            scribble.cubicTo(-8,-23,-4,-10,0,2)
            scribble.cubicTo(5,-9,17,-26,17,-18)
            scribble.cubicTo(14,-8,4,-1,-1,7)
            p.setBrush(C.Qt.NoBrush)
            p.setPen(G.QPen(G.QColor('#a40920'),1.8,C.Qt.SolidLine,C.Qt.RoundCap,C.Qt.RoundJoin))
            p.drawPath(scribble)
            p.restore()
            continue
        p.setBrush(C.Qt.NoBrush)
        for offset,color,width in [(0,'#e43d48' if heart else '#dfdce1',2.5),(.8,'#932a3c' if heart else '#8299a9',.8)]:
            p.setPen(G.QPen(G.QColor(color),width,C.Qt.SolidLine,C.Qt.RoundCap,C.Qt.RoundJoin))
            p.drawPath(path.translated(offset,-offset*.6))
        p.restore()
    p.restore()
