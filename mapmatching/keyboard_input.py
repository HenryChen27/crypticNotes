"""Passive keyboard Raw Input; only configured shortcut edges are retained."""
import ctypes
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
        super().__init__()
        self.keys=keys

    def register(self,hwnd):
        app=C.QCoreApplication.instance()
        device=RAWINPUTDEVICE(1,6,RIDEV_INPUTSINK,wintypes.HWND(hwnd))
        if app is None or not user32.RegisterRawInputDevices(ctypes.byref(device),1,ctypes.sizeof(device)):
            return False
        app.installNativeEventFilter(self);self._app=app;self.ok=True
        return True

    def release(self):
        if self._app is not None:
            self._app.removeNativeEventFilter(self);self._app=None
        if self.ok:
            device=RAWINPUTDEVICE(1,6,RIDEV_REMOVE,None)
            user32.RegisterRawInputDevices(ctypes.byref(device),1,ctypes.sizeof(device))
        self.ok=False

    def _read(self,handle):
        size=wintypes.UINT(0);hs=ctypes.sizeof(RAWINPUTHEADER)
        if user32.GetRawInputData(wintypes.HANDLE(handle),RID_INPUT,None,ctypes.byref(size),hs)!=0:
            return
        if size.value<hs+ctypes.sizeof(RAWKEYBOARD):return
        buffer=ctypes.create_string_buffer(size.value)
        if user32.GetRawInputData(wintypes.HANDLE(handle),RID_INPUT,buffer,ctypes.byref(size),hs)!=size.value:return
        if RAWINPUTHEADER.from_buffer(buffer).dwType!=1:return
        key=RAWKEYBOARD.from_buffer(buffer,hs)
        self.keys.raw_edge(int(key.VKey),bool(key.Flags&1))
