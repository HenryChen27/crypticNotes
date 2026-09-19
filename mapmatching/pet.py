"""Optional, event-driven mascot presentation; no capture or matching dependencies."""
import math
from PySide6 import QtCore as C, QtGui as G, QtWidgets as W


# Polygons in the original 306 × 332 logo coordinates. Slight overlaps at
# joints keep seams covered. These are runtime sprite masks, not altered assets.
PARTS = {
    'head': [(75,0),(238,0),(238,132),(182,140),(120,137),(75,117)],
    'body': [(132,130),(177,130),(186,183),(184,219),(178,240),(132,242),(112,220),(115,182)],
    'left_upper': [(130,137),(140,145),(119,184),(107,197),(95,185)],
    'left_lower': [(105,174),(120,183),(105,213),(84,228),(72,215),(87,193)],
    'right_upper': [(176,138),(184,140),(205,182),(195,195),(183,176)],
    'right_lower': [(197,173),(211,195),(229,221),(226,240),(213,240),(196,216),(187,188)],
    'left_leg': [(109,210),(130,225),(124,252),(142,316),(116,320),(98,275),(97,239)],
    'right_leg': [(180,210),(195,219),(190,267),(173,317),(149,319),(153,288),(171,243)],
}


def pose(mood, progress):
    """Joint angles with ease-in/hold/ease-out, always returning to rest."""
    t = max(0., min(1., progress))
    ramp = min(1., t/.22, (1-t)/.25)
    ease = ramp*ramp*(3-2*ramp)
    flutter = math.sin(t*math.pi*12)*ease
    angles = dict(head=0., left_upper=0., left_lower=0.,
                  right_upper=0., right_lower=0., left_leg=0., right_leg=0.)
    if mood == 'heart':
        angles.update(head=-7*ease, left_upper=-57*ease, left_lower=-92*ease,
                      right_upper=50*ease, right_lower=102*ease,
                      left_leg=-4*ease, right_leg=4*ease)
    elif mood == 'puzzled':
        angles.update(head=-10*ease, right_upper=-137*ease,
                      right_lower=-30*ease+7*flutter, left_upper=8*ease)
    elif mood == 'sleep':
        angles.update(head=12*ease, left_upper=-8*ease, right_upper=8*ease)
    else:
        angles.update(head=7*ease, left_upper=110*ease,
                      left_lower=35*ease+12*flutter, right_leg=-5*ease)
    return angles, ease


class SpeechBubble(W.QLabel):
    """Non-activating, click-through speech with a tail aimed at the mascot."""
    def __init__(self):
        super().__init__('', None, C.Qt.Tool | C.Qt.FramelessWindowHint |
                         C.Qt.WindowStaysOnTopHint | C.Qt.WindowDoesNotAcceptFocus |
                         C.Qt.WindowTransparentForInput)
        self.setAttribute(C.Qt.WA_TranslucentBackground)
        self.setAttribute(C.Qt.WA_ShowWithoutActivating)
        self.setTextFormat(C.Qt.PlainText)
        self.setContentsMargins(19, 12, 19, 12)
        self.tail = 'right'
        self.tail_y = 22
        self.setStyleSheet('color:#dbe5ec;background:transparent;border:0;font-size:13px;')

    def point_at(self, point, enabled=True):
        self.tail = ('left' if point.x() < self.x() else 'right') if enabled else None
        self.tail_y = max(15, min(self.height()-15, point.y()-self.y()))
        self.update()

    def paintEvent(self, event):
        p = G.QPainter(self)
        p.setRenderHint(G.QPainter.Antialiasing)
        rect = C.QRectF(8, 1, self.width()-17, self.height()-2)
        path = G.QPainterPath()
        path.addRoundedRect(rect, 11, 11)
        if self.tail:
            triangle = G.QPainterPath()
            x = rect.left() if self.tail == 'left' else rect.right()
            tip = 1 if self.tail == 'left' else self.width()-2
            triangle.moveTo(x, self.tail_y-6)
            triangle.lineTo(tip, self.tail_y)
            triangle.lineTo(x, self.tail_y+6)
            triangle.closeSubpath()
            path = path.united(triangle)
        gradient = G.QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, G.QColor(45,61,73,248))
        gradient.setColorAt(1, G.QColor(22,33,43,248))
        p.setBrush(gradient)
        p.setPen(G.QPen(G.QColor(153,177,190,150), 1))
        p.drawPath(path)
        p.end()
        super().paintEvent(event)


def reaction(message):
    if any(word in message for word in ('失败', '无法', '冲突', '中断', '退出，请', '未匹配', '不足')):
        return 'puzzled'
    if any(word in message for word in ('隐藏', '关闭')):
        return 'sleep'
    if any(word in message for word in ('成功', '已录入', '已更新', '楼', '层')):
        return 'heart'
    return 'curious'


class PetAnimation:
    def __init__(self, button, logo):
        self.button = button
        self.pixmap = G.QPixmap(str(logo))
        self.layers = {}
        if not self.pixmap.isNull():
            for name, vertices in PARTS.items():
                layer = G.QPixmap(306, 332)
                layer.fill(C.Qt.transparent)
                painter = G.QPainter(layer)
                painter.setRenderHint(G.QPainter.Antialiasing)
                path = G.QPainterPath()
                path.addPolygon(G.QPolygonF([C.QPointF(*v) for v in vertices]))
                painter.setClipPath(path)
                painter.drawPixmap(C.QRect(0,0,306,332), self.pixmap)
                painter.end()
                self.layers[name] = layer
        self.enabled = False
        self.mood = 'curious'
        self.clock = C.QElapsedTimer()
        self.timer = C.QTimer(button)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.advance)

    def enable(self, enabled):
        self.enabled = bool(enabled and not self.pixmap.isNull())
        self.timer.stop()
        self.button.setFixedSize(112, 132) if self.enabled else self.button.setFixedSize(46, 46)
        self.button.update()

    def play(self, mood):
        if not self.enabled:
            return
        self.mood = mood
        self.clock.start()
        self.timer.start()
        self.button.update()

    def advance(self):
        if self.clock.elapsed() >= 2200 or not self.button.isVisible():
            self.timer.stop()
        self.button.update()

    def paint(self, progress=None):
        p = G.QPainter(self.button)
        p.setRenderHints(G.QPainter.Antialiasing | G.QPainter.SmoothPixmapTransform)
        t = progress if progress is not None else (self.clock.elapsed()/2200 if self.timer.isActive() else 1)
        angles, ease = pose(self.mood, t)
        p.translate(1, 6 - 3*ease if self.mood == 'heart' else 6)
        p.scale(.36, .36)

        def part(name, pivot, angle):
            p.save()
            p.translate(*pivot)
            p.rotate(angle)
            p.translate(-pivot[0], -pivot[1])
            p.drawPixmap(0, 0, self.layers[name])
            p.restore()

        def arm(side, shoulder, elbow):
            # Elbow inherits the shoulder transform: a genuine two-bone chain.
            p.save()
            p.translate(*shoulder)
            p.rotate(angles[side+'_upper'])
            p.translate(-shoulder[0], -shoulder[1])
            p.drawPixmap(0, 0, self.layers[side+'_upper'])
            part(side+'_lower', elbow, angles[side+'_lower'])
            p.restore()

        part('left_leg', (119,228), angles['left_leg'])
        part('right_leg', (182,228), angles['right_leg'])
        p.drawPixmap(0, 0, self.layers['body'])
        part('head', (153,134), angles['head'])
        arm('left', (132,145), (108,184))
        arm('right', (179,146), (197,186))
        if ease > 0:
            p.resetTransform()
            p.setPen(G.QColor('#e9d2c8' if self.mood == 'heart' else '#d2e1e8'))
            font = G.QFont('Segoe UI Symbol', 19)
            p.setFont(font)
            mark = {'heart': '♥', 'puzzled': '?', 'sleep': 'z', 'curious': '♪'}[self.mood]
            p.setOpacity(ease)
            p.drawText(C.QRectF(82, 2, 27, 30), C.Qt.AlignCenter, mark)
        p.end()
