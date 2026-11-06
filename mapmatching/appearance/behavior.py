"""What the mascot does when nobody asked it to do anything.

A 1 Hz scheduler on top of :class:`PetAnimation`. It never interrupts work
the player can see (matching, a background mini-game, an open settings
panel, a drag); it only fills the quiet in between:

- small unprompted actions every 20–60 s (tilt, shift weight, stretch, look
  at the cursor), halved in power-saving mode, off in quiet mode;
- a doze after five minutes without any input on the machine, left again on
  the first input or hover;
- an idle fade after 30 s of no interaction with the companion, restored on
  hover (optional);
- a head turn towards the speech bubble while one is up.
"""
import random
import sys
import time
from PySide6 import QtCore as C, QtGui as G

MICRO_ACTIONS = ('tilt', 'shift', 'stretch', 'look')
DOZE_AFTER_S = 300
FADE_AFTER_S = 30
FADE_TO = .7
MICRO_GAP_S = (20, 60)
HOVER_COOLDOWN_S = 9


def seconds_since_input():
    """Idle time of the whole machine, or None when the platform cannot say."""
    try:
        if sys.platform == 'win32':
            import ctypes
            from ctypes import wintypes
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [('cbSize', wintypes.UINT), ('dwTime', wintypes.DWORD)]
            info = LASTINPUTINFO(); info.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
                return None
            return max(0, (ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF)/1000
        if sys.platform == 'darwin':
            import Quartz
            return float(Quartz.CGEventSourceSecondsSinceLastEventType(1, 0xFFFFFFFF))
    except Exception:
        return None
    return None


class PetBehavior(C.QObject):
    def __init__(self, gear, window=None, idle_source=seconds_since_input):
        super().__init__(gear)
        self.gear = gear
        self.window = window
        self.idle_source = idle_source
        self.quiet = False
        self.fade = True
        self.sleeping = False
        self.last_hover = 0.
        self.last_touch = time.monotonic()
        self.look_until = 0.
        self.next_action_at = self._later()
        self.timer = C.QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    # ── inputs from the UI ──────────────────────────────────────
    def touched(self):
        """Any interaction with the companion itself (hover, click, drag)."""
        self.last_touch = time.monotonic()
        if self.sleeping:
            self.wake()
        self.gear.pet.opacity_target = 1.

    def hover(self):
        """True when the greeting wave may play now."""
        self.touched()
        now = time.monotonic()
        if now - self.last_hover < HOVER_COOLDOWN_S or self.panel_open():
            return False
        self.last_hover = now
        return True

    def bubble_shown(self, side):
        """`side` is where the bubble sits relative to the doll: 'left'/'right'."""
        self.gear.pet.look = 8. if side == 'right' else -8.

    def bubble_hidden(self):
        if time.monotonic() >= self.look_until:
            self.gear.pet.look = 0.

    # ── state ─────────────────────────────────────────────────
    def panel_open(self):
        panel = getattr(self.window, 'panel', None)
        return panel is not None and panel.isVisible()

    def busy(self):
        state = getattr(self.window, 'state', None)
        return (getattr(self.gear, 'matching', False) or getattr(self.gear, 'game_background', False)
                or self.gear.pet.dragging or self.panel_open()
                or (state is not None and getattr(state, 'opened', False))
                or getattr(self.window, '_update_starting', False))

    def saving(self):
        choice = getattr(self.window, 'power_saving', None)
        return choice is not None and choice.isChecked()

    def _later(self):
        low, high = MICRO_GAP_S
        gap = random.uniform(low, high)
        return time.monotonic() + (gap*2 if self.saving() else gap)

    def sleep(self):
        if self.sleeping or not self.gear.pet.enabled:
            return
        self.sleeping = True
        self.gear.pet.look = 0.
        self.gear.pet.play('doze')

    def wake(self):
        if not self.sleeping:
            return
        self.sleeping = False
        pet = self.gear.pet
        if pet.enabled and pet.mood == 'doze':
            pet.mood = 'idle'     # play() refuses nothing here; make the switch explicit
            pet.play('wake')
        self.next_action_at = self._later()

    def tick(self):
        pet = self.gear.pet
        if not pet.enabled:
            return
        now = time.monotonic()
        idle = self.idle_source()
        busy = self.busy()
        # Doze: the whole machine has been quiet, not just the companion.
        if self.sleeping:
            if (idle is not None and idle < 2) or busy:
                self.wake()
            return
        if idle is not None and idle >= DOZE_AFTER_S and not busy and not self.quiet:
            self.sleep()
            return
        # Idle fade: only the companion has been left alone.
        if self.fade and not busy and now - self.last_touch >= FADE_AFTER_S and not self.panel_open():
            pet.opacity_target = FADE_TO
        else:
            pet.opacity_target = 1.
        # Head turn towards the cursor ends on its own.
        if self.look_until and now >= self.look_until:
            self.look_until = 0.
            toast = getattr(self.window, 'toast', None)
            if toast is None or not toast.isVisible():
                pet.look = 0.
        if busy or self.quiet or pet.mood != 'idle' or now < self.next_action_at:
            return
        action = random.choice(MICRO_ACTIONS)
        if action == 'look':
            self.look_at_cursor()
        else:
            pet.play(action)
        self.next_action_at = self._later()

    def look_at_cursor(self):
        """Turn the head towards the pointer for a moment, if it is nearby."""
        pet = self.gear.pet
        if pet.look != 0.:
            return
        cursor = G.QCursor.pos()
        head = self.gear.mapToGlobal(C.QPoint(self.gear.width()//2, self.gear.height()//3))
        dx = cursor.x() - head.x()
        if abs(dx) < 40 or abs(dx) > 900:
            return
        pet.look = max(-14., min(14., dx/40.))
        self.look_until = time.monotonic() + 2.5
        if pet.timer.isActive():
            pet.button.update()
