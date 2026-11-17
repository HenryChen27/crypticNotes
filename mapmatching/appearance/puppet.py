"""The 守财木偶 body: a jointed wooden thief carrying a sack.

Two things set it apart from the other bodies. It can turn round (``facing``)
because it walks and runs across the desktop during its game, and its sack can
come off (``has_sack``), which reveals the far arm and the repainted shirt.
Poses cross-fade into each other over a few frames, so a run can break into a
fall without a jump cut.
"""
import math
import numpy as np
from PySide6 import QtCore as C, QtGui as G
from .player import RigPlayer
from .skins import puppet, doll

CROSSFADE_MS = 170
OVERSAMPLE = 1.5            # layers are kept this much finer than they are drawn: rotation stays crisp
SYMBOL_MOODS = ('heart', 'happy', 'angry', 'puzzled', 'sleep')


class PuppetAnimation(RigPlayer):
    # Room on both sides: it leans into a run, reaches out, and lies down.
    BASE_ORIGIN = (10, 22)
    BASE_SIZE = (156, 160)
    GAME_SIZE = (190, 204)
    RENDER_SCALE = .30
    WAITING_ANCHOR = (128, 48)
    NAME = puppet.NAME
    skin_id = 'puppet'

    def __init__(self, button, skin=puppet):
        super().__init__(button, skin)
        self.boxes = {}
        if not self.pixmap.isNull():
            for name in skin.LAYERS:
                image = G.QImage(str(skin.LAYER_DIR/(name+'.png')))
                if image.isNull():
                    self.pixmap = G.QPixmap()      # an incomplete skin falls back to the gear
                    break
                # Each layer covers a small part of the 444×484 canvas: keep
                # only that part and remember where it goes.
                image = image.convertToFormat(G.QImage.Format_RGBA8888)
                alpha = np.frombuffer(image.constBits(), np.uint8).reshape(
                    image.height(), image.bytesPerLine()//4, 4)[:, :image.width(), 3]
                ys, xs = np.where(alpha > 0)
                box = (C.QRect(int(xs.min()), int(ys.min()), int(xs.max()-xs.min()+1), int(ys.max()-ys.min()+1))
                       if len(xs) else C.QRect(0, 0, 1, 1))
                self.layers[name] = G.QPixmap.fromImage(image.copy(box))
                self.boxes[name] = C.QRectF(box)
        self._sized = {}            # layers resampled for the size they are drawn at
        self._facing = 1            # 1 as drawn (looking left), -1 mirrored
        self._has_sack = True
        self.carrying = False       # it has the pointer (nothing is drawn: the pointer is simply gone)
        self._shown = None          # the pose last painted, for cross-fades
        self._from = None
        self.fade_clock = C.QElapsedTimer()

    # ── state the game switches ────────────────────────────────
    @property
    def facing(self):
        return self._facing

    @facing.setter
    def facing(self, value):
        value = -1 if value < 0 else 1
        if value != self._facing:
            self._facing = value
            self._idle_cache.clear()
            self.button.update()

    @property
    def has_sack(self):
        return self._has_sack

    @has_sack.setter
    def has_sack(self, value):
        if bool(value) != self._has_sack:
            self._has_sack = bool(value)
            self._idle_cache.clear()
            self.button.update()

    def act(self, mood):
        """Play `mood` now, whatever else is going on; the game drives the
        body through this instead of ``play``, which defers to matching."""
        if not self.enabled:
            return
        self._begin_fade()
        self.mood = mood
        self.clock.start()
        self.since_play.start()
        self.timer.start(33)
        self.button.update()

    def play(self, mood):
        before = self.mood
        super().play(mood)
        if self.mood != before:
            self._begin_fade()

    def _begin_fade(self):
        if self._shown is not None:
            self._from = self._shown
            self.fade_clock.start()

    @property
    def fading(self):
        return self._from is not None and self.fade_clock.isValid() and self.fade_clock.elapsed() < CROSSFADE_MS

    @property
    def blending(self):
        return False                # the cross-fade does this job for every mood

    @property
    def modified(self):
        return super().modified or self.fading

    def _after_advance(self):
        if self.enabled and self.mood in self.skin.HEIST_MOODS and self.timer.isActive():
            self.timer.setInterval(33)

    # ── geometry the game needs ────────────────────────────────
    def widget_point(self, canvas_point):
        """A canvas point of the resting figure, in the button's coordinates."""
        ox, oy = self.origin_for(self.button.width(), self.button.height())
        rs = self.render_scale
        x, y = ox+canvas_point[0]*rs, oy+canvas_point[1]*rs
        if self._facing < 0:
            x = self.button.width()-x
        return C.QPointF(x, y)

    # ── painting ───────────────────────────────────────────────
    def _values(self, t):
        a, _ = self.skin.pose(self.mood, t)
        m = dict(self.skin.body_motion(self.mood, t))
        if self.fading:
            k = self.fade_clock.elapsed()/CROSSFADE_MS
            k = k*k*(3-2*k)
            old_a, old_m = self._from
            a = {name: old_a.get(name, 0.)*(1-k)+value*k for name, value in a.items()}
            m = {name: old_m.get(name, 0.)*(1-k)+value*k for name, value in m.items()}
        elif self._from is not None:
            self._from = None
        # A pose value that is not a number must never reach the painter: a
        # transform built from one can keep the rasteriser busy for ever.
        for values in (a, m):
            for name, value in values.items():
                if not math.isfinite(value):
                    values[name] = 0.
        self._shown = (dict(a), dict(m))
        return a, m

    def _paint_on(self, device, t, render_scale=.30, origin=(-8, 14)):
        skin = self.skin
        pivots = skin.PIVOTS
        p = G.QPainter(device)
        p.setRenderHints(G.QPainter.Antialiasing | G.QPainter.SmoothPixmapTransform)
        if self.opacity < 1.:
            p.setOpacity(self.opacity)
        a, m = self._values(t)
        # Runtime modifiers: a glance, and being carried by the hat.
        lift, swing = self.drag_lift, self.drag_swing
        a['head'] += self.look_current*.8+self.drag_lean*.4
        a['lean'] += self.drag_lean*.7
        for limb in ('arm', 'back_arm', 'leg_l', 'leg_r'):
            a[limb] += swing
        a['sack'] -= swing*.6
        a['knee_l'] -= 10*lift
        a['knee_r'] -= 16*lift
        m['y'] -= 7*lift
        seconds = (self.since_play.elapsed() if self.since_play.isValid() else 0)/1000

        if self._facing < 0:
            p.translate(self.button.width(), 0)
            p.scale(-1, 1)
        p.translate(*origin)
        p.scale(render_scale, render_scale)
        lying = min(1., abs(a['lean'])/abs(skin.LIE_LEAN))
        if self.shadow:
            (cx, cy), (rx, ry) = skin.SHADOW['laden' if self._has_sack else 'bare']
            air = max(min(1., max(0., -m['y'])/90), lift)
            p.save()
            p.setPen(C.Qt.NoPen)
            p.setBrush(G.QColor(0, 0, 0, int(56*(1-air*.85))))
            # Lying down, the shadow stretches out under the whole length of it.
            p.drawEllipse(C.QPointF(cx+m['x']-150*lying, cy), rx*(1-air*.4)*(1+1.3*lying), ry*(1-air*.4))
            p.restore()
        ground = G.QTransform(p.transform())     # the floor: no hop, no lean
        p.translate(m['x'], m['y'])
        root = pivots['root']
        p.translate(*root)
        p.scale(1+m['squash'], 1-m['squash'])
        p.rotate(a['lean'])
        p.translate(-root[0], -root[1])

        def turn(pivot, angle):
            p.translate(*pivot)
            p.rotate(angle)
            p.translate(-pivot[0], -pivot[1])

        # Draw from layers already resampled to about the size they appear
        # at, not from the full-size artwork scaled down on every frame.
        detail = round(render_scale*self.button.devicePixelRatioF()*OVERSAMPLE, 3)
        if detail not in self._sized:
            if len(self._sized) >= 3:
                self._sized.clear()
            self._sized[detail] = {
                name: layer.scaled(max(1, round(layer.width()*detail)), max(1, round(layer.height()*detail)),
                                   C.Qt.IgnoreAspectRatio, C.Qt.SmoothTransformation) if detail < 1 else layer
                for name, layer in self.layers.items()}
        sized = self._sized[detail]

        def draw(name):
            layer = sized[name]
            p.drawPixmap(self.boxes[name], layer, C.QRectF(layer.rect()))

        def limb(upper, lower, joint, hinge, angle, bend):
            p.save()
            turn(pivots[joint], angle)
            draw(upper)
            turn(pivots[hinge], bend)
            draw(lower)
            p.restore()

        # Behind the legs: the sack, and the arm it hides while it is worn.
        drop = max(0., min(1., a.get('drop', 0.))) if self._has_sack else 1.
        p.save()
        turn(pivots['waist'], m['torso'])
        if drop > 0:
            limb('arm_back_upper', 'arm_back_lower', 'back_shoulder', 'back_elbow', a['back_arm'], a['back_fore'])
        if self._has_sack:
            p.save()
            turn(pivots['sack'], a['sack'])
            if drop > 0:
                # Between the back and the ground it travels in an arc: blend
                # the two placements, the way a tossed thing would go.
                down = skin.SACK_DOWN
                rest = G.QTransform(ground)
                rest.translate(down['x'], down['y'])
                rest.translate(300, 360)
                rest.rotate(down['turn'])
                rest.translate(-300, -360)
                worn = p.transform()
                k = drop*drop*(3-2*drop)
                mix = lambda u, v: u*(1-k)+v*k
                p.setTransform(G.QTransform(mix(worn.m11(), rest.m11()), mix(worn.m12(), rest.m12()),
                                            mix(worn.m21(), rest.m21()), mix(worn.m22(), rest.m22()),
                                            mix(worn.dx(), rest.dx()),
                                            mix(worn.dy(), rest.dy())-down['arc']*render_scale*math.sin(math.pi*drop)))
            draw('sack')
            p.restore()
        p.restore()
        behind = self.mood in skin.ARM_BEHIND
        if behind:
            p.save()
            turn(pivots['waist'], m['torso'])
            limb('arm_upper', 'arm_lower', 'shoulder', 'elbow', a['arm'], a['fore'])
            p.restore()
        limb('leg_r_upper', 'leg_r_lower', 'hip_r', 'knee_r', a['leg_r'], a['knee_r'])
        limb('leg_l_upper', 'leg_l_lower', 'hip_l', 'knee_l', a['leg_l'], a['knee_l'])
        p.save()
        turn(pivots['waist'], m['torso'])
        draw('torso')
        if self._has_sack and drop < .5:
            # The neck of the sack over the shoulder, with the hand gripping it.
            p.save()
            turn(pivots['sack'], a['sack'])
            p.setOpacity(p.opacity()*(1-2*drop))
            draw('sack_front')
            p.restore()
        p.save()
        turn(pivots['neck'], a['head'])
        draw('head')
        p.restore()
        if not behind:
            limb('arm_upper', 'arm_lower', 'shoulder', 'elbow', a['arm'], a['fore'])
        p.restore()
        skin.paint_extras(p, self.mood, seconds)
        if self.mood == 'down':
            # Stars circle above the head wherever it came to rest, upright.
            head = p.transform().map(C.QPointF(*skin.EYE))
            p.resetTransform()
            p.translate(head.x(), head.y()-34*self.scale)
            p.scale(render_scale, render_scale)
            skin.paint_stars(p, seconds)
        if self.mood in SYMBOL_MOODS:
            avoid = 'right' if self.look > 0 else 'left' if self.look < 0 else None
            doll.paint_effects(p, self.mood, t, self.duration, effect_scale=self.scale, avoid=avoid)
        p.end()
