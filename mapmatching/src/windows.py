"""Windows desktop capture. Hotkeys are observed, never swallowed/injected."""
import ctypes
import numpy as np
import win32gui
import win32api
import win32ui
import win32con

user32 = ctypes.windll.user32


def dpi_aware():
    # Per-monitor V2, before creating any windows.
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))


def client_rect(hwnd):
    left,top,right,bottom = win32gui.GetClientRect(hwnd)
    x,y = win32gui.ClientToScreen(hwnd,(left,top))
    return x,y,right-left,bottom-top


def monitor_rect(hwnd):
    """Physical pixel bounds of the screen containing the active window."""
    monitor = win32api.MonitorFromWindow(hwnd,win32con.MONITOR_DEFAULTTOPRIMARY)
    x0,y0,x1,y1 = win32api.GetMonitorInfo(monitor)['Monitor']
    return x0,y0,x1-x0,y1-y0


def capture(rect):
    x,y,w,h = rect
    if w < 100 or h < 100:
        raise ValueError('游戏窗口过小或已最小化')
    desktop = win32gui.GetDC(0)
    dc = win32ui.CreateDCFromHandle(desktop)
    memory = dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    try:
        bitmap.CreateCompatibleBitmap(dc,w,h)
        memory.SelectObject(bitmap)
        memory.BitBlt((0,0),(w,h),dc,(x,y),win32con.SRCCOPY)
        return np.frombuffer(bitmap.GetBitmapBits(True),np.uint8).reshape(h,w,4)[:,:,:3].copy()
    finally:
        memory.DeleteDC()
        dc.DeleteDC()
        win32gui.ReleaseDC(0,desktop)
        win32gui.DeleteObject(bitmap.GetHandle())


def place_overlay(hwnd, rect):
    x,y,w,h = rect
    style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    win32gui.SetWindowLong(hwnd,win32con.GWL_EXSTYLE,style | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_NOACTIVATE | win32con.WS_EX_TOOLWINDOW)
    win32gui.SetWindowPos(hwnd,win32con.HWND_TOPMOST,x,y,w,h,win32con.SWP_NOACTIVATE)


class Keys:
    def __init__(self):
        self.down = set()
        self.toggle_key = 0x47

    def edges(self):
        pressed = {key for key in (self.toggle_key,0x1B) if user32.GetAsyncKeyState(key) & 0x8000}
        rising = pressed - self.down
        self.down = pressed
        return rising
