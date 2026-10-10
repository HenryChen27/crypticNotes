"""Passive keyboard Raw Input; only configured shortcut edges are retained."""
import ctypes
import time
from ctypes import wintypes
from PySide6 import QtCore as C
from .mouse_input import (MouseWatcher,RAWINPUTDEVICE,RAWINPUTHEADER,user32,
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
        if self._app is None:
            app.installNativeEventFilter(self)
        self._app=app;self.ok=True;self.hwnd=hwnd;self.last_error=None
        return True

    def release(self):
        if self._app is not None:
            self._app.removeNativeEventFilter(self);self._app=None
        if self.ok:
            device=RAWINPUTDEVICE(1,6,RIDEV_REMOVE,None)
            user32.RegisterRawInputDevices(ctypes.byref(device),1,ctypes.sizeof(device))
        self.ok=False

    def _read(self,handle):
        self.messages += 1
        size=wintypes.UINT(0);hs=ctypes.sizeof(RAWINPUTHEADER)
        result=user32.GetRawInputData(wintypes.HANDLE(handle),RID_INPUT,None,ctypes.byref(size),hs)
        if result!=0:
            self._read_failed('size',result,size.value)
            return
        if size.value<hs:
            self._read_failed('header_size',0,size.value)
            return
        buffer=ctypes.create_string_buffer(size.value)
        result=user32.GetRawInputData(wintypes.HANDLE(handle),RID_INPUT,buffer,ctypes.byref(size),hs)
        if result!=size.value:
            self._read_failed('data',result,size.value)
            return
        if RAWINPUTHEADER.from_buffer(buffer).dwType!=1:return
        if size.value<hs+ctypes.sizeof(RAWKEYBOARD):
            self._read_failed('keyboard_size',result,size.value)
            return
        self.received += 1
        key=RAWKEYBOARD.from_buffer(buffer,hs)
        if int(key.VKey) in (self.keys.toggle_key,self.keys.hide_key,self.keys.close_key):
            self.shortcut_events += 1
        self.keys.raw_edge(int(key.VKey),bool(key.Flags&1))
