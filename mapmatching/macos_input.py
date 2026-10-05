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
_VK_TO_CG.update({0x14:57,0x90:71,0x2D:114,0x2E:117,0x24:115,0x23:119,
    0x21:116,0x22:121,0xBD:27,0xBB:24,0xDB:33,0xDD:30,0xDC:42,
    0xBA:41,0xDE:39,0xBC:43,0xBE:47,0xBF:44,0xC0:50,
    0x6A:67,0x6B:69,0x6D:78,0x6E:65,0x6F:75})
_VK_TO_CG.update({0x60+i:code for i,code in enumerate((82,83,84,85,86,87,88,89,91,92))})
_VK_TO_CG.update({0x7C+i:code for i,code in enumerate((105,107,113,106,64,79,80,90))})


def pressed_virtual_keys(vk):
    if vk in (0x01,0x02,0x04,0x05,0x06):
        button={0x01:0,0x02:1,0x04:2,0x05:3,0x06:4}[vk]
        return bool(Quartz.CGEventSourceButtonState(Quartz.kCGEventSourceStateCombinedSessionState,button))
    code=_VK_TO_CG.get(vk)
    return bool(code is not None and Quartz.CGEventSourceKeyState(
        Quartz.kCGEventSourceStateCombinedSessionState,code))


def request_permission():
    """Ask once for Input Monitoring.

    Polling key state is a *passive* read: it never raises the system prompt,
    and without the prompt macOS never records the app in 系统设置 → 隐私与安全性
    → 输入监控 at all -- the app cannot be found in that list, and every poll
    silently returns False so the hotkeys just do nothing.  Only an explicit
    request both shows the prompt and creates the list entry.

    Older pyobjc builds predate the ListenEvent helpers; a missing symbol must
    not take the watcher down, so the shortcut keys simply keep not working.
    """
    try:
        if not Quartz.CGPreflightListenEventAccess():
            Quartz.CGRequestListenEventAccess()
    except AttributeError:
        pass


class KeyboardWatcher:
    def __init__(self,keys): self.keys=keys; self.monitor=None
    def register(self,_window):
        request_permission()
        # Global monitor observes events, never consumes them. It retains quick
        # taps which polling can miss while a screenshot is being acquired.
        try:
            from AppKit import NSEvent
            reverse={code:vk for vk,code in _VK_TO_CG.items()}
            def observe(event):
                kind=int(event.type())
                if kind==12:
                    key=reverse.get(int(event.keyCode()))
                    if key is not None and (key==0x14 or pressed_virtual_keys(key)):
                        self.keys.raw_edge(key,False)
                        self.keys.raw_edge(key,True)
                    return
                if kind in (10,11):
                    if kind==10 and event.isARepeat(): return
                    key=reverse.get(int(event.keyCode()))
                else:
                    key={1:0x02,2:0x04,3:0x05,4:0x06}.get(int(event.buttonNumber()))
                if key is not None:self.keys.raw_edge(key,kind in (4,11,26))
            self.monitor=NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                (1<<3)|(1<<4)|(1<<10)|(1<<11)|(1<<12)|(1<<25)|(1<<26),observe)
        except Exception:
            pass  # Polling remains available on older PyObjC installations.
        return True
    def release(self):
        if self.monitor is not None:
            from AppKit import NSEvent
            NSEvent.removeMonitor_(self.monitor)
            self.monitor=None


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
