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
RIM_TYPEKEYBOARD = 1
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


# 鼠标包 48 字节、键盘包 40 字节（x64）；留余量。更大的只有 HID 报告，不是我们订阅的。
RAW_INPUT_BUFFER = 96


def read_raw_input(handle, buffer):
    """一次 GetRawInputData 读进预分配缓冲；返回拷贝的字节数，装不下或失败返回 None。

    原来每条消息先问长度、再 create_string_buffer、再读一次 —— 1000 Hz 鼠标下
    每秒几千次分配。缓冲装不下的只会是 HID 报告，直接忽略即可。
    """
    size = wintypes.UINT(len(buffer))
    copied = user32.GetRawInputData(wintypes.HANDLE(handle), RID_INPUT, buffer,
                                    ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
    if copied == 0xFFFFFFFF or copied < ctypes.sizeof(RAWINPUTHEADER):
        return None
    return copied


class RawInputFilter(C.QAbstractNativeEventFilter):
    """全进程唯一的 WM_INPUT 入口：读一次，按 dwType 分发给鼠标 / 键盘 watcher。

    以前鼠标、键盘各装一个 filter，每条 WM_INPUT 都被两个 filter 完整读取；
    而 Qt 又把同一条消息投递两次（先 windows_dispatcher_MSG，后窗口过程里的
    windows_generic_MSG），于是每次鼠标移动触发 4 次读取。

    这里**只在 generic 那一次读**：它来自窗口过程，在任何事件循环（包括原生
    模态循环）里都会到达；dispatcher 那一次只在 Qt 自己的循环里有，且随后
    必然还会以 generic 再来一次。watcher 的状态更新本就是幂等的，不依赖次数。
    """
    _instance = None

    @classmethod
    def shared(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self.mouse = None
        self.keyboard = None
        self._app = None
        self._buffer = ctypes.create_string_buffer(RAW_INPUT_BUFFER)
        self.last_error = None

    def attach(self, mouse=None, keyboard=None):
        if mouse is not None:
            self.mouse = mouse
        if keyboard is not None:
            self.keyboard = keyboard
        app = C.QCoreApplication.instance()
        if self._app is None and app is not None:
            app.installNativeEventFilter(self)
            self._app = app

    def detach(self, mouse=None, keyboard=None):
        if mouse is not None and self.mouse is mouse:
            self.mouse = None
        if keyboard is not None and self.keyboard is keyboard:
            self.keyboard = None
        if self.mouse is None and self.keyboard is None and self._app is not None:
            try:
                self._app.removeNativeEventFilter(self)
            except (RuntimeError, TypeError):
                pass
            self._app = None

    def nativeEventFilter(self, eventType, message):
        try:
            if eventType == b'windows_generic_MSG':
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_INPUT:
                    self._read(int(msg.lParam))
        except Exception as error:            # 绝不因为观察失败而打断 Qt 的事件派发
            self.last_error = str(error)
        return (False, 0)

    def _read(self, handle):
        copied = read_raw_input(handle, self._buffer)
        if copied is None:
            return
        kind = RAWINPUTHEADER.from_buffer(self._buffer).dwType
        if kind == RIM_TYPEMOUSE:
            if self.mouse is not None:
                self.mouse._mouse_packet(self._buffer, copied)
        elif kind == RIM_TYPEKEYBOARD:
            if self.keyboard is not None:
                self.keyboard._keyboard_packet(self._buffer, copied)


class MouseWatcher(C.QAbstractNativeEventFilter):
    """观察鼠标按键/滚轮；只用 `interacting()` 对外表态。

    注册失败时 `ok=False`，`interacting()` 恒为 False（fail open）——
    一个静默失效的监听，远好于一个永远不恢复的叠图。

    `keys` 是可选的：给了它，鼠标按键的按下/松开会一并转给 `Keys`，
    侧键/中键因此也能当「打开地图」的快捷键。键盘 watcher 是同一个类的子类，
    走的就是这条线。
    """

    WHEEL_HOLD = 0.120     # 滚轮停多久算「停稳」
    STUCK_TIMEOUT = 30.0   # 持有按键却这么久没有任何边沿 -> 判定为丢了 release

    def __init__(self, keys=None):
        super().__init__()
        self.ok = False
        self.keys = keys
        self.buttons = set()
        self.last_wheel = 0.0
        self.last_edge = 0.0
        self._app = None
        self._poll_works = False
        self.last_error = None
        self._buffer = ctypes.create_string_buffer(RAW_INPUT_BUFFER)

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
        RawInputFilter.shared().attach(mouse=self)
        self._app = app
        self.ok = True
        return True

    def release(self):
        if self._app is not None:
            RawInputFilter.shared().detach(mouse=self)
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
        # 兼容入口：正常运行时不再单独装这个 filter，而是由 RawInputFilter
        # 读一次再分发；直接调用时也只认 generic 那一次（见 RawInputFilter）。
        try:
            if eventType == b'windows_generic_MSG':
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_INPUT:
                    self._read(int(msg.lParam))
        except Exception as error:            # 绝不因为观察失败而打断 Qt 的事件派发
            self.last_error = str(error)
        return (False, 0)                     # PySide6 要求返回 (handled, result) 元组

    def _read(self, handle):
        """一次读取（不再先问长度再开缓冲），只处理鼠标包。"""
        copied = read_raw_input(handle, self._buffer)
        if copied is None:
            return
        self._mouse_packet(self._buffer, copied)

    def _mouse_packet(self, buffer, copied):
        header_size = ctypes.sizeof(RAWINPUTHEADER)
        if copied < header_size + ctypes.sizeof(RAWMOUSE):
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
                self._hotkey_edge(vk, False)
            elif flags & up_bit:
                self.buttons.discard(vk)
                self._hotkey_edge(vk, True)

    def _hotkey_edge(self, vk, released):
        """把鼠标按键的边沿转给快捷键状态机（`Keys` 自己会挑出它关心的那几个键）。"""
        if self.keys is not None:
            self.keys.raw_edge(vk, released)

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

    def map_interacting(self):
        # Keep existing polling/release recovery, but only map controls can
        # invalidate a pose. Right/middle/side buttons are unrelated actions.
        self.interacting()
        return 0x01 in self.buttons or (time.perf_counter()-self.last_wheel)<self.WHEEL_HOLD

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
