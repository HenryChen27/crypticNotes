"""被动观察鼠标按键与滚轮，只读取，绝不吞掉或合成任何输入。

机制是 Win32 Raw Input 的 RIDEV_INPUTSINK：注册在**本进程**上，不需要窗口在前台，
不装全局钩子、不 SendInput、不使用 RIDEV_NOLEGACY / RIDEV_CAPTUREMOUSE
（那两个会改变 legacy 消息的产生方式，等于干扰游戏收到的输入）。

Raw Input 给的是**边沿**（down/up 各一条），对「按住/松开」这种状态机天生脆弱：
漏掉一条 release 就会永久卡在按下态。所以叠加 GetAsyncKeyState 轮询做自愈兜底。
轮询在提权游戏上会被 UIPI 挡住（恒返回 0），因此只在**证明它看得见**之后才采信它；
那种情况下再叠一条 STUCK_TIMEOUT 时间兜底，免得卡死的按下态永远放不掉。
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import time

from PySide6 import QtCore as C

user32 = ctypes.WinDLL('user32', use_last_error=True)

WM_INPUT = 0x00FF
RID_INPUT = 0x10000003
RIM_TYPEMOUSE = 0
HID_USAGE_PAGE_GENERIC = 0x01
HID_USAGE_GENERIC_MOUSE = 0x02
RIDEV_INPUTSINK = 0x00000100
RIDEV_REMOVE = 0x00000001
GA_ROOT = 2

# Raw Input 的按键位（usButtonFlags）。按下/抬起成对出现。
BUTTON_EDGES = (
    (0x0001, 0x0002, 0x01),   # 左键   -> VK_LBUTTON
    (0x0004, 0x0008, 0x02),   # 右键   -> VK_RBUTTON
    (0x0010, 0x0020, 0x04),   # 中键   -> VK_MBUTTON
    (0x0040, 0x0080, 0x05),   # 侧键 1 -> VK_XBUTTON1
    (0x0100, 0x0200, 0x06),   # 侧键 2 -> VK_XBUTTON2
)
RI_MOUSE_WHEEL = 0x0400
RI_MOUSE_HWHEEL = 0x0800
BUTTON_VKS = (0x01, 0x02, 0x04, 0x05, 0x06)
BUTTON_MASK = 0x03FF   # 五个键的 down/up 位，不含滚轮


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [('usUsagePage', wintypes.USHORT),
                ('usUsage', wintypes.USHORT),
                ('dwFlags', wintypes.DWORD),
                ('hwndTarget', wintypes.HWND)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [('dwType', wintypes.DWORD),
                ('dwSize', wintypes.DWORD),
                ('hDevice', wintypes.HANDLE),
                ('wParam', wintypes.WPARAM)]


class RAWMOUSE(ctypes.Structure):
    # usFlags 之后有 2 字节对齐填充，ctypes 不会自己补，必须显式声明，
    # 否则后面所有字段都错位，读出来是垃圾值。
    _fields_ = [('usFlags', wintypes.USHORT),
                ('_pad', wintypes.USHORT),
                ('ulButtons', wintypes.ULONG),
                ('ulRawButtons', wintypes.ULONG),
                ('lLastX', wintypes.LONG),
                ('lLastY', wintypes.LONG),
                ('ulExtraInformation', wintypes.ULONG)]


class _RAWUNION(ctypes.Union):
    _fields_ = [('mouse', RAWMOUSE), ('_raw', ctypes.c_byte * 24)]


class RAWINPUT(ctypes.Structure):
    _fields_ = [('header', RAWINPUTHEADER), ('data', _RAWUNION)]


user32.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT, ctypes.c_void_p,
                                   ctypes.POINTER(wintypes.UINT), wintypes.UINT]
user32.GetRawInputData.restype = wintypes.UINT
user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT]
user32.RegisterRawInputDevices.restype = wintypes.BOOL
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND


class MouseWatcher(C.QAbstractNativeEventFilter):
    """观察鼠标按键/滚轮；只用 `interacting()` 对外表态。

    注册失败时 `ok=False`，`interacting()` 恒为 False（fail open）——
    一个静默失效的监听，远好于一个永远不恢复的叠图。
    """

    WHEEL_HOLD = 0.120     # 滚轮停多久算「停稳」
    STUCK_TIMEOUT = 30.0   # 持有按键却这么久没有任何边沿 -> 判定为丢了 release

    def __init__(self):
        super().__init__()
        self.ok = False
        self.buttons = set()
        self.last_wheel = 0.0
        self.last_edge = 0.0
        self._app = None
        self._poll_works = False
        self.last_error = None

    # ── 生命周期 ───────────────────────────────────────────────
    def register(self, hwnd):
        """在本进程注册鼠标 Raw Input。hwnd 只作为 INPUTSINK 的接收者，不需要前台。"""
        if self.ok:
            return True
        app = C.QCoreApplication.instance()
        if app is None:
            self.last_error = '没有 QApplication'
            return False
        device = RAWINPUTDEVICE(HID_USAGE_PAGE_GENERIC, HID_USAGE_GENERIC_MOUSE,
                                RIDEV_INPUTSINK, wintypes.HWND(hwnd))
        if not user32.RegisterRawInputDevices(ctypes.byref(device), 1, ctypes.sizeof(RAWINPUTDEVICE)):
            self.last_error = f'RegisterRawInputDevices 失败 (err={ctypes.get_last_error()})'
            return False
        app.installNativeEventFilter(self)
        self._app = app
        self.ok = True
        return True

    def release(self):
        if self._app is not None:
            try:
                self._app.removeNativeEventFilter(self)
            except (RuntimeError, TypeError):
                pass
            self._app = None
        if self.ok:
            # RIDEV_REMOVE 按文档必须配 hwndTarget=NULL。
            device = RAWINPUTDEVICE(HID_USAGE_PAGE_GENERIC, HID_USAGE_GENERIC_MOUSE, RIDEV_REMOVE, None)
            user32.RegisterRawInputDevices(ctypes.byref(device), 1, ctypes.sizeof(RAWINPUTDEVICE))
            self.ok = False
        self.buttons.clear()
        self.last_edge = self.last_wheel = 0.0

    # ── 消息入口 ───────────────────────────────────────────────
    def nativeEventFilter(self, eventType, message):
        # Qt 的 Windows 派发器会把同一条 WM_INPUT 投递两次
        # （先 windows_dispatcher_MSG 后 windows_generic_MSG），所以下面所有状态
        # 更新都必须是幂等的：按键存 set、滚轮存时间戳，绝不累加计数。
        try:
            if eventType in (b'windows_generic_MSG', b'windows_dispatcher_MSG'):
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_INPUT:
                    self._read(int(msg.lParam))
        except Exception as error:            # 绝不因为观察失败而打断 Qt 的事件派发
            self.last_error = str(error)
        return (False, 0)                     # PySide6 要求返回 (handled, result) 元组

    def _read(self, handle):
        size = wintypes.UINT(0)
        header_size = ctypes.sizeof(RAWINPUTHEADER)
        if user32.GetRawInputData(wintypes.HANDLE(handle), RID_INPUT, None,
                                  ctypes.byref(size), header_size) != 0:
            return
        if size.value < header_size + ctypes.sizeof(RAWMOUSE):
            return
        # 按实际长度开缓冲：键盘/RAWHID 事件也可能落到这里，长度不定。
        buffer = ctypes.create_string_buffer(size.value)
        if user32.GetRawInputData(wintypes.HANDLE(handle), RID_INPUT, buffer,
                                  ctypes.byref(size), header_size) != size.value:
            return
        raw = RAWINPUT.from_buffer(buffer)
        if raw.header.dwType != RIM_TYPEMOUSE:
            return
        flags = raw.data.mouse.ulButtons & 0xFFFF    # 低 16 位才是 usButtonFlags
        now = time.perf_counter()
        if flags & (RI_MOUSE_WHEEL | RI_MOUSE_HWHEEL):
            self.last_wheel = now
        if flags & BUTTON_MASK:                      # 任何按键边沿（按下或抬起）
            self.last_edge = now
        for down_bit, up_bit, vk in BUTTON_EDGES:
            if flags & down_bit:
                self.buttons.add(vk)
            elif flags & up_bit:
                self.buttons.discard(vk)

    # ── 查询 ───────────────────────────────────────────────────
    def interacting(self, now=None):
        if not self.ok:
            return False
        now = time.perf_counter() if now is None else now
        down = {vk for vk in BUTTON_VKS if user32.GetAsyncKeyState(vk) & 0x8000}
        if down:
            self._poll_works = True
            self.buttons |= down
        elif self._poll_works:
            # 轮询已证明看得见按键，它说「都松开了」就是权威 —— 自愈掉漏收的 release。
            self.buttons.clear()
        elif self.buttons and now - self.last_edge > self.STUCK_TIMEOUT:
            # 轮询帮不上忙时才启用的时间兜底：提权游戏下 UIPI 让它恒为 0，
            # 唯一的信息源就是 Raw Input，而边沿流漏一条 up（设备切换、独占全屏、
            # 截屏前那 60 ms 隐藏窗口）就会永久卡在按下态，叠图再也回不来。
            # 用「久到不可能是真的按住」把它放掉。全程不用计数器 ——
            # Qt 把每条 WM_INPUT 投递两次，累加必然翻倍。
            self.buttons.clear()
        # 轮询从没见过按键按下时不作数：提权游戏下 UIPI 会让它恒为 0，
        # 此时唯一的信息源是 Raw Input，清空等于把 Raw Input 的信号也抹掉。
        return bool(self.buttons) or (now - self.last_wheel) < self.WHEEL_HOLD

    def window_at_cursor(self):
        """光标下**根窗口**的 hwnd（物理像素）。失败返回 0。"""
        point = wintypes.POINT()
        if not user32.GetCursorPos(ctypes.byref(point)):
            return 0
        hwnd = user32.WindowFromPoint(point)
        if not hwnd:
            return 0
        root = user32.GetAncestor(hwnd, GA_ROOT)
        return int(root or hwnd)
