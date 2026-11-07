"""The 磷焰矿灯 body: a lamp that hovers on its own light, settles onto two
legs to doze, hangs from its ring when carried, and keeps its light behind a
cracked lens.

Its two tricks leave the button: the laser it sweeps when something failed
(it climbs into the air to fire) and the ghost fire it spits when a map
lands. Both are drawn on :class:`EffectStage`, a click-through window laid
over the desktop around the lamp for just as long as the mood lasts.
"""
import sys
from PySide6 import QtCore as C, QtGui as G, QtWidgets as W
from .player import RigPlayer
from .skins import lantern


class EffectStage(W.QWidget):
    """Transparent, non-activating, input-transparent canvas over the desktop."""

    def __init__(self):
        super().__init__(None, C.Qt.Tool | C.Qt.FramelessWindowHint | C.Qt.WindowStaysOnTopHint |
                         C.Qt.WindowDoesNotAcceptFocus | C.Qt.WindowTransparentForInput)
        self.setAttribute(C.Qt.WA_TranslucentBackground)
        self.setAttribute(C.Qt.WA_ShowWithoutActivating)
        self.setAttribute(C.Qt.WA_TransparentForMouseEvents)
        if sys.platform == 'darwin':
            self.setAttribute(C.Qt.WA_MacAlwaysShowToolWindow)
        self.painter = None

    def paintEvent(self, event):
        if self.painter is None:
            return
        p = G.QPainter(self)
        try:
            self.painter(p)
        finally:
            p.end()


class LanternAnimation(RigPlayer):
    # Headroom above the lamp for hovering, climbing and flying up to fire.
    BASE_ORIGIN = (5, 40)
    BASE_SIZE = (112, 146)
    GAME_SIZE = (146, 190)
    RENDER_SCALE = .23
    WAITING_ANCHOR = (98, 34)
    NAME = lantern.NAME
    skin_id = 'lantern'

    def __init__(self, button, skin=lantern):
        super().__init__(button, skin)
        w, h = skin.CANVAS
        if not self.pixmap.isNull():
            for name, polygons in skin.PARTS.items():
                layer = G.QPixmap(w, h)
                layer.fill(C.Qt.transparent)
                painter = G.QPainter(layer)
                painter.setRenderHint(G.QPainter.Antialiasing)
                path = G.QPainterPath()
                for vertices in polygons:
                    piece = G.QPainterPath()
                    piece.addPolygon(G.QPolygonF([C.QPointF(*v) for v in vertices]))
                    piece.closeSubpath()
                    path = path.united(piece)
                painter.setClipPath(path)
                painter.drawPixmap(C.QRect(0, 0, w, h), self.pixmap)
                painter.end()
                self.layers[name] = layer
        self.stage = None
        self.stage_side = 'left'
        self.eye_point = None       # bright core, in the button's logical coordinates
        self.ground_point = None    # under the feet, same frame, without root motion
        # Hover height eases between moods, so dozing is a landing and waking
        # a lift-off rather than a jump.
        self.hover = skin.HOVER_DEFAULT
        self.hover_target = skin.HOVER_DEFAULT

    # ── modifiers ──────────────────────────────────────────────
    def _advance_modifiers(self):
        changed = super()._advance_modifiers()
        self.hover_target = self.skin.HOVER.get(self.mood, self.skin.HOVER_DEFAULT)
        before = round(self.hover, 1)
        self.hover += (self.hover_target-self.hover)*.14
        if abs(self.hover-self.hover_target) < .2:
            self.hover = self.hover_target
        return changed or round(self.hover, 1) != before

    @property
    def modified(self):
        return super().modified or self.hover != self.hover_target

    def play(self, mood):
        super().play(mood)
        self.hover_target = self.skin.HOVER.get(self.mood, self.skin.HOVER_DEFAULT)

    # ── stage ──────────────────────────────────────────────────
    def stage_active(self):
        mood = self.mood
        if not (self.enabled and self.timer.isActive() and mood in self.skin.STAGE_MOODS):
            return False
        if not self.button.isVisible() or self.dragging:
            return False
        # The stage stays up with the settings panel open: a click opens the
        # panel and starts the fire together, and the fire now hangs above
        # the lamp while the beam fades out below it, so neither covers the
        # settings being read.
        return 0 < self.clock.elapsed() < self.duration

    def _after_advance(self):
        if not self.stage_active():
            if self.stage is not None and self.stage.isVisible():
                self.stage.hide()
            return
        if self.stage is None:
            self.stage = EffectStage()
            self.stage.painter = self._paint_stage
        eye, ground = self._anchors()
        area = self._screen_area(eye)
        scale = self.scale
        reach = (self.skin.effects.FIRE_OFFSET+40)*scale
        # The fire lands away from the speech bubble, unless that is off-screen.
        side = 'left' if self.look > 0 else 'right' if self.look < 0 else 'left'
        if side == 'left' and eye[0]-reach < area.left():
            side = 'right'
        elif side == 'right' and eye[0]+reach > area.right():
            side = 'left'
        self.stage_side = side
        rect = self.skin.stage_rect(eye, ground, scale, side)
        if self.stage.geometry() != rect:
            self.stage.setGeometry(rect)
        if not self.stage.isVisible():
            self.stage.show()
            if sys.platform == 'darwin':
                # Qt reapplies its own window level on every show there.
                try:
                    from ..src import macos as native
                    native.keep_floating(int(self.stage.winId()))
                except Exception:
                    pass
        self.stage.update()

    def _anchors(self):
        """Global positions of the bright core and the ground under the feet."""
        rs = self.render_scale
        origin = self.origin_for(self.button.width(), self.button.height())
        eye = self.eye_point or (origin[0]+self.skin.CORE[0]*rs, origin[1]+self.skin.CORE[1]*rs)
        ground = self.ground_point or (origin[0]+250*rs, origin[1]+self.skin.GROUND_Y*rs)
        base = self.button.mapToGlobal(C.QPoint(0, 0))
        return (base.x()+eye[0], base.y()+eye[1]), (base.x()+ground[0], base.y()+ground[1])

    def _screen_area(self, point):
        screen = W.QApplication.screenAt(C.QPoint(int(point[0]), int(point[1]))) or W.QApplication.primaryScreen()
        return screen.availableGeometry() if screen is not None else C.QRect(0, 0, 10**6, 10**6)

    def _paint_stage(self, p):
        if not self.stage_active():
            return
        eye, ground = self._anchors()
        area = self._screen_area(eye)
        laser_reach = (self.skin.effects.LASER_LENGTH+20)*self.scale
        room_left = eye[0]-laser_reach >= area.left()
        room_right = eye[0]+laser_reach <= area.right()
        t = self.clock.elapsed()/self.duration
        p.translate(-self.stage.x(), -self.stage.y())
        if self.opacity < 1.:
            p.setOpacity(self.opacity)
        self.skin.paint_stage(p, self.mood, t, t*self.duration/1000, eye, ground, self.scale,
                              self.stage_side, room_left, room_right)
        if self.mood == 'angry':
            # The beam and its sparks sweep across the map below the lamp:
            # thin them out towards the bottom of the stage so what is being
            # read stays legible. Alpha only, so the colours are untouched.
            stage = self.stage.geometry()
            top = eye[1]+24*self.scale
            fade = G.QLinearGradient(0, top, 0, stage.bottom())
            fade.setColorAt(0, G.QColor(0, 0, 0, 255))
            fade.setColorAt(.4, G.QColor(0, 0, 0, 140))
            fade.setColorAt(1, G.QColor(0, 0, 0, 40))
            p.save()
            p.setOpacity(1.)
            p.setCompositionMode(G.QPainter.CompositionMode_DestinationIn)
            p.fillRect(C.QRectF(stage.left(), top, stage.width(), stage.bottom()-top), fade)
            p.restore()

    # ── painting ───────────────────────────────────────────────
    def _paint_on(self, device, t, render_scale=.23, origin=(5, 26)):
        skin = self.skin
        p = G.QPainter(device)
        p.setRenderHints(G.QPainter.Antialiasing | G.QPainter.SmoothPixmapTransform)
        if self.opacity < 1.:
            p.setOpacity(self.opacity)
        a, ease = skin.pose(self.mood, t)
        if self.mood == 'curious' and not self.wave_right:
            a['scan'] *= -1
            a['tilt'] *= -1
        motion = dict(skin.body_motion(self.mood, t))
        if self.blending:
            blend = min(1., self.since_play.elapsed()/400)
            a = {k: v*blend for k, v in a.items()}
            motion = {k: v*blend for k, v in motion.items()}
        lift = self.drag_lift
        lean = self.drag_lean
        swing = self.drag_swing
        # Runtime modifiers: a glance follows the bubble or the cursor; carried
        # by the ring the lamp swings and its legs dangle.
        a['scan'] += self.look_current/14*.7
        a['tilt'] += self.look_current*.12+lean*.5*(1-lift)
        a['left_leg'] += -7*lift+swing*.3
        a['right_leg'] += 7*lift+swing*.3
        a['chain'] -= swing*.9
        a['handle'] *= 1-lift
        motion['y'] -= 8*lift+self.hover
        glow = max(.05, min(2., 1+a['glow']))
        seconds = t*self.duration/1000

        p.translate(*origin)
        p.scale(render_scale, render_scale)
        ground = p.transform().map(C.QPointF(250, skin.GROUND_Y))
        self.ground_point = (ground.x(), ground.y())
        height = max(0., -motion['y'])
        if self.shadow:
            # The lamp lights the ground it floats over: a pool of its own
            # light, plus a faint contact shadow that fades with height.
            air = min(1., height/110)
            air = max(air, lift)
            cx, cy = skin.SHADOW['center']
            rx, ry = skin.SHADOW['radii']
            p.save()
            p.setPen(C.Qt.NoPen)
            p.setBrush(G.QColor(0, 0, 0, int(34*(1-air*.9))))
            p.drawEllipse(C.QPointF(cx+motion['x']*.4, cy), rx*(1-air*.4), ry*(1-air*.4))
            pool = G.QRadialGradient(C.QPointF(cx+motion['x']*.5, cy), rx*1.25)
            strength = glow*(1-air*.75)*(1-.6*(a['blink'] > .5))
            pool.setColorAt(0, G.QColor(140, 215, 255, int(255*.3*strength)))
            pool.setColorAt(.55, G.QColor(90, 120, 255, int(255*.12*strength)))
            pool.setColorAt(1, G.QColor(80, 60, 200, 0))
            p.setBrush(pool)
            p.drawEllipse(C.QPointF(cx+motion['x']*.5, cy), rx*1.25, ry*1.6)
            p.restore()
        skin.paint_motes(p, seconds, glow, period=self.duration/1000)
        p.translate(motion['x'], motion['y'])
        if lift > 0:
            ring = skin.PIVOTS['ring']
            p.translate(*ring)
            p.rotate(lean*1.4*lift)
            p.translate(-ring[0], -ring[1])
        base = skin.PIVOTS['base']
        p.translate(*base)
        p.scale(1+motion['squash'], 1-motion['squash'])
        p.rotate(a['tilt']+motion['torso'])
        p.translate(-base[0], -base[1])

        def part(name, angle):
            pivot = skin.PIVOTS[name]
            p.save()
            p.translate(*pivot)
            p.rotate(angle)
            p.translate(-pivot[0], -pivot[1])
            p.drawPixmap(0, 0, self.layers[name])
            p.restore()

        part('chain', a['chain'])
        part('left_crystal', a['left_crystal'])
        part('right_crystal', a['right_crystal'])
        part('left_leg', a['left_leg'])
        part('right_leg', a['right_leg'])
        p.drawPixmap(0, 0, self.layers['body'])
        self._paint_light(p, a, glow)
        part('handle', a['handle'])
        skin.paint_glints(p, seconds, period=self.duration/1000)
        # Symbols rise from the lamp's own top-right corner and travel with it.
        skin.paint_effects(p, self.mood, t, self.duration)
        p.end()

    def _paint_light(self, p, a, glow):
        """The light behind the glass: brightness, a glance, a blink, a squint."""
        skin = self.skin
        cx, cy = skin.LENS['center']
        rx, ry = skin.LENS['radii']
        core = C.QPointF(skin.CORE[0]+a['scan']*22, skin.CORE[1])
        eye = p.transform().map(core)
        self.eye_point = (eye.x(), eye.y())
        lens = G.QPainterPath()
        lens.addEllipse(C.QPointF(cx, cy), rx, ry)
        p.save()
        p.setPen(C.Qt.NoPen)
        # Haze spilling onto the frost around the lens, violet at the rim.
        halo = G.QRadialGradient(core, 130)
        halo.setColorAt(0, G.QColor(120, 205, 255, int(255*min(1., .10+.22*max(0., glow-1)))))
        halo.setColorAt(.6, G.QColor(110, 90, 255, int(255*min(1., .05+.1*max(0., glow-1)))))
        halo.setColorAt(1, G.QColor(90, 60, 220, 0))
        p.setBrush(halo)
        p.drawEllipse(core, 130, 130)
        p.setClipPath(lens)
        if glow > 1:
            p.setCompositionMode(G.QPainter.CompositionMode_Plus)
            light = G.QRadialGradient(core, 86)
            boost = glow-1
            light.setColorAt(0, G.QColor(255, 255, 255, int(255*min(1., .55*boost))))
            light.setColorAt(.4, G.QColor(170, 235, 255, int(255*min(1., .35*boost))))
            light.setColorAt(1, G.QColor(60, 160, 255, 0))
            p.setBrush(light)
            p.drawEllipse(core, 86, 86)
            p.setCompositionMode(G.QPainter.CompositionMode_SourceOver)
        elif glow < 1:
            p.setBrush(G.QColor(8, 18, 30, int(255*.78*(1-glow))))
            p.drawPath(lens)
        if a['scan']:
            # The bright core moved: a soft spot where it now sits, and a
            # faint scan line while matching.
            spot = G.QRadialGradient(core, 48)
            spot.setColorAt(0, G.QColor(235, 250, 255, int(255*.5*min(1., abs(a['scan'])))))
            spot.setColorAt(1, G.QColor(170, 235, 255, 0))
            p.setBrush(spot)
            p.drawEllipse(core, 48, 48)
            if self.mood == 'matching':
                p.setBrush(G.QColor(220, 248, 255, 70))
                p.drawRect(C.QRectF(core.x()-2.5, cy-ry, 5, 2*ry))
        if a['squint'] > 0:
            # Lids closing to a slit; the upper one knits down in the middle.
            dark = G.QColor(10, 18, 28, int(255*.92*a['squint']))
            p.setBrush(dark)
            gap = 11+28*(1-a['squint'])
            brow = G.QPolygonF([C.QPointF(cx-rx-2, cy-ry-2), C.QPointF(cx+rx+2, cy-ry-2),
                                C.QPointF(cx+rx+2, cy-gap-9), C.QPointF(cx, cy-gap+5), C.QPointF(cx-rx-2, cy-gap-9)])
            p.drawPolygon(brow)
            p.drawRect(C.QRectF(cx-rx-2, cy+gap, 2*rx+4, ry-gap+2))
            # The slit itself burns hotter while it fires.
            p.setCompositionMode(G.QPainter.CompositionMode_Plus)
            slit = G.QLinearGradient(cx-rx, 0, cx+rx, 0)
            slit.setColorAt(0, G.QColor(150, 90, 255, 0))
            slit.setColorAt(.5, G.QColor(230, 250, 255, int(255*.6*a['squint'])))
            slit.setColorAt(1, G.QColor(150, 90, 255, 0))
            p.setBrush(slit)
            p.drawRect(C.QRectF(cx-rx, cy-gap+5, 2*rx, 2*gap-5))
            p.setCompositionMode(G.QPainter.CompositionMode_SourceOver)
        if a['blink'] > 0:
            p.setBrush(G.QColor(10, 18, 28, int(255*.92*min(1., a['blink']))))
            p.drawPath(lens)
        p.restore()
