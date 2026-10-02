"""Passive macOS keyboard/mouse polling; never injects or consumes input."""
from __future__ import annotations
import time
import Quartz

# Windows virtual keys used by the shared settings UI -> macOS hardware codes.
_VK_TO_CG = {
    0x08:51, 0x09:48, 0x0D:36, 0x10:56, 0x11:59, 0x12:58, 0x1B:53,
    0x20:49, 0x25:123, 0x26:126, 0x27:124, 0x28:125,
}
_VK_TO_CG.update({0x41+i: code for i,code in enumerate(
    (0,11,8,2,14,3,5,4,34,38,40,37,46,45,31,35,12,15,1,17,32,9,13,7,16,6))})
_VK_TO_CG.update({0x30+i: code for i,code in enumerate((29,18,19,20,21,23,22,26,28,25))})
_VK_TO_CG.update({0x70+i: code for i,code in enumerate((122,120,99,118,96,97,98,100,101,109,103,111))})


def pressed_virtual_keys(vk):
    if vk in (0x01,0x02,0x04):
        button={0x01:0,0x02:1,0x04:2}[vk]
        return bool(Quartz.CGEventSourceButtonState(Quartz.kCGEventSourceStateCombinedSessionState,button))
    code=_VK_TO_CG.get(vk)
    return bool(code is not None and Quartz.CGEventSourceKeyState(
        Quartz.kCGEventSourceStateCombinedSessionState,code))


class KeyboardWatcher:
    def __init__(self,keys): self.keys=keys
    def register(self,_window): return True
    def release(self): pass


class MouseWatcher:
    WHEEL_HOLD=.12
    def __init__(self,keys=None):
        self.keys=keys; self.ok=False; self._left=False; self.last_wheel=0.0
    def register(self,_window): self.ok=True; return True
    def release(self): self.ok=False; self._left=False
    def interacting(self,now=None):
        return any(pressed_virtual_keys(v) for v in (0x01,0x02,0x04))
    def map_interacting(self): return pressed_virtual_keys(0x01)
    def window_at_cursor(self): return 0
