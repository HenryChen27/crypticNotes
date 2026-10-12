"""Low-rate, window-bound scene change detection for optional mini-games."""
import time
import cv2
import numpy as np
from PySide6 import QtCore as C

CHANGE_THRESHOLD=.25

def sample_frame(pixels):
    if pixels is None or pixels.ndim!=3 or min(pixels.shape[:2])<32:return None
    image=cv2.GaussianBlur(cv2.resize(pixels[:,:,:3],(320,180),interpolation=cv2.INTER_AREA),(5,5),0)
    if image.std()<2 or image.mean()<3:return None
    return image.astype(np.float32)

def difference(before,after):
    delta=np.abs(before-after).mean(axis=2)
    return {'changed_fraction':float((delta>18).mean()),'mean_delta':float(delta.mean()),'similarity':float(1-(delta>18).mean())}

class SceneDetector:
    def __init__(self):self.reset()
    def reset(self):self.reference=None;self.shape=None;self.stable=0;self.armed=False;self.triggered=False
    def feed(self,pixels):
        frame=sample_frame(pixels)
        if frame is None:return None
        shape=pixels.shape[:2]
        if self.shape is not None and any(abs(a-b)/max(1,b)>.02 for a,b in zip(shape,self.shape)):
            self.reset();self.shape=shape
        else:self.shape=shape
        if self.reference is None:self.reference=frame;return None
        score=difference(self.reference,frame)
        if not self.armed:
            self.stable=self.stable+1 if score['changed_fraction']<.08 and score['mean_delta']<6 else 0
            self.reference=frame
            self.armed=self.stable>=1
            return None
        if not self.triggered and score['changed_fraction']>=CHANGE_THRESHOLD and score['mean_delta']>=12:
            self.triggered=True;return score
        if score['changed_fraction']<.08 and score['mean_delta']<6:
            self.reference=.9*self.reference+.1*frame
        return None

def find_game_window(preferred=None):
    import win32gui
    def eligible(hwnd):
        if not hwnd or not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):return False
        title=win32gui.GetWindowText(hwnd).strip().lower()
        return '第五人格' in title or title in ('identity v','identityv')
    if eligible(preferred):return int(preferred)
    candidates=[]
    def visit(hwnd,_):
        if eligible(hwnd):
            l,t,r,b=win32gui.GetClientRect(hwnd)
            if r-l>=320 and b-t>=240:candidates.append(((r-l)*(b-t),hwnd))
    win32gui.EnumWindows(visit,None)
    return max(candidates)[1] if candidates else None

class WindowSceneWatch(C.QObject):
    changed=C.Signal(object)
    failed=C.Signal(str)
    def __init__(self,hwnd,parent=None):
        super().__init__(parent);self.hwnd=int(hwnd);self.detector=SceneDetector();self.control=None;self.active=False;self.last_frame=0
    def start(self):
        from windows_capture import WindowsCapture
        import win32gui
        self.active=True
        capture=WindowsCapture(window_hwnd=self.hwnd,cursor_capture=False,draw_border=False,secondary_window=False,minimum_update_interval=1500)
        @capture.event
        def on_frame_arrived(frame,capture_control):
            if not self.active:capture_control.stop();return
            now=time.monotonic()
            if now-self.last_frame<1.4:return
            self.last_frame=now
            if not win32gui.IsWindow(self.hwnd) or win32gui.IsIconic(self.hwnd):self.detector.reset();return
            try:
                score=self.detector.feed(frame.frame_buffer)
                if score is not None:self.changed.emit(score)
            except Exception as error:self.failed.emit(str(error));capture_control.stop()
        @capture.event
        def on_closed():
            if self.active:self.failed.emit('第五人格窗口已关闭，画面检测已停止')
        self.capture=capture
        try:self.control=capture.start_free_threaded()
        except Exception:self.active=False;raise
    def stop(self):
        self.active=False
        if self.control is not None:
            try:self.control.stop()
            except Exception:pass
            self.control=None
