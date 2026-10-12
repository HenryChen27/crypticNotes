"""Nonblocking Windows window snapshots in physical screen coordinates."""
import ctypes
import threading
import time
import cv2


def frame_rect(hwnd):
    import win32gui
    rect = (ctypes.c_long * 4)()
    result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        ctypes.c_void_p(hwnd), 9, ctypes.byref(rect), ctypes.sizeof(rect))
    left, top, right, bottom = tuple(rect) if result == 0 else win32gui.GetWindowRect(hwnd)
    return left, top, right-left, bottom-top


def normalize_frame(pixels, rect):
    w, h = rect[2:]
    if w < 100 or h < 100:
        raise ValueError('游戏窗口过小')
    pixels = pixels[:, :, :3].copy()
    if pixels.shape[:2] != (h, w):
        pixels = cv2.resize(pixels, (w, h), interpolation=cv2.INTER_LINEAR)
    return pixels


class WindowSnapshot:
    def __init__(self, hwnd):
        from windows_capture import WindowsCapture
        self.lock = threading.Lock()
        self.result = None
        self.error = None
        self.capture = WindowsCapture(window_hwnd=int(hwnd), cursor_capture=False,
                                      draw_border=False, secondary_window=False)

        @self.capture.event
        def on_frame_arrived(frame, control):
            try:
                rect = frame_rect(hwnd)
                pixels = normalize_frame(frame.frame_buffer, rect)
                with self.lock:
                    self.result = (pixels, rect)
            except Exception as exc:
                self.error = str(exc)
            finally:
                control.stop()

        @self.capture.event
        def on_closed():
            if self.result is None:
                self.error = '游戏窗口已关闭'

        self.control = self.capture.start_free_threaded()

    def stop(self):
        self.control.stop()


def capture_now(hwnd, timeout=2):
    """For background guards and final verification; never sample the desktop."""
    shot = WindowSnapshot(hwnd)
    try:
        deadline = time.monotonic()+timeout
        while shot.result is None and shot.error is None and time.monotonic()<deadline:
            time.sleep(.01)
        if shot.result is None:
            raise RuntimeError(shot.error or 'window capture timeout')
        return shot.result[0]
    finally:
        shot.stop()
