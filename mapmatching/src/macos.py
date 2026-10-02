"""macOS screen capture and window helpers used by the shared desktop UI."""
from __future__ import annotations

import os
import numpy as np
from AppKit import NSWorkspace, NSScreen
import Quartz


def dpi_aware():
    pass


def _screen_rect():
    bounds = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
    return int(bounds.origin.x), int(bounds.origin.y), int(bounds.size.width), int(bounds.size.height)


def monitor_rect(target):
    # External targets are application PIDs, not Qt window handles. Capture
    # their visible main window: the primary display may contain only desktop
    # when the game is windowed or running on an external monitor.
    windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID) or []
    candidates = []
    for window in windows:
        if (int(window.get('kCGWindowOwnerPID',0)) != target
                or int(window.get('kCGWindowLayer',-1)) != 0):
            continue
        bounds = window.get('kCGWindowBounds',{})
        rect = tuple(round(bounds.get(key,0)) for key in ('X','Y','Width','Height'))
        if rect[2] >= 100 and rect[3] >= 100:
            candidates.append(rect)
    return max(candidates,key=lambda r:r[2]*r[3]) if candidates else _screen_rect()


def client_rect(_window):
    from PySide6.QtWidgets import QApplication
    for widget in QApplication.topLevelWidgets():
        if int(widget.winId()) == int(_window):
            r = widget.geometry()
            return r.x(),r.y(),r.width(),r.height()
    return 0, 0, 0, 0


def mask_screen_rect(pixels, capture_rect, excluded_rect):
    x,y,w,h = capture_rect
    ex,ey,ew,eh = excluded_rect
    # Quartz rectangles use points; Retina captures contain backing pixels.
    ph,pw = pixels.shape[:2]
    sx,sy = pw/w,ph/h
    left,top = max(0,round((ex-x)*sx)),max(0,round((ey-y)*sy))
    right,bottom = min(pw,round((ex+ew-x)*sx)),min(ph,round((ey+eh-y)*sy))
    if right > left and bottom > top:
        pixels[top:bottom,left:right] = 0
    return pixels


def capture(rect):
    x,y,w,h = map(int, rect)
    if w < 100 or h < 100:
        raise ValueError('游戏窗口过小或已最小化')
    image = Quartz.CGWindowListCreateImage(
        Quartz.CGRectMake(x,y,w,h),
        Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGNullWindowID,
        Quartz.kCGWindowImageDefault)
    if image is None:
        raise PermissionError('无法读取屏幕，请在系统设置中允许“屏幕录制”权限后重启应用')
    width, height = Quartz.CGImageGetWidth(image), Quartz.CGImageGetHeight(image)
    provider = Quartz.CGImageGetDataProvider(image)
    raw = bytes(Quartz.CGDataProviderCopyData(provider))
    row_bytes = Quartz.CGImageGetBytesPerRow(image)
    frame = np.frombuffer(raw, np.uint8).reshape(height, row_bytes)[:, :width*4].reshape(height,width,4)
    # CGWindow images use premultiplied BGRA on current Intel and Apple Silicon Macs.
    return frame[:,:,:3].copy()


def place_overlay(_window, rect):
    from PySide6 import QtCore as C
    from PySide6 import QtWidgets as W
    # winId() is an NSView pointer on macOS, but it is still stable enough to
    # identify the exact Qt widget.  Selecting the first input-transparent
    # top-level window could resize the toast instead of the map overlay.
    for widget in W.QApplication.topLevelWidgets():
        if int(widget.winId()) == int(_window):
            widget.setGeometry(*map(int,rect))
            widget.raise_()
            return
    # Returning silently here used to mean "matched fine, nothing on screen" with
    # no way to tell it apart from a window AppKit kept off screen.
    from .ui_trace import trace
    trace('overlay_place_missing',window=int(_window),rect=list(map(int,rect)))


# Qt::Tool becomes an NSPanel on macOS, and Qt sets hidesOnDeactivate on it, so
# AppKit pulls the overlay off screen the moment the game takes focus back:
# capture and matching keep working while nothing is ever drawn.  Qt only skips
# that when WA_MacAlwaysShowToolWindow was set before the window was created,
# and even then the panel stays at NSFloatingWindowLevel.  Add the AppKit half
# here: never hide, float above a full-screen game, and join its Space.
_panels = {}


def _panel_for(window):
    import objc
    from AppKit import NSApp
    key = int(window)
    if key in _panels:
        return _panels[key]
    panel = None
    for candidate in NSApp.windows() or []:
        view = candidate.contentView()
        if view is not None and objc.pyobjc_id(view) == key:
            panel = candidate
            break
    if panel is None:
        try:
            import ctypes
            # pyobjc takes a ctypes.c_void_p here, not a bare int; the Qt winId
            # may be a subview rather than the window's content view.
            panel = objc.objc_object(c_void_p=ctypes.c_void_p(key)).window()
        except Exception:
            panel = None
    if panel is not None:
        _panels[key] = panel
        from .ui_trace import trace
        trace('overlay_panel_bound',window=key,level=int(panel.level()))
    return panel


def keep_floating(window):
    from AppKit import (NSScreenSaverWindowLevel,
                        NSWindowCollectionBehaviorCanJoinAllSpaces,
                        NSWindowCollectionBehaviorFullScreenAuxiliary,
                        NSWindowCollectionBehaviorStationary)
    panel = _panel_for(window)
    if panel is None:
        from .ui_trace import trace
        trace('overlay_panel_missing',window=int(window))
        return False
    try:
        panel.setHidesOnDeactivate_(False)
        panel.setCanHide_(False)
        panel.setLevel_(NSScreenSaverWindowLevel)
        panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces |
            NSWindowCollectionBehaviorFullScreenAuxiliary |
            NSWindowCollectionBehaviorStationary)
    except Exception:
        _panels.pop(int(window), None)
        return False
    return True


class _WindowAPI:
    own_window = 0

    @staticmethod
    def GetForegroundWindow():
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if not app:
            return 0
        pid=int(app.processIdentifier())
        return _WindowAPI.own_window if pid == os.getpid() else pid

    @staticmethod
    def IsWindow(pid):
        if not pid:
            return False
        try:
            os.kill(int(pid), 0)
            return True
        except OSError:
            return False

    @staticmethod
    def IsIconic(_pid):
        return False


window_api = _WindowAPI()


def activate_target(pid):
    """Return focus to the app the user was using before opening settings."""
    from AppKit import NSRunningApplication, NSApplicationActivateIgnoringOtherApps
    if not pid or pid == os.getpid() or pid == window_api.own_window:
        return False
    app = NSRunningApplication.runningApplicationWithProcessIdentifier_(int(pid))
    return bool(app and app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps))


class Keys:
    """Poll global key state without installing or swallowing an event tap."""
    def __init__(self):
        self.down=set(); self.toggle_key=0x47; self.hide_key=0x08
        self.raw_keyboard=False; self.raw_mouse=False

    def raw_edge(self, _key, _released):
        pass

    def edges(self):
        from mapmatching.macos_input import pressed_virtual_keys
        watched=(self.toggle_key,self.hide_key,0x1B)
        pressed={key for key in watched if pressed_virtual_keys(key)}
        rising=pressed-self.down
        self.down=pressed
        return rising
