"""macOS screen capture and window helpers used by the shared desktop UI."""
from __future__ import annotations

import os
import numpy as np
from AppKit import NSWorkspace, NSScreen
import Quartz
from .ui_trace import trace

_capture_window = None


def _select_window(window_id, pid, rect):
    global _capture_window
    _capture_window = (int(window_id), int(pid), tuple(rect))
    trace('mac_capture_target',window_id=int(window_id),pid=int(pid),rect=list(rect))


def dpi_aware():
    # A floating utility must not activate a regular Dock application and move
    # the user out of the game's full-screen Space.
    from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
    NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)


def bind_local_window(handle):
    panel = _panel_for(handle)
    if panel is None:
        raise RuntimeError('无法绑定本地截图窗口')
    rect = client_rect(handle)
    _select_window(panel.windowNumber(),os.getpid(),rect)
    return rect


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
            candidates.append((rect,int(window.get('kCGWindowNumber',0))))
    if not candidates:
        raise RuntimeError('未找到目标应用的可见窗口；请点击游戏窗口后重试')
    rect,window_id = max(candidates,key=lambda item:item[0][2]*item[0][3])
    _select_window(window_id,target,rect)
    return rect


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
    permission = bool(Quartz.CGPreflightScreenCaptureAccess())
    trace('mac_capture_permission',granted=permission,pid=os.getpid())
    if not permission:
        Quartz.CGRequestScreenCaptureAccess()
        raise PermissionError('当前进程没有屏幕录制权限；请授权当前版本的加页手记后完全退出并重新打开')
    if _capture_window is None or tuple(rect) != _capture_window[2]:
        raise RuntimeError('截图目标未绑定，已停止截图以避免读取桌面背景')
    from .macos_capture import capture_window
    window_id,pid,_ = _capture_window
    try:
        image = capture_window(window_id,pid)
    except Exception as error:
        trace('mac_capture_failed',window_id=window_id,pid=pid,error=str(error))
        raise
    width, height = Quartz.CGImageGetWidth(image), Quartz.CGImageGetHeight(image)
    provider = Quartz.CGImageGetDataProvider(image)
    raw = bytes(Quartz.CGDataProviderCopyData(provider))
    row_bytes = Quartz.CGImageGetBytesPerRow(image)
    frame = np.frombuffer(raw, np.uint8).reshape(height, row_bytes)[:, :width*4].reshape(height,width,4)
    trace('mac_capture_complete',backend='ScreenCaptureKit',window_id=window_id,
          pid=pid,width=width,height=height)
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


def _appkit(name, value):
    """AppKit constant, or its documented value.

    pyobjc has been moving NS_OPTIONS/NS_ENUM to enum classes; the module-level
    names still exist, but a lookup failing must not take the overlay down with
    it, and these are plain NSInteger values either way.
    """
    import AppKit
    return getattr(AppKit, name, value)


def keep_floating(window):
    try:
        panel = _panel_for(window)
    except Exception:
        panel = None
    if panel is None:
        from .ui_trace import trace
        trace('overlay_panel_missing',window=int(window))
        return False
    try:
        panel.setHidesOnDeactivate_(False)
        panel.setCanHide_(False)
        panel.setLevel_(_appkit('NSScreenSaverWindowLevel', 1000))
        panel.setCollectionBehavior_(
            _appkit('NSWindowCollectionBehaviorCanJoinAllSpaces', 1 << 0) |
            _appkit('NSWindowCollectionBehaviorStationary', 1 << 4) |
            _appkit('NSWindowCollectionBehaviorFullScreenAuxiliary', 1 << 8))
        import AppKit
        join = getattr(AppKit,'NSWindowCollectionBehaviorCanJoinAllApplications',None)
        if join is not None:
            panel.setCollectionBehavior_(int(panel.collectionBehavior()) | int(join))
        trace('mac_panel_configured',window=int(window),level=int(panel.level()),
              behavior=int(panel.collectionBehavior()))
    except Exception as error:
        # Never let a cosmetic hardening pass break the overlay it is meant to
        # rescue; the window simply stays as Qt left it.
        _panels.pop(int(window), None)
        trace('mac_panel_failed',window=int(window),error=str(error))
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
