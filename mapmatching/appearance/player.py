from PySide6 import QtCore as C, QtGui as G
from .skins import doll

class PetAnimation:
    def __init__(self, button, skin=doll):
        self.skin = skin
        self.button = button
        self.pixmap = G.QPixmap(str(skin.IMAGE))
        self.layers = {}
        if not self.pixmap.isNull():
            for name, vertices in skin.PARTS.items():
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
        self.timer.setInterval(25)
        self.timer.timeout.connect(self.advance)

    def enable(self, enabled):
        self.enabled = bool(enabled and not self.pixmap.isNull())
        self.timer.stop()
        self.button.setFixedSize(112, 132) if self.enabled else self.button.setFixedSize(46, 46)
        self.button.update()

    def play(self, mood):
        if not self.enabled:
            return
        if self.timer.isActive() and self.mood == mood:
            return
        self.mood = mood
        self.clock.start()
        self.timer.start()
        self.button.update()

    def advance(self):
        if self.clock.elapsed() >= self.duration or not self.button.isVisible():
            self.timer.stop()
        self.button.update()

    @property
    def duration(self):
        return getattr(self.skin,'DURATIONS',{}).get(self.mood,2200)

    def paint(self, progress=None):
        p = G.QPainter(self.button)
        p.setRenderHints(G.QPainter.Antialiasing | G.QPainter.SmoothPixmapTransform)
        t = progress if progress is not None else (self.clock.elapsed()/self.duration if self.timer.isActive() else 1)
        angles, ease = self.skin.pose(self.mood, t)
        p.translate(1, 6)
        p.scale(.36, .36)
        motion = self.skin.body_motion(self.mood,t) if hasattr(self.skin,'body_motion') else dict(x=0,y=0,torso=0,squash=0)
        p.translate(motion['x'],motion['y'])
        p.translate(153,228)
        p.scale(1+motion['squash'],1-motion['squash'])
        p.translate(-153,-228)

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

        part('left_leg', self.skin.PIVOTS["left_leg"], angles['left_leg'])
        part('right_leg', self.skin.PIVOTS["right_leg"], angles['right_leg'])
        p.save()
        p.translate(153,228)
        p.rotate(motion['torso'])
        p.translate(-153,-228)
        p.drawPixmap(0, 0, self.layers['body'])
        part('head', self.skin.PIVOTS["head"], angles['head'])
        arm('left', self.skin.PIVOTS["left_shoulder"], self.skin.PIVOTS["left_elbow"])
        arm('right', self.skin.PIVOTS["right_shoulder"], self.skin.PIVOTS["right_elbow"])
        p.restore()
        if hasattr(self.skin,'paint_effects'):
            self.skin.paint_effects(p,self.mood,t,self.duration)
        p.end()
