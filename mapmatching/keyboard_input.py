"""Passive keyboard Raw Input; only configured shortcut edges are retained."""
import ctypes
import time
from ctypes import wintypes
from PySide6 import QtCore as C
from .mouse_input import (MouseWatcher,RawInputFilter,RAWINPUTDEVICE,RAWINPUTHEADER,user32,
                         RID_INPUT,RIDEV_INPUTSINK,RIDEV_REMOVE)


class RAWKEYBOARD(ctypes.Structure):
    _fields_=[('MakeCode',wintypes.USHORT),('Flags',wintypes.USHORT),
              ('Reserved',wintypes.USHORT),('VKey',wintypes.USHORT),
              ('Message',wintypes.UINT),('ExtraInformation',wintypes.ULONG)]


class KeyboardWatcher(MouseWatcher):
    def __init__(self,keys):
        super().__init__(keys)
        self.hwnd = None
        self.last_check = 0.0
        self.received = 0
        self.messages = 0
        self.read_errors = 0
        self.shortcut_events = 0
        self.last_read_error = None
        self.last_report = 0.0

    def report(self, foreground):
        """Periodic counts only: never record ordinary keys or typed text."""
        now = time.monotonic()
        if now - self.last_report < 5.0:
            return
        self.last_report = now
        # An idle machine produced an identical line every 5s. Only write when
        # a counter, the foreground window or the registration state moved.
        state = (foreground, self.hwnd, self.ok, self.messages, self.received,
                 self.read_errors, self.shortcut_events, self.last_error)
        if state == getattr(self, '_last_health', None):
            return
        self._last_health = state
        from .src.ui_trace import trace
        watched = {self.keys.toggle_key, self.keys.hide_key, self.keys.close_key}
        trace('keyboard_health', schema=2, foreground=foreground, target=self.hwnd,
              registered=self.ok, messages=self.messages, parsed=self.received,
              read_errors=self.read_errors, read_error=self.last_read_error,
              shortcuts=self.shortcut_events, registration_error=self.last_error,
              held=sorted(self.keys.down & watched))

    def _read_failed(self, stage, result, size):
        self.read_errors += 1
        self.last_read_error = dict(stage=stage, result=result, size=size,
                                    winerror=ctypes.get_last_error())

    def maintain(self, hwnd):
        """Repair registrations replaced by another component or a recreated HWND."""
        now = time.monotonic()
        if now - self.last_check < 1.0:
            return
        self.last_check = now
        count = wintypes.UINT()
        api = user32.GetRegisteredRawInputDevices
        api.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), ctypes.POINTER(wintypes.UINT), wintypes.UINT]
        api.restype = wintypes.UINT
        size = ctypes.sizeof(RAWINPUTDEVICE)
        error = 0xFFFFFFFF
        result = api(None, ctypes.byref(count), size)
        if result == error:
            self.last_error = 'GetRegisteredRawInputDevices: '+str(ctypes.get_last_error())
            return
        devices = (RAWINPUTDEVICE * count.value)()
        result = api(devices, ctypes.byref(count), size)
        if result == error:
            self.last_error = 'GetRegisteredRawInputDevices: '+str(ctypes.get_last_error())
            return
        owner = next((d for d in devices[:result] if d.usUsagePage == 1 and d.usUsage == 6), None)
        if owner is None or owner.hwndTarget != hwnd or not owner.dwFlags & RIDEV_INPUTSINK:
            from .src.ui_trace import trace
            previous = int(owner.hwndTarget or 0) if owner else None
            self.keys.raw_keyboard = self.register(hwnd)
            trace('keyboard_registration_repaired',previous=previous,target=hwnd,
                  ok=self.ok,error=self.last_error,received=self.received)

    def register(self,hwnd):
        app=C.QCoreApplication.instance()
        device=RAWINPUTDEVICE(1,6,RIDEV_INPUTSINK,wintypes.HWND(hwnd))
        if app is None or not user32.RegisterRawInputDevices(ctypes.byref(device),1,ctypes.sizeof(device)):
            self.ok=False
            self.last_error='RegisterRawInputDevices: '+str(ctypes.get_last_error())
            return False
        # 不再自己装 filter：共用 RawInputFilter，一条 WM_INPUT 只读一次。
        RawInputFilter.shared().attach(keyboard=self)
        self._app=app;self.ok=True;self.hwnd=hwnd;self.last_error=None
        return True

    def release(self):
        if self._app is not None:
            RawInputFilter.shared().detach(keyboard=self);self._app=None
        if self.ok:
            device=RAWINPUTDEVICE(1,6,RIDEV_REMOVE,None)
            user32.RegisterRawInputDevices(ctypes.byref(device),1,ctypes.sizeof(device))
        self.ok=False

    def _read(self,handle):
        """直接调用时的入口（测试与兼容）：一次读取，只处理键盘包。"""
        self.messages += 1
        size=wintypes.UINT(len(self._buffer));hs=ctypes.sizeof(RAWINPUTHEADER)
        result=user32.GetRawInputData(wintypes.HANDLE(handle),RID_INPUT,self._buffer,ctypes.byref(size),hs)
        if result==0xFFFFFFFF:
            self._read_failed('size',result,size.value)
            return
        if result<hs:
            self._read_failed('header_size',result,size.value)
            return
        if RAWINPUTHEADER.from_buffer(self._buffer).dwType!=1:return
        self._keyboard_packet(self._buffer,result,counted=True)

    def _keyboard_packet(self,buffer,copied,counted=False):
        if not counted:self.messages += 1
        hs=ctypes.sizeof(RAWINPUTHEADER)
        if copied<hs+ctypes.sizeof(RAWKEYBOARD):
            self._read_failed('keyboard_size',copied,copied)
            return
        self.received += 1
        key=RAWKEYBOARD.from_buffer(buffer,hs)
        if int(key.VKey) in (self.keys.toggle_key,self.keys.hide_key,self.keys.close_key):
            self.shortcut_events += 1
        self.keys.raw_edge(int(key.VKey),bool(key.Flags&1))
