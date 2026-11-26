"""The 守财木偶's own game: it steals the mouse pointer.

There is no cool-down, but there is one game per rest of the mouse: after a
game the mouse has to move, and then be still for ten seconds again, before
the next. If it never moves, the puppet dozes off ten seconds after its game
instead, and stays asleep until something stirs.

Leave the mouse still for ten seconds and an oversized pointer appears over
the real one. The puppet tiptoes up to it (freezing and whistling at the sky
whenever the mouse moves), snatches it, and bolts. What follows the real
pointer from then on is a gun sight. The puppet trips after a stretch, or as
soon as it is clicked or touched, and its sack comes off. Shooting the sack
gives the pointer back and knocks the 辞章 out of it (always a purple and a
blue one, sometimes a gold or red one too), which hang in the air
over the sack for a moment and are gone; the puppet gets up in tears, trudges
after the pointer and swings at it, a great windmill of one arm and then of
the other, like a child in a tantrum, until a click on the puppet makes it up. Escape ends the
game at once and puts the puppet where it started.

It is deliberately light on the window system. The game ticks at 30 Hz, a
window is only moved when its position really changed, the pointer overlay
is hidden whenever it has nothing to draw, the sack's window is only as big
as what it is showing, and none of the game's windows carries a display
affinity (the game ends the moment a capture is wanted, so they are never
on screen for one). A game also ends by itself after ``MAX_GAME_S``, or if
its ticks start arriving late.

Nothing here touches the system cursor or moves the real pointer: the big
pointer and the sight are drawn on a small click-through window that follows
the pointer, so a crash leaves nothing behind. Mouse
buttons and Escape are polled, not hooked.

There is no text anywhere in it. What to do next is shown instead: the sight
turns red over something that can be shot, the fallen sack glows and hops.
"""
import json
import math
import random
import sys
import time
from PySide6 import QtCore as C, QtGui as G, QtWidgets as W
from .lantern import EffectStage
from .skins import puppet

STILL_S = 10.           # the mouse has to rest this long; that is the only condition, every time
SNEAK_SPEED = 70.       # px/s at pet scale 1
RUN_SPEED = 210.        # a waddle under that sack, slow enough to catch
CRY_SPEED = 58.
WALK_SPEED = 150.
RUN_DISTANCE = (520., 820.)
MAX_FALLS = 3           # after this many unanswered falls it keeps the pointer and goes home
DOWN_S = 5.5            # how long it lies there before picking the sack up again
CRY_S = 40.             # how long it begs before giving up
SNEAK_LIMIT_S = 45.
SPOTTED_S = 1.1         # frozen this long after the mouse last moved
TICK_MS = 33            # 30 Hz: every tick moves top-level windows, which the compositor pays for
MAX_GAME_S = 150.       # whatever happens, a game never outlives this
STALL_S = 1.            # a tick this late means the machine is struggling ...
STALL_LIMIT = 3         # ... and this many in a row end the game

QUALITY_GLOW = {'虚妄': (255, 104, 104), '稀世': (255, 206, 96), '奇珍': (192, 132, 255), '独特': (112, 190, 255)}
ARROW = ((0, 0), (0, 17), (4, 13.2), (6.6, 19.4), (9.4, 18.2), (6.8, 12.2), (12, 12.2))


class Inputs:
    """Polled state of the left button and Escape, wherever the focus is."""

    def left_down(self):
        try:
            if sys.platform == 'win32':
                import ctypes
                user32 = ctypes.windll.user32
                return bool(user32.GetAsyncKeyState(0x02 if user32.GetSystemMetrics(23) else 0x01) & 0x8000)
            if sys.platform == 'darwin':
                import Quartz
                return bool(Quartz.CGEventSourceButtonState(1, 0))
        except Exception:
            pass
        return bool(W.QApplication.mouseButtons() & C.Qt.LeftButton)

    def escape_down(self):
        try:
            if sys.platform == 'win32':
                import ctypes
                return bool(ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000)
            if sys.platform == 'darwin':
                import Quartz
                return bool(Quartz.CGEventSourceKeyState(1, 53))
        except Exception:
            pass
        return False


def load_relics():
    """The 辞章 that can fall out of the sack: dicts with name, quality, value, file."""
    try:
        items = json.loads((puppet.RELIC_DIR/'relics.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    return [item for item in items if isinstance(item, dict) and (puppet.RELIC_DIR/str(item.get('file', ''))).is_file()]


COMMON = ('奇珍', '独特')         # purple and blue: one of each, every time
RARE = ('稀世', '虚妄')           # gold and red: sometimes one more on top
RARE_CHANCE = .30
# The extra 辞章 has a floor: by this many sacks at the latest it is this one.
# The dearest first, so that when both fall due together the core wins and
# the necklace follows with the next sack.
PITY = (('穆修拉之核', 20), ('被诅咒的蓝宝石', 10))


def new_pity(saved=None):
    """Sacks shot since each guaranteed 辞章 last fell out, from saved settings."""
    pity = {name: 0 for name, _ in PITY}
    if isinstance(saved, dict):
        for name, limit in PITY:
            value = saved.get(name)
            if isinstance(value, int) and not isinstance(value, bool):
                pity[name] = max(0, min(limit, value))
    return pity


def pick_loot(relics, rng=random, pity=None):
    """What falls out of the sack, the sure ones first.

    Always one purple and one blue 辞章, any of each with the same odds. Three
    times in ten a third one, gold or better. Only that third one has a floor
    (``PITY``): the count for a guaranteed 辞章 goes up with every sack and
    back to zero whenever it falls out, on the floor or by luck before it.
    """
    loot = []
    for quality in COMMON:
        pool = [item for item in relics if item.get('quality') == quality]
        if pool:
            loot.append(rng.choice(pool))
    rare = [item for item in relics if item.get('quality') in RARE]
    extra = None
    if pity is not None:
        for name, limit in PITY:
            pity[name] = pity.get(name, 0)+1
        for name, limit in PITY:
            due = [item for item in rare if item.get('name') == name]
            if pity[name] >= limit and due:
                extra = due[0]
                break
    if extra is None and rare and rng.random() < RARE_CHANCE:
        extra = rng.choice(rare)
    if extra is not None:
        loot.append(extra)
        if pity is not None and extra.get('name') in pity:
            pity[extra['name']] = 0
    if not loot and relics:
        loot.append(rng.choice(relics))
    return loot


# How loudly each quality arrives. Reach, lift and size are at pet scale 1.
TIERS = {
    '独特': dict(rays=6, reach=58, spin=40, sparks=0, rings=0, size=27, lift=0),
    '奇珍': dict(rays=10, reach=76, spin=55, sparks=7, rings=0, size=30, lift=4),
    '稀世': dict(rays=14, reach=98, spin=70, sparks=11, rings=1, size=34, lift=10),
    '虚妄': dict(rays=18, reach=120, spin=90, sparks=16, rings=2, size=38, lift=16),
}


def paint_relic_burst(p, base, seconds, life, pixmap, quality, s, dx=0.):
    """One 辞章 jumping out at `base`: rays, a pop, a moment to look, gone.
    Blue is a plain glow; purple adds sparks; gold a shock ring and longer
    rays; red two rings, the longest rays and a pulse."""
    if seconds <= 0 or life <= 0:
        return
    tier = TIERS.get(quality, TIERS['独特'])
    colour = QUALITY_GLOW.get(quality, QUALITY_GLOW['独特'])
    r, g, b = colour
    t = min(1., seconds/life)
    rise = _back_out(min(1., seconds/.4))
    fade = 1-max(0., (t-.82)/.18)
    pulse = 1+.07*math.sin(seconds*7) if tier['rings'] > 1 else 1.
    centre = C.QPointF(base.x()+dx*rise, base.y()-(56+tier['lift'])*s*rise-4*s*math.sin(seconds*3.))
    reach = tier['reach']*s*rise*pulse
    p.save()
    p.setOpacity(fade)
    for k in range(tier['rings']):
        age = (seconds-.12-k*.24)/.75
        if 0 < age < 1:
            p.setPen(G.QPen(G.QColor(r, g, b, int(230*(1-age))), (5-3*age)*s))
            p.setBrush(C.Qt.NoBrush)
            radius = tier['reach']*s*(.25+1.05*age)
            p.drawEllipse(centre, radius, radius)
    p.save()
    p.translate(centre)
    p.rotate(seconds*tier['spin'])
    p.setPen(C.Qt.NoPen)
    for i in range(tier['rays']):
        p.rotate(360/tier['rays'])
        length = reach*(1. if i % 2 else .62)
        ray = G.QLinearGradient(0, 0, 0, -length)
        ray.setColorAt(0, G.QColor(r, g, b, 170))
        ray.setColorAt(1, G.QColor(r, g, b, 0))
        p.setBrush(ray)
        p.drawPolygon(G.QPolygonF([C.QPointF(-5*s, 0), C.QPointF(5*s, 0), C.QPointF(0, -length)]))
    p.restore()
    _glow(p, centre, tier['size']*1.75*s*rise*pulse, colour, .72)
    for i in range(tier['sparks']):
        cycle = (seconds*.85+i*.137) % 1.
        angle = i*2.39996+seconds*.6
        distance = tier['reach']*s*(.32+.78*cycle)
        size = (2.6+1.6*(i % 3))*s*math.sin(math.pi*cycle)*rise
        if size <= .2:
            continue
        p.save()
        p.translate(centre.x()+math.cos(angle)*distance, centre.y()+math.sin(angle)*distance*.86)
        p.rotate(seconds*120+i*33)
        p.setPen(C.Qt.NoPen)
        p.setBrush(G.QColor(min(255, r+70), min(255, g+70), min(255, b+70), 235))
        p.drawPolygon(G.QPolygonF([C.QPointF(0, -size*2.2), C.QPointF(size*.45, -size*.45), C.QPointF(size*2.2, 0),
                                   C.QPointF(size*.45, size*.45), C.QPointF(0, size*2.2), C.QPointF(-size*.45, size*.45),
                                   C.QPointF(-size*2.2, 0), C.QPointF(-size*.45, -size*.45)]))
        p.restore()
    if pixmap is not None and not pixmap.isNull():
        half = tier['size']*s*rise
        p.drawPixmap(C.QRectF(centre.x()-half, centre.y()-half, 2*half, 2*half), pixmap, C.QRectF(pixmap.rect()))
    p.restore()


def coin_pixmap():
    """Stand-in when no 辞章 artwork is installed: a plain gold coin."""
    pixmap = G.QPixmap(96, 96)
    pixmap.fill(C.Qt.transparent)
    p = G.QPainter(pixmap)
    p.setRenderHint(G.QPainter.Antialiasing)
    p.setPen(G.QPen(G.QColor(120, 80, 20), 5))
    p.setBrush(G.QColor(244, 196, 72))
    p.drawEllipse(C.QRectF(10, 10, 76, 76))
    p.setPen(G.QPen(G.QColor(150, 104, 30), 4))
    p.setBrush(C.Qt.NoBrush)
    p.drawEllipse(C.QRectF(24, 24, 48, 48))
    p.end()
    return pixmap


def _back_out(x):
    """0→1 with a small overshoot: things pop in rather than fade in."""
    x = max(0., min(1., x))-1
    return 1+x*x*(2.7*x+1.7)


def _float_window(widget):
    """Qt resets the window level on every show on macOS."""
    if sys.platform == 'darwin':
        try:
            from ..src import macos as native
            native.keep_floating(int(widget.winId()))
        except Exception:
            pass


def _glow(p, centre, radius, colour, alpha):
    gradient = G.QRadialGradient(centre, radius)
    gradient.setColorAt(0, G.QColor(colour[0], colour[1], colour[2], int(255*alpha)))
    gradient.setColorAt(.55, G.QColor(colour[0], colour[1], colour[2], int(255*alpha*.35)))
    gradient.setColorAt(1, G.QColor(colour[0], colour[1], colour[2], 0))
    p.setPen(C.Qt.NoPen)
    p.setBrush(gradient)
    p.drawEllipse(centre, radius, radius)


class CursorSprite(EffectStage):
    """What rides on the real pointer: the oversized pointer while the puppet
    is after it, the gun sight once it is gone."""
    SIZE = 176

    def __init__(self):
        super().__init__()
        self.resize(self.SIZE, self.SIZE)
        self.scale = 1.
        self.mode = None            # 'arrow' | 'cross' | None
        self.leaving = False        # the arrow is shrinking away
        self.mode_clock = C.QElapsedTimer()
        self.hot = False            # the sight is over something to shoot
        self.hit = False            # the puppet is pounding on it
        self.life = C.QElapsedTimer()
        self.life.start()
        self.painter = self._paint

    def set_mode(self, mode, leaving=False):
        self.mode = mode
        self.leaving = leaving
        self.mode_clock.start()

    def follow(self, point):
        """Ride on the pointer; hidden altogether while there is nothing to draw."""
        if self.idle():
            if self.isVisible():
                self.hide()
            return
        corner = C.QPoint(point.x()-self.SIZE//2, point.y()-self.SIZE//2)
        if corner != self.pos():
            self.move(corner)
        if not self.isVisible():
            self.show()
            _float_window(self)
        self.update()

    def idle(self):
        """Nothing left to draw."""
        return self.mode is None and not self.hit

    def _paint(self, p):
        p.setRenderHints(G.QPainter.Antialiasing | G.QPainter.SmoothPixmapTransform)
        c = self.SIZE/2
        s = self.scale
        seconds = self.life.elapsed()/1000
        age = self.mode_clock.elapsed()/1000 if self.mode_clock.isValid() else 9.
        if self.hit:
            # Each blow on the pointer throws off a few stars.
            for i in range(3):
                beat = (seconds*1.33+i*.33) % 1.
                angle = i*2.1+int(seconds*1.33+i*.33)*2.4
                p.save()
                p.translate(c+math.cos(angle)*(14+30*beat)*s, c+math.sin(angle)*(14+30*beat)*s)
                p.rotate(seconds*300+i*50)
                p.scale(s*(1-beat*.5), s*(1-beat*.5))
                p.setOpacity(1-beat)
                p.setPen(G.QPen(G.QColor(60, 40, 10), 1.6))
                p.setBrush(puppet.effects.STAR)
                p.drawPath(puppet.effects.star_path(7.))
                p.restore()
        shake = C.QPointF(0, 0)
        if self.mode == 'arrow':
            size = (1-min(1., age/.3))**2 if self.leaving else _back_out(age/.28)
            if self.leaving and age >= .3:
                self.mode = None
            elif size > 0:
                p.save()
                p.translate(c+shake.x(), c+shake.y())
                if not self.leaving:
                    # A soft pulse under it: this is the thing being eyed.
                    _glow(p, C.QPointF(14*s, 20*s), 46*s, (255, 236, 170), .28+.14*math.sin(seconds*5))
                p.scale(3.1*s*size, 3.1*s*size)
                p.setPen(G.QPen(G.QColor(20, 20, 20), 1.15, C.Qt.SolidLine, C.Qt.RoundCap, C.Qt.RoundJoin))
                p.setBrush(G.QColor(255, 255, 255))
                p.drawPolygon(G.QPolygonF([C.QPointF(x, y) for x, y in ARROW]))
                p.restore()
        elif self.mode == 'cross':
            size = _back_out(age/.3)
            colour = G.QColor(255, 70, 60) if self.hot else G.QColor(255, 255, 255)
            radius = (17 if self.hot else 21)*s
            p.save()
            p.translate(c, c)
            p.scale(size, size)
            p.rotate(seconds*(150 if self.hot else 24))
            for pen in (G.QPen(G.QColor(0, 0, 0, 200), 5.2*s, C.Qt.SolidLine, C.Qt.RoundCap),
                        G.QPen(colour, 2.6*s, C.Qt.SolidLine, C.Qt.RoundCap)):
                p.setPen(pen)
                p.setBrush(C.Qt.NoBrush)
                p.drawEllipse(C.QPointF(0, 0), radius, radius)
                for quarter in range(4):
                    p.save()
                    p.rotate(quarter*90)
                    p.drawLine(C.QPointF(0, -radius-9*s), C.QPointF(0, -radius+7*s))
                    p.restore()
            p.setPen(C.Qt.NoPen)
            p.setBrush(colour)
            p.drawEllipse(C.QPointF(0, 0), 2.4*s, 2.4*s)
            p.restore()


class SackWindow(W.QWidget):
    """The sack where it fell. The one thing in the game that takes a click."""

    def __init__(self, on_hit):
        super().__init__(None, C.Qt.Tool | C.Qt.FramelessWindowHint | C.Qt.WindowStaysOnTopHint |
                         C.Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(C.Qt.WA_TranslucentBackground)
        self.setAttribute(C.Qt.WA_ShowWithoutActivating)
        if sys.platform == 'darwin':
            self.setAttribute(C.Qt.WA_MacAlwaysShowToolWindow)
        self.setCursor(C.Qt.CrossCursor)
        self.on_hit = on_hit
        self.pixmap = G.QPixmap(str(puppet.SACK_IMAGE))
        self.phase = None           # 'fly' | 'rest' | 'burst'
        self.clock = C.QElapsedTimer()
        self.scale = 1.
        self.start = self.end = C.QPointF()
        self.spin = 1
        self.relics = []            # (pixmap, quality) of what is bursting out

    FLY_S = .55
    BURST_S = 2.6           # the 辞章 hangs over the sack this long, then is gone

    def launch(self, start, end, spin, scale):
        """Thrown from `start` to lie at `end` (its bottom centre, global)."""
        self.scale = scale
        self._fit(210)              # the sack and its halo; the burst needs more
        self.start, self.end, self.spin = C.QPointF(start), C.QPointF(end), spin
        self.phase = 'fly'
        self.clock.start()
        self.step()
        self.show()
        _float_window(self)

    def burst(self, relics):
        """`relics` is a list of (pixmap, quality), the surest first."""
        self.relics = list(relics)
        self.phase = 'burst'
        self.clock.start()
        self._fit(390)              # room for the widest burst
        self.step()

    def _fit(self, side):
        side = int(side*self.scale)
        if self.width() != side:
            self.resize(side, side)

    def put_away(self):
        self.phase = None
        self.hide()

    def targetable(self):
        return self.phase in ('fly', 'rest') and self.isVisible()

    def hit_rect(self):
        """Where the sack itself is, for turning the sight red."""
        side = 120*self.scale
        return C.QRectF(self.end.x()-side/2, self.end.y()-side*.9, side, side)

    def rest_point(self):
        return C.QPointF(self.end)

    def step(self):
        """Advance; called every frame of the game."""
        if self.phase is None:
            return
        seconds = self.clock.elapsed()/1000
        point = C.QPointF(self.end)
        if self.phase == 'fly':
            t = min(1., seconds/self.FLY_S)
            point = self.start+(self.end-self.start)*t
            point.setY(point.y()-80*self.scale*math.sin(math.pi*t))
            if t >= 1:
                self.phase = 'rest'
                self.clock.start()
        elif self.phase == 'burst' and seconds >= self.BURST_S:
            self.put_away()
            return
        corner = C.QPoint(int(point.x()-self.width()/2), int(point.y()-self.height()+18*self.scale))
        if corner != self.pos():
            self.move(corner)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == C.Qt.LeftButton and self.targetable():
            self.on_hit()
        event.accept()

    def paintEvent(self, event):
        if self.phase is None or self.pixmap.isNull():
            return
        p = G.QPainter(self)
        p.setRenderHints(G.QPainter.Antialiasing | G.QPainter.SmoothPixmapTransform)
        s = self.scale
        seconds = self.clock.elapsed()/1000
        ground = C.QPointF(self.width()/2, self.height()-18*s)
        rs = puppet_render_scale(s)
        w, h = self.pixmap.width()*rs, self.pixmap.height()*rs
        lying = 74.*self.spin
        hop = 0.
        angle = lying
        alpha = 1.
        size = 1.
        if self.phase == 'fly':
            t = min(1., seconds/self.FLY_S)
            angle = lying*t+self.spin*360*t*(1-t)
        elif self.phase == 'rest':
            settle = math.exp(-seconds*5)*math.cos(seconds*18)
            beat = (seconds % 1.5)/1.5
            hop = 7*s*abs(math.sin(math.pi*min(1., beat/.3))) if seconds > .5 else 0.
            angle = lying+8*settle*self.spin+4*math.sin(math.pi*min(1., beat/.3))*self.spin
            # "Shoot this": a warm halo that breathes, and a hop every beat and a half.
            _glow(p, C.QPointF(ground.x(), ground.y()-h*.3), 86*s, (255, 214, 120), .34+.2*math.sin(seconds*4.4))
        else:
            t = min(1., seconds/.22)
            alpha = 1-t
            size = 1+.35*t
        p.save()
        p.setPen(C.Qt.NoPen)
        p.setBrush(G.QColor(0, 0, 0, int(50*alpha)))
        p.drawEllipse(ground, h*.42, 7*s)
        p.restore()
        if alpha > 0:
            p.save()
            p.setOpacity(alpha)
            p.translate(ground.x(), ground.y()-w*.46-hop)
            p.rotate(angle)
            p.scale(size, size)
            p.drawPixmap(C.QRectF(-w/2, -h/2, w, h), self.pixmap, C.QRectF(self.pixmap.rect()))
            p.restore()
        if self.phase == 'burst':
            base = C.QPointF(ground.x(), ground.y()-h*.3)
            # The sure pair to either side; a third, rarer one comes a beat
            # later, between them and on top.
            pair = self.relics[:2]
            for index, (pixmap, quality) in enumerate(pair):
                spread = (index-(len(pair)-1)/2)*(124 if len(self.relics) > 2 else 96)*s
                paint_relic_burst(p, base, seconds-index*.12, self.BURST_S-index*.12, pixmap, quality, s, spread)
            for pixmap, quality in self.relics[2:3]:
                paint_relic_burst(p, C.QPointF(base.x(), base.y()-34*s), seconds-.45, self.BURST_S-.45,
                                  pixmap, quality, s)
        p.end()


def puppet_render_scale(scale):
    from .puppet import PuppetAnimation
    return PuppetAnimation.RENDER_SCALE*scale


class Heist(C.QObject):
    """Watches for a resting mouse and runs the game when the time is right."""

    def __init__(self, gear, window=None, inputs=None, clock=time.monotonic, cursor=None, rng=None):
        super().__init__(gear)
        self.gear = gear
        self.window = window if window is not None else gear.window()
        self.inputs = inputs or Inputs()
        self.clock = clock
        self.cursor = cursor or (lambda: G.QCursor.pos())
        self.rng = rng or random.Random()
        self.enabled = True
        self.state = None
        self.needs_move = False     # after a game: no other until the mouse has moved again
        self.rested = False         # ... and it has already been sent to doze for this rest
        self._still_pos = None
        self._still_since = self.clock()
        self.sprite = None
        self.sack = None
        self.relics = None
        self.pity = new_pity()
        self.loot = None
        self.falls = 0
        self.win = False
        self.home = C.QPoint()
        self.offset = C.QPoint()
        self.pos = C.QPointF()
        self.area = C.QRect()
        self.velocity = C.QPointF()
        self.watch = C.QTimer(self)
        self.watch.setInterval(500)
        self.watch.timeout.connect(self.poll)
        self.watch.start()
        self.timer = C.QTimer(self)
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self.tick)

    # ── when ───────────────────────────────────────────────────
    @property
    def pet(self):
        return self.gear.pet

    @property
    def active(self):
        return self.state is not None

    def is_puppet(self):
        return getattr(self.pet, 'skin_id', None) == 'puppet'

    def _interrupted(self):
        window = self.window
        state = getattr(window, 'state', None)
        panel = getattr(window, 'panel', None)
        return (not self.pet.enabled or not self.is_puppet() or not self.gear.isVisible()
                or getattr(self.gear, 'origin', None) is not None       # a hand is on it
                or getattr(self.gear, 'matching', False) or getattr(self.gear, 'game_background', False)
                or self.pet.dragging or (panel is not None and panel.isVisible())
                or (state is not None and getattr(state, 'opened', False))
                or getattr(window, '_update_starting', False))

    def ready(self, now, cursor):
        """Everything but the ten seconds of stillness."""
        if not self.enabled or self._interrupted():
            return False
        behavior = getattr(self.window, 'behavior', None)
        if behavior is not None and (behavior.quiet or behavior.sleeping):
            return False
        if self.pet.mood != 'idle' or self.inputs.left_down():
            return False
        rect = C.QRect(self.gear.mapToGlobal(C.QPoint(0, 0)), self.gear.size())
        if rect.contains(cursor):
            return False
        here = W.QApplication.screenAt(rect.center())
        return here is not None and here == W.QApplication.screenAt(cursor)

    def poll(self):
        now = self.clock()
        cursor = self.cursor()
        if self._still_pos is None or (cursor-self._still_pos).manhattanLength() > 2:
            if self._still_pos is not None:
                self.needs_move = False     # the mouse is back: the next rest counts
                self.rested = False
            self._still_pos = C.QPoint(cursor)
            self._still_since = now
        if self.active or now-self._still_since < STILL_S:
            return
        if self.needs_move:
            self._rest()
        elif self.ready(now, cursor):
            self.start()

    def _rest(self):
        """One game per rest of the mouse. It has not moved since the last game
        ended, so instead of another the puppet settles down to doze."""
        behavior = getattr(self.window, 'behavior', None)
        if (behavior is None or behavior.sleeping or behavior.quiet or self._interrupted()
                or self.pet.mood != 'idle' or self.rested):
            return
        # Once only: typing with the mouse at rest wakes it, and it should
        # then stay up rather than nod off again every ten seconds.
        self.rested = True
        behavior.sleep()

    # ── start and end ──────────────────────────────────────────
    def start(self):
        if self.active:
            return
        now = self.clock()
        corner = self.gear.mapToGlobal(C.QPoint(0, 0))
        self.home = C.QPoint(self.window.pos())
        self.offset = corner-self.home
        self.pos = C.QPointF(corner)
        screen = W.QApplication.screenAt(C.QRect(corner, self.gear.size()).center()) or W.QApplication.primaryScreen()
        self.area = screen.availableGeometry()
        self.falls = 0
        self.loot = None
        self.win = False
        self.started = now
        self.spotted_until = 0.
        self.grace_until = 0.
        self.forced_trip = False
        self._last_tick = now
        self._last_cursor = self.cursor()
        self._was_down = self.inputs.left_down()
        self.click = False
        self.cursor_moved = False
        self.stalls = 0
        self._last_real = time.monotonic()
        if self.sprite is None:
            self.sprite = CursorSprite()
        self.sprite.scale = self.pet.scale
        self.sprite.hit = self.sprite.hot = False
        self.sprite.set_mode('arrow')
        self.sprite.follow(self._last_cursor)
        behavior = getattr(self.window, 'behavior', None)
        if behavior is not None:
            behavior.touched()
        self._go('sneak')
        self.timer.start()

    def abort(self):
        """Stop now and put everything back (Escape, or work to be done)."""
        if not self.active:
            return
        self._end()

    def _end(self):
        self.timer.stop()
        self.state = None
        if self.sprite is not None:
            self.sprite.mode = None
            self.sprite.hit = False
            self.sprite.hide()
        if self.sack is not None:
            self.sack.put_away()
        pet = self.pet
        if self.is_puppet():
            pet.carrying = False
            pet.has_sack = True
            pet.facing = 1
            if pet.enabled and pet.mood in puppet.HEIST_MOODS:
                pet.act('land')
        self._restore_cursor()
        self.window.move(self.home)
        # No cool-down, but one game per rest: the mouse has to move, and
        # then be still for ten seconds again, before the next.
        self._still_since = self.clock()
        self.needs_move = True
        self.rested = False
        self.loot = None

    def _restore_cursor(self):
        self.gear.setCursor(C.Qt.ArrowCursor if getattr(self.gear, 'locked', False) else C.Qt.PointingHandCursor)

    # ── helpers ────────────────────────────────────────────────
    def _go(self, state):
        self.state = state
        self.t0 = self.clock()
        if self.sprite is not None:
            self.sprite.hit = state == 'hit'
        if state == 'rejoice':
            self.pet.act('rejoice')

    def _pose(self, mood):
        if self.pet.mood != mood:
            self.pet.act(mood)

    @property
    def scale(self):
        return self.pet.scale

    def _apply(self):
        """Clamp to the screen and move the window; says which edges were hit."""
        w, h = self.gear.width(), self.gear.height()
        left, top = self.area.left(), self.area.top()
        right, bottom = max(left, self.area.right()-w), max(top, self.area.bottom()-h)
        x, y = self.pos.x(), self.pos.y()
        hit_x, hit_y = not left <= x <= right, not top <= y <= bottom
        self.pos = C.QPointF(min(max(x, left), right), min(max(y, top), bottom))
        corner = self.pos.toPoint()-self.offset
        if corner != self.window.pos():
            self.window.move(corner)
        return hit_x, hit_y

    def _move_to(self, target, speed, dt):
        """Step towards `target`; returns the distance still to go."""
        dx, dy = target.x()-self.pos.x(), target.y()-self.pos.y()
        distance = math.hypot(dx, dy)
        step = speed*self.scale*dt
        if distance <= step or distance < .5:
            self.pos = C.QPointF(target)
            self._apply()
            return 0.
        self.pos = C.QPointF(self.pos.x()+dx/distance*step, self.pos.y()+dy/distance*step)
        hit_x, hit_y = self._apply()
        if (hit_x and abs(dy) < 2) or (hit_y and abs(dx) < 2) or (hit_x and hit_y):
            return 0.               # pinned against the edge: as close as it gets
        return distance-step

    def _centre(self):
        return C.QPointF(self.pos.x()+self.gear.width()/2, self.pos.y()+self.gear.height()/2)

    def _face(self, x):
        centre = self._centre().x()
        if x > centre+20*self.scale:
            self.pet.facing = -1
        elif x < centre-20*self.scale:
            self.pet.facing = 1

    def _reach_target(self, cursor):
        """Where the gear has to be for the outstretched hand to be on the pointer."""
        self._face(cursor.x())
        return C.QPointF(cursor)-self.pet.widget_point(puppet.REACH)

    def _body_rect(self):
        inset = int(34*self.scale)
        return C.QRectF(self.pos.x()+inset, self.pos.y()+inset*.6,
                        self.gear.width()-2*inset, self.gear.height()-inset*.6)

    # ── the frame ──────────────────────────────────────────────
    def tick(self):
        if not self.active:
            self.timer.stop()
            return
        now = self.clock()
        dt = max(0., min(.05, now-self._last_tick))
        self._last_tick = now
        # Safety nets: a game that has gone on too long, or whose ticks keep
        # arriving late (the machine has better things to do), just ends.
        real = time.monotonic()
        self.stalls = self.stalls+1 if real-self._last_real > STALL_S else 0
        self._last_real = real
        if (self.inputs.escape_down() or self._interrupted() or now-self.started > MAX_GAME_S
                or self.stalls >= STALL_LIMIT):
            self.abort()
            return
        cursor = self.cursor()
        down = self.inputs.left_down()
        self.click = down and not self._was_down
        self._was_down = down
        self.cursor_moved = (cursor-self._last_cursor).manhattanLength() > 2
        self._last_cursor = C.QPoint(cursor)
        getattr(self, '_s_'+self.state)(now, dt, cursor)
        if not self.active:
            return
        if self.sack is not None:
            self.sack.step()
        sprite = self.sprite
        sprite.hot = sprite.mode == 'cross' and (
            (self.sack is not None and self.sack.targetable() and self.sack.hit_rect().contains(C.QPointF(cursor)))
            or (self.state == 'run' and self._body_rect().contains(C.QPointF(cursor))))
        sprite.follow(cursor)

    def _s_sneak(self, now, dt, cursor):
        if now-self.started > SNEAK_LIMIT_S:
            self._go('home')
            return
        if self.cursor_moved:
            self.spotted_until = now+SPOTTED_S
        if now < self.spotted_until:
            self._pose('freeze')
            return
        target = self._reach_target(cursor)
        self._pose('sneak')
        if self._move_to(target, SNEAK_SPEED, dt) < 3:
            self._go('grab')

    def _s_grab(self, now, dt, cursor):
        self._pose('grab')
        elapsed = now-self.t0
        if not self.pet.carrying:
            hand = self.pos+self.pet.widget_point(puppet.REACH)
            if math.hypot(cursor.x()-hand.x(), cursor.y()-hand.y()) > 60*self.scale:
                self.spotted_until = now+SPOTTED_S     # it got away: back to creeping
                self._go('sneak')
                return
            if elapsed >= .36:
                self.pet.carrying = True
                self.sprite.set_mode('cross')
                self.gear.setCursor(C.Qt.CrossCursor)
        if elapsed >= .8:
            self._begin_run(now, cursor)

    def _begin_run(self, now, cursor):
        centre = self._centre()
        direction = 1 if centre.x() >= cursor.x() else -1
        room = (self.area.right()-(self.pos.x()+self.gear.width())) if direction > 0 else (self.pos.x()-self.area.left())
        if room < 260*self.scale:
            direction = -direction
        speed = RUN_SPEED*self.scale
        self.velocity = C.QPointF(direction*speed, self.rng.uniform(-.28, .28)*speed)
        self.run_left = self.rng.uniform(*RUN_DISTANCE)*self.scale
        self.grace_until = now+.7
        self.forced_trip = False
        self._go('run')

    def _s_run(self, now, dt, cursor):
        self._pose('run')
        speed = RUN_SPEED*self.scale
        centre = self._centre()
        ax, ay = centre.x()-cursor.x(), centre.y()-cursor.y()
        distance = math.hypot(ax, ay)
        vx, vy = self.velocity.x(), self.velocity.y()
        if 1 < distance < 300*self.scale and now >= self.grace_until:
            # Veer away from the pointer coming after it.
            vx, vy = vx*.9+ax/distance*speed*.1, vy*.9+ay/distance*speed*.1
        length = math.hypot(vx, vy) or 1.
        vx, vy = vx/length*speed, vy/length*speed
        self.pos = C.QPointF(self.pos.x()+vx*dt, self.pos.y()+vy*dt)
        hit_x, hit_y = self._apply()
        if hit_x:
            vx = -vx
        if hit_y:
            vy = -vy
        self.velocity = C.QPointF(vx, vy)
        if abs(vx) > speed*.15:
            self.pet.facing = 1 if vx < 0 else -1
        self.run_left -= speed*dt
        caught = now >= self.grace_until and (self.click or self.forced_trip
                                              or self._body_rect().contains(C.QPointF(cursor)))
        if caught or self.run_left <= 0:
            self._begin_trip(now)

    def _begin_trip(self, now):
        pet = self.pet
        vx, vy = self.velocity.x(), self.velocity.y()
        length = math.hypot(vx, vy) or 1.
        self.slide = C.QPointF(vx/length*190*self.scale, vy/length*190*self.scale)
        self.falls += 1
        start = self.pos+pet.widget_point(puppet.SACK_CENTRE)
        feet = self.pos+pet.widget_point((206, puppet.GROUND_Y))
        behind = 1 if pet.facing > 0 else -1        # facing left, the sack flies off to the right
        end = C.QPointF(feet.x()+behind*96*self.scale, feet.y())
        # Far enough from the edges that what bursts out of it stays on screen.
        side, above = 200*self.scale, 240*self.scale
        end.setX(min(max(end.x(), self.area.left()+side), self.area.right()-side))
        end.setY(min(max(end.y(), self.area.top()+above), self.area.bottom()-6))
        pet.has_sack = False
        if self.sack is None:
            self.sack = SackWindow(self.sack_hit)
        self.sack.launch(start, end, behind, self.scale)
        self._go('trip')

    def _s_trip(self, now, dt, cursor):
        self._pose('trip')
        elapsed = now-self.t0
        ease = max(0., 1-elapsed/.7)
        self.pos = C.QPointF(self.pos.x()+self.slide.x()*ease*dt, self.pos.y()+self.slide.y()*ease*dt)
        self._apply()
        if elapsed >= .78:
            self.down_until = now+DOWN_S
            self._go('down')

    def _s_down(self, now, dt, cursor):
        self._pose('down')
        if (self.loot is not None and now-self.t0 > 1.) or now > self.down_until:
            self._go('getup')

    def _s_getup(self, now, dt, cursor):
        self._pose('getup')
        if now-self.t0 >= 1.1:
            self._after_getup(now)

    def _after_getup(self, now):
        if self.loot is not None:
            self.cry_until = now+CRY_S
            self._go('cry')
        else:
            self._go('fetch')

    def _s_fetch(self, now, dt, cursor):
        """Nobody shot the sack: back on with it and off again."""
        if self.loot is not None:
            self._after_getup(now)
            return
        sack = self.sack.rest_point()
        self._face(sack.x())
        target = sack-self.pet.widget_point((206, puppet.GROUND_Y))
        self._pose('walk')
        if self._move_to(target, WALK_SPEED*1.3, dt) < 4:
            self.sack.put_away()
            self.pet.has_sack = True
            if self.falls >= MAX_FALLS:
                self.win = True
                self._go('home')
            else:
                self._begin_run(now, cursor)

    def sack_hit(self):
        """The sight was on the sack and the trigger was pulled."""
        if self.loot is not None or self.state not in ('trip', 'down', 'getup', 'fetch'):
            return
        if self.relics is None:
            self.relics = load_relics()
        items = pick_loot(self.relics, self.rng, self.pity)
        shown = [(G.QPixmap(str(puppet.RELIC_DIR/item['file'])), item.get('quality')) for item in items]
        self.loot = items or [dict(name='', quality='稀世')]
        self.sack.burst(shown or [(coin_pixmap(), '稀世')])
        self.pet.carrying = False
        self._restore_cursor()
        self.sprite.set_mode('arrow', leaving=True)

    def _s_cry(self, now, dt, cursor):
        if now > self.cry_until:
            self._go('sulk')
            return
        target = self._reach_target(cursor)
        self._pose('cry')
        if self._move_to(target, CRY_SPEED, dt) < 4:
            self._go('hit')

    def _s_hit(self, now, dt, cursor):
        if now > self.cry_until:
            self._go('sulk')
            return
        self._pose('hit')
        target = self._reach_target(cursor)
        if math.hypot(target.x()-self.pos.x(), target.y()-self.pos.y()) > 36*self.scale:
            self._go('cry')

    def _s_sulk(self, now, dt, cursor):
        self._pose('sulk')
        if now-self.t0 >= 3.5:
            self.loot = None
            self._go('home')

    def _s_rejoice(self, now, dt, cursor):
        if now-self.t0 >= 1.75:
            self._go('home')

    def _s_home(self, now, dt, cursor):
        target = C.QPointF(self.home+self.offset)
        if abs(target.x()-self.pos.x()) > 6:
            self.pet.facing = 1 if target.x() < self.pos.x() else -1
        self._pose('walk')
        if self._move_to(target, WALK_SPEED, dt) < 2:
            pet = self.pet
            pet.facing = 1
            pet.has_sack = True
            if pet.carrying:
                # It keeps nothing on the desktop: the pointer comes back here.
                pet.carrying = False
                self.sprite.set_mode('arrow', leaving=True)
                self._restore_cursor()
            pet.act('rejoice' if self.win else 'land')
            self._go('settle')

    def _s_settle(self, now, dt, cursor):
        if now-self.t0 >= (1.8 if self.win else .6):
            self._end()

    # ── clicks on the puppet itself ────────────────────────────
    def pet_clicked(self):
        """A left click on the puppet while the game runs. Always consumed.
        While it is begging, the click is what it was asking for."""
        if self.state == 'run':
            self.forced_trip = True
        elif self.loot is not None and self.state in ('cry', 'hit', 'sulk', 'down', 'getup'):
            self.give_back()
        return True

    def give_back(self):
        self.loot = None
        if self.sack is not None:
            self.sack.put_away()
        self.pet.has_sack = True
        self._go('rejoice')
