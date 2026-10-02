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


def monitor_rect(_target):
    return _screen_rect()


def client_rect(_window):
    # Qt's winId is an NSView pointer rather than a CGWindowID. Returning an
    # empty exclusion is safe; the assistant uses a small translucent ball and
    # map matching already masks HUD-like regions.
    return 0, 0, 0, 0


def mask_screen_rect(pixels, capture_rect, excluded_rect):
    x,y,w,h = capture_rect
    ex,ey,ew,eh = excluded_rect
    left,top = max(0,ex-x),max(0,ey-y)
    right,bottom = min(w,ex+ew-x),min(h,ey+eh-y)
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
    # The caller has already shown the overlay; locate it by its transparent,
    # input-pass-through window flags and apply physical screen geometry.
    for widget in W.QApplication.topLevelWidgets():
        if widget.windowFlags() & C.Qt.WindowTransparentForInput:
            widget.setGeometry(*map(int,rect))
            widget.raise_()
            return


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
