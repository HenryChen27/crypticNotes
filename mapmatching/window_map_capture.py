"""Nonblocking Windows window snapshots in physical screen coordinates."""
import ctypes
import threading
import time
import cv2

_capture_denied=False
_capture_slots=threading.BoundedSemaphore(2)

def capture_denied(error):
    text=str(error).lower()
    return isinstance(error,PermissionError) or any(marker in text for marker in (
        '0x80070005','e_accessdenied','access is denied','access denied','permission denied',
        'deniedbyuser','accessdenied','not authorized','permission was denied','user declined','user denied','0x800704c7','拒绝访问','拒绝授权'))

def allow_capture_retry():
    global _capture_denied
    _capture_denied=False

def ensure_capture_allowed():
    if _capture_denied:raise PermissionError('截图授权未完成，请允许权限后点击重新识别')



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
        global _capture_denied
        ensure_capture_allowed()
        from windows_capture import WindowsCapture
        if not _capture_slots.acquire(blocking=False):raise RuntimeError('截图资源仍在回收，请稍后重试')
        self.lock = threading.Lock()
        self._stop_requested = threading.Event()
        self._frame_claimed = False
        self._started_at = time.monotonic()
        self.result = None
        self.error = None
        try:
            self.capture = WindowsCapture(window_hwnd=int(hwnd), cursor_capture=False,
                                          draw_border=False, secondary_window=False)
        except Exception as exc:
            _capture_slots.release()
            if capture_denied(exc):
                _capture_denied=True
                raise PermissionError('截图授权未完成，请允许权限后点击重新识别') from exc
            raise

        @self.capture.event
        def on_frame_arrived(frame, control):
            # Native stop is asynchronous. Drivers may deliver more callbacks
            # before shutdown completes; a snapshot must copy at most one frame.
            with self.lock:
                if self._frame_claimed or self._stop_requested.is_set():
                    return
                self._frame_claimed = True
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

        try:
            self.control = self.capture.start_free_threaded()
        except Exception as exc:
            self.capture.frame_handler=None;self.capture.closed_handler=None;self.capture.capture=None
            self.capture=None;_capture_slots.release()
            if capture_denied(exc):
                _capture_denied=True
                raise PermissionError('截图授权未完成，请允许权限后点击重新识别') from exc
            raise
        # Keep callback owners alive until the native thread has actually exited.
        # Then break native/Python callback cycles, including the full-size result.
        threading.Thread(target=self._release_capture,daemon=True,name='capture-release').start()

    def _release_capture(self):
        control=self.control
        joined=False
        try:
            deadline=time.monotonic()+3
            while not self._stop_requested.wait(.02):
                if control.is_finished():break
                if time.monotonic()>=deadline:break
            if not control.is_finished():
                if time.monotonic()-self._started_at>=1:
                    from .src.ui_trace import trace
                    trace('window_capture_stop_pending',elapsed_ms=round((time.monotonic()-self._started_at)*1000),frame_received=self.result is not None)
                control.stop()
            control.wait()
            joined=True
        except Exception as exc:
            if self.error is None:self.error=str(exc)
        finally:
            if not joined:
                from .src.ui_trace import trace
                trace('window_capture_release_failed',error=self.error)
                # Keep ownership and the slot if a driver fails to stop. Never
                # free callbacks under a potentially live native thread.
                return
            capture=self.capture
            if capture is not None:
                capture.frame_handler=None
                capture.closed_handler=None
                capture.capture=None
            self.capture=None
            self.control=None
            _capture_slots.release()
            elapsed=time.monotonic()-self._started_at
            if elapsed>=1:
                from .src.ui_trace import trace
                trace('window_capture_slow_release',elapsed_ms=round(elapsed*1000),error=self.error)

    def stop(self):
        # Never join a native capture thread on the Qt GUI thread.
        self._stop_requested.set()


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
