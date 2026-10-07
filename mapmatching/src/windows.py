"""Windows desktop capture. Hotkeys are observed, never swallowed/injected."""
import ctypes
import numpy as np
import win32gui
import win32api
import win32ui
import win32con

user32 = ctypes.windll.user32


def activate_target(hwnd):
    """Return focus after a user explicitly presses Re-identify."""
    if not hwnd or not win32gui.IsWindow(hwnd):
        return False
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd,win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        return win32gui.GetForegroundWindow() == hwnd
    except Exception:
        # Windows may deny focus activation. The UI still samples the visible
        # screen and keeps its normal map-visibility gate.
        return False


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


def mask_screen_rect(pixels, capture_rect, excluded_rect):
    """Mask an assistant window in physical screen coordinates, in place."""
    x,y,w,h = capture_rect
    ex,ey,ew,eh = excluded_rect
    left,top = max(0,ex-x),max(0,ey-y)
    right,bottom = min(w,ex+ew-x),min(h,ey+eh-y)
    if right>left and bottom>top:
        pixels[top:bottom,left:right] = 0
    return pixels


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


def keep_floating(_window):
    """Windows 上 HWND_TOPMOST 已经够用，这个钩子只为和 macOS 对称。"""
    return True


# 0x01~0x06 在任何键盘上都是鼠标键（左/右/中/侧1/侧2）。用来判断某个键的
# 按下态该由鼠标还是键盘的 Raw Input 负责。与 mouse_input.BUTTON_VKS 同源。
MOUSE_VKS = frozenset((0x01,0x02,0x04,0x05,0x06))


class Keys:
    def __init__(self):
        self.down = set()
        self.pending_edges = set()
        self.raw_down = set()
        self.poll_seen = set()
        self.close_key = 0x1B
        self.toggle_key = 0x47
        self.hide_key = 0x08  # Backspace
        # 两类设备各自是否注册上了 Raw Input。**必须分开记**：只用一个
        # raw_active 时，键盘注册成功、鼠标没注册上（或反过来）会让没注册的那类
        # 键永远等不到释放边，按下态一旦置上就再也清不掉 —— 症状是「这个快捷键
        # 按一次有反应，之后按多少次都没反应」。
        self.raw_keyboard = False
        self.raw_mouse = False

    def raw_edge(self,key,released):
        if key not in (self.toggle_key,self.hide_key,self.close_key):return
        if released:
            self.raw_down.discard(key)
            self.poll_seen.discard(key)
            self.down.discard(key)
        else:
            self.raw_down.add(key)
            if key not in self.down:
                self.down.add(key)
                self.pending_edges.add(key)

    def _raw_owns(self,key):
        return self.raw_mouse if key in MOUSE_VKS else self.raw_keyboard

    def edges(self):
        watched = (self.toggle_key,self.hide_key,self.close_key)
        pressed = {key for key in watched if user32.GetAsyncKeyState(key) & 0x8000}
        rising = (pressed - self.down) | self.pending_edges
        self.pending_edges.clear()
        for key in watched:
            if key in pressed:
                self.down.add(key)
                self.poll_seen.add(key)
            elif (not self._raw_owns(key) or key not in self.raw_down
                  or key in self.poll_seen):
                # 注册成功不等于每次都能收到 Raw Input。只收到轮询按下时，
                # 必须允许轮询释放；否则第一次之后会永久锁住。收到过轮询
                # 按下的本轮也可用它补漏 release。始终盲读的 Raw Input
                # 按住态仍保留，避免把键盘自动重复当成新的按下。
                self.down.discard(key)
                self.raw_down.discard(key)
                self.poll_seen.discard(key)
        return rising
