"""Small Windows companion UI; no injection, game hooks or network service."""
from __future__ import annotations
import argparse
import json
import multiprocessing as mp
from pathlib import Path
import sys
import time

from .paths import ROOT, DATA_ROOT
_venv_deps = ROOT/'.venv/Lib/site-packages'
_fallback_deps = ROOT/'.ui-deps'
# Prefer the real virtualenv even when an older bundled dependency directory
# is present beside the source tree.
if _venv_deps.exists():
    sys.path.insert(0, str(_venv_deps))
elif _fallback_deps.exists():
    sys.path.insert(0, str(_fallback_deps))

from PySide6 import QtCore as C, QtGui as G, QtWidgets as W
from .src.live import ToggleState, worker
from .src import windows as native
from .mouse_input import MouseWatcher
from .pet import PetAnimation, SpeechBubble, reaction
from .panel_dialogs import own_dialog_open
from .theme import MistPanel, GearButton, ChalkButton, ChalkChoice, DelaySlider, ChalkSlider, ChalkToggle, EditButton
import win32gui

BG = 'rgba(20,28,37,234)'
# Bundled faces, registered app-locally; nothing is installed system-wide.
# Order matters: Qt resolves glyph by glyph, so Latin stays with the italic face
# and CJK falls through to the Chinese one.
FONT_DIR = Path(__file__).resolve().parent/'assets/fonts'
FONT_FILES = ('EssayText-Italic.ttf','HYDiWRGJ.ttf')
FONT_FALLBACK = 'Microsoft YaHei UI'
FONT_CACHE = []
ARROW = (Path(__file__).resolve().parent/'assets/chevron.png').as_posix()


def font_stack():
    """Load the bundled fonts once and return the Qt/CSS family list."""
    if not FONT_CACHE:
        for name in FONT_FILES:
            path = FONT_DIR/name
            if path.exists():
                font_id = G.QFontDatabase.addApplicationFont(str(path))
                FONT_CACHE.extend(G.QFontDatabase.applicationFontFamilies(font_id))
        FONT_CACHE.append(FONT_FALLBACK)
        app = W.QApplication.instance()
        if app is not None:
            font = G.QFont()
            font.setFamilies(FONT_CACHE)
            font.setPixelSize(16)
            app.setFont(font)
    return FONT_CACHE


def css_font():
    return ', '.join(f'"{family}"' for family in font_stack())


# 冷调灰蓝雾面、浅色文字：按用户给的两张游戏内参考图定的方向。
# 面板半透明，让游戏画面透出来；控件是雾面浅色块配深色字。
STYLE = '''
QWidget { color: #dbe5ec; font-family: __FONT__; font-size: 16px; }
QFrame#panel { background: rgba(20,28,37,234); border: 1px solid rgba(154,180,200,60); border-radius: 10px; }
QLabel#title { color: #eef4f8; font-size: 24px; }
QLabel#muted { color: #acbdca; font-size: 14px; }
QPushButton, QComboBox { background: rgba(203,215,223,92); border: 1px solid rgba(219,230,237,110); border-radius: 6px; padding: 7px; color: #101b25; }
QPushButton:hover, QComboBox:hover { background: rgba(219,230,237,140); border-color: rgba(238,245,250,175); }
QPushButton:pressed { background: rgba(236,243,248,190); }
QComboBox::drop-down { border: none; width: 22px; }
/* Qt 不支持 CSS 画三角形的写法（会渲染成实心方块），必须用图片。 */
QComboBox::down-arrow { image: url(__ARROW__); width: 11px; height: 7px; }
QComboBox QAbstractItemView { background: #1b2530; color: #dbe5ec; border: 1px solid rgba(154,180,200,70);
    selection-background-color: #b9cbd7; selection-color: #101b25; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid rgba(170,194,212,110);
    background: rgba(190,203,212,45); border-radius: 3px; }
QCheckBox::indicator:checked { background: #b9cbd7; }
QSlider::groove:horizontal { height: 3px; background: rgba(140,166,186,60); border-radius: 2px; }
QSlider::sub-page:horizontal { background: #93aec0; border-radius: 2px; }
QSlider::handle:horizontal { background: #ccdae3; width: 12px; margin: -5px 0; border-radius: 6px; }
/* 分段开关：照参考图的「关 / 开」——选中亮、未选中暗。 */
QPushButton#seg { background: rgba(203,215,223,34); color: #a9b8c5; border: 1px solid rgba(219,230,237,54); border-radius: 6px; padding: 7px; }
QPushButton#seg:hover { background: rgba(219,230,237,78); color: #dbe5ec; }
QPushButton#seg:checked { background: rgba(228,238,245,232); color: #101b25; border-color: rgba(242,248,252,246); }
QPushButton#seg:checked:hover { background: rgba(241,248,253,250); }
QPushButton#gear { font-size: 25px; color: #dbe5ec; background: rgba(20,28,37,234);
    border-radius: 22px; border: 1px solid rgba(158,184,204,84); }
QPushButton#gear:hover { border-color: #b6cbd9; background: rgba(36,48,60,240); }
/* 地图管理列表。全项目第一个滚动区：不写这段，滚动条就是 Windows 原生灰条，
   和雾面面板完全打架。viewport 也要显式透明，否则它按调色板底色刷成一块白。 */
QScrollArea, QScrollArea > QWidget#qt_scrollarea_viewport, QWidget#mapbody { background: transparent; border: none; }
QWidget#maprow { background: rgba(203,215,223,20); border: 1px solid rgba(219,230,237,34); border-radius: 6px; }
QWidget#maprow:hover { background: rgba(219,230,237,48); border-color: rgba(238,245,250,80); }
/* 缩略图正开着的那一行。改 objectName 后必须 repolish，见 map_manage_ui.pick()。 */
QWidget#maprow-on { background: rgba(203,215,223,62); border: 1px solid rgba(238,245,250,150); border-radius: 6px; }
QLabel#section { color: #93a7b6; font-size: 13px; padding: 4px 2px 2px 2px; }
QLabel#mapname { color: #e3edf2; font-size: 15px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: rgba(178,199,214,110); border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: rgba(203,220,232,175); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
'''


HOTKEYS = {**{chr(k):k for k in range(65,91)},
           **{str(k):48+k for k in range(10)},
           **{f'F{k}':111+k for k in range(1,13)},
           # Common non-character keys (Windows virtual-key codes).
           # Escape remains reserved by the hotkey dialog for cancel.
           'TAB': 0x09, 'SPACE': 0x20, 'ENTER': 0x0D,
           'BACKSPACE': 0x08, 'INSERT': 0x2D, 'DELETE': 0x2E,
           'RETURN': 0x0D,
           'HOME': 0x24, 'END': 0x23, 'PAGEUP': 0x21, 'PAGEDOWN': 0x22}


def advise(details,message):
    """把引擎的中立 reason 翻译成这一刻真正可操作的提示。

    `matcher.py` 在可见角点不足 4 个时直接返回 insufficient_visible_structure，
    `presentation_candidate` 会把它说成「请打开游戏地图后重试」—— 可放大到看不清时
    地图明明是开着的，该做的是缩小。只改文案，不动任何阈值。
    """
    if details.get('reason') == 'insufficient_visible_structure':
        return '可见地图内容太少，请用滚轮缩小地图后重试'
    return message


def explain_failure(message):
    """`matcher.py:38` 在候选集为空时抛英文异常，一路原样冒到提示框里。

    这条现在真的可能发生了 —— 「管理地图」能把某个难度的地图删空。只换文案，
    不动那一行 raise，也不给它加兜底。
    """
    if 'No references satisfy the supplied hints' in message:
        return '这个难度下已经没有可用地图了，请在「管理地图」里恢复或新增'
    return message


# 连续两帧判定「屏幕上没有地图」才退出；第二帧自动获取，不需要再次操作。
# 刚进地图、还没探索、或者一次失手都可能只失败一次。
NO_MAP_STREAK = 2

# 「屏幕上没有地图」需要的角点数下限。实测（见 tests/test_no_map_signal.py）：
# 3D 游戏场景 320~372 个角点，而地图画面（无论探索多少）只有 32~60 个 —— 差 6 倍以上。
# 地图面板是平面的风格化线条，3D 场景则满是纹理，所以这个数在物理上说得通。
# 实测它对分辨率几乎不敏感（同一张图缩到 60%：372→320、60→54、54→56），
# 所以用绝对值而不是每像素密度。描述符上限 512，372 没有被截断。
NO_MAP_ANCHORS = 150


def no_map_evidence(details):
    """这一帧的结果是否说明「屏幕上根本没有地图」。

    **必须和「地图放得太大」分开**：放大到看不清时 `matcher.match` 直接返回
    insufficient_visible_structure（可见角点 < 4），可地图明明是开着的 —— 上一版
    把这类失败也当成会话结束，正是用户报的「调整之后就不认了」，绝不能重蹈。
    所以 insufficient_visible_structure 在这里**不算**「没有地图」，它继续走
    `advise()` 的「请缩小地图」。

    真正的「没有地图」是另一条路：证据提取找得到角点（实测桌面截图 anchors=68），
    但配出来的候选过不了 `live.py` 的可靠性门 —— 真地图 explained≈0.76 /
    contradiction≈0.20，非地图画面 explained≈0.29 / contradiction≈0.64。

    **先看纹理密度再看可靠性门**：光靠可靠性门分不开 —— 实测「地图开着但没探索」
    会给出 explained=0.226，比 3D 游戏画面的 0.387 还低，两者完全重叠。真正分开它们的是
    角点数（3D 场景 320~372，地图画面 32~60）。所以先要求画面足够「花」，再看引擎是否
    认不出它。少了角点这一关，刚进地图还没探索时就会被误判成「没有地图」并退出。

    下面逐条复刻 `live.py:34` 那道门（阈值一个字没改，只是把「不可靠」读成
    「这不是地图」）。门的后半段 —— 两张图过于相似、楼层未确认 —— **不在这里**：
    那两种情况说明地图明明在屏幕上，绝不能拿来当退出的理由。
    """
    if not details or details.get('reason') == 'insufficient_visible_structure':
        return False
    # 角点在 diagnostics 里，不在顶层 —— `to_dict()` 是 asdict(MatchResult)，
    # 顶层只有 reason/candidates/... 写成 details['anchors'] 会恒为 None，
    # 这一关就永远返回 False，功能等于没做（test_no_map_signal 抓的就是这个）。
    if ((details.get('diagnostics') or {}).get('anchors') or 0) < NO_MAP_ANCHORS:
        return False
    candidates = details.get('candidates') or []
    if not candidates:
        return True                      # 连候选都没有：屏幕上没有地图结构
    top = candidates[0]
    if top.get('pose') is None:
        return True
    if (top.get('explained') or 0) < .55:
        return True
    if top.get('contradiction') is None or top['contradiction'] > .40:
        return True
    return (top.get('retrieval_score') or 0) < 4


# 提示停留时长。够扫一眼就行 —— 再长就开始挡视野，而完整说法一直留在面板底部。
TOAST_MS = 1200

# 提示框最宽占可用屏宽的比例，超了才换行。短句因此永远是个短框。
TOAST_MAX_RATIO = .42

# 长句压成一眼扫完的短句。完整原文照样进面板底部的 status，这里只管齿轮旁边那一条。
TOAST_BRIEF = {
    '没有找到可靠匹配，请增加探索范围后重试':'未匹配，请多探索一些',
    '可见地图内容太少，请用滚轮缩小地图后重试':'内容太少，请缩小地图',
    '没有识别到地图结构，请打开游戏地图后重试':'未发现地图，请先打开地图',
    '正在确认地图已关闭…':'确认中…',
    '鼠标监听未启用，跟随缩放/移动已关闭':'鼠标监听未启用',
    '窗口位置或大小已变化，请重新匹配':'窗口已变化，请重新匹配',
    '匹配进程已退出，请重试':'匹配中断，请重试',
    '匹配进程中断，请重试':'匹配中断，请重试',
    '无法读取截图，请选择 PNG 或 JPG 图片':'请选择 PNG 或 JPG 图片',
    '点击截图窗口，按 G 开始匹配；Esc 隐藏':'按 G 开始匹配，Esc 隐藏',
    '请切到要识别的画面；1 秒后截屏':'1 秒后截屏',
    '请先切到截图或游戏画面':'请先切到画面',
}


def hotkey_text(name):
    return {'BACKSPACE':'退格键','TAB':'Tab','SPACE':'空格','ENTER':'回车','RETURN':'回车'}.get(name,name)


class HotkeyDialog(W.QDialog):
    def __init__(self,current,parent,default='G'):
        super().__init__(parent,C.Qt.Dialog | C.Qt.FramelessWindowHint)
        self.selected=current
        self.default=default
        self.setAttribute(C.Qt.WA_TranslucentBackground)
        self.setFixedWidth(320)
        outer=W.QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0)
        panel=MistPanel()
        outer.addWidget(panel)
        layout=W.QVBoxLayout(panel)
        layout.setContentsMargins(22,22,22,22)
        layout.setSpacing(14)
        title=W.QLabel('修改快捷键')
        title.setObjectName('title')
        layout.addWidget(title)
        self.readout=W.QLabel(hotkey_text(current))
        self.readout.setAlignment(C.Qt.AlignCenter)
        self.readout.setStyleSheet('font-size:28px;padding:12px;')
        layout.addWidget(self.readout)
        self.hint=W.QLabel('按下字母、数字或 F1–F12\nEsc 保留为隐藏 / 取消')
        self.hint.setObjectName('muted')
        layout.addWidget(self.hint)
        row=W.QHBoxLayout()
        for label,action in [('恢复默认',self.reset),('取消',self.reject),('保存',self.accept)]:
            button=ChalkButton(label)
            button.setFocusPolicy(C.Qt.NoFocus)
            button.clicked.connect(action)
            row.addWidget(button)
        layout.addLayout(row)

    def reset(self):
            self.selected=self.default
            self.readout.setText(hotkey_text(self.default))

    def keyPressEvent(self,event):
        if event.key()==C.Qt.Key_Escape:
            self.reject()
            return
        name=G.QKeySequence(event.key()).toString().upper()
        if name in HOTKEYS and not (event.modifiers() & (C.Qt.ControlModifier | C.Qt.AltModifier | C.Qt.ShiftModifier | C.Qt.MetaModifier)):
            self.selected=name
            self.readout.setText(hotkey_text(name))
        else:
            self.hint.setText('请选择单个字母、数字或 F1–F12\nEsc 保留为隐藏 / 取消')


class Overlay(W.QWidget):
    def __init__(self):
        super().__init__(None,C.Qt.Tool | C.Qt.FramelessWindowHint | C.Qt.WindowStaysOnTopHint | C.Qt.WindowTransparentForInput | C.Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(C.Qt.WA_TranslucentBackground)
        self.setAttribute(C.Qt.WA_ShowWithoutActivating)
        self.picture = None
        self.opacity = .30

    def display(self, layer, rect, opacity):
        h,w = layer.shape[:2]
        self.picture = G.QImage(layer.data,w,h,layer.strides[0],G.QImage.Format_ARGB32).copy()
        self.opacity = opacity
        self.show()
        native.place_overlay(int(self.winId()),rect)
        self.update()

    def paintEvent(self,event):
        if self.picture is not None:
            p = G.QPainter(self)
            p.setOpacity(self.opacity)
            p.drawImage(self.rect(),self.picture)


class ScreenshotWindow(W.QLabel):
    closed = C.Signal()

    def closeEvent(self,event):
        self.closed.emit()
        super().closeEvent(event)


class Segmented(W.QWidget):
    """点击即选的分段开关，按下拉框那套接口实现，便于直接替换。

    参考游戏内「关 / 开」：选中项亮、未选中项暗，不用展开弹层。
    """
    currentIndexChanged = C.Signal(int)

    def __init__(self, items):
        super().__init__()
        self.items = list(items)
        self.index = 0
        row = W.QHBoxLayout(self)
        row.setContentsMargins(0,0,0,0)
        row.setSpacing(6)
        self.group = W.QButtonGroup(self)
        self.group.setExclusive(True)
        for i,(label,_data) in enumerate(self.items):
            button = W.QPushButton(label)
            button.setObjectName('seg')
            button.setCheckable(True)
            button.setCursor(C.Qt.PointingHandCursor)
            self.group.addButton(button,i)
            row.addWidget(button)
        self.group.button(0).setChecked(True)
        # idClicked only fires for real clicks, so a click on the already
        # selected segment stays silent, matching the old combo behaviour.
        self.group.idClicked.connect(self.setCurrentIndex)

    def currentIndex(self):
        return self.index

    def currentData(self):
        return self.items[self.index][1]

    def setCurrentIndex(self,index):
        if index == self.index:
            return
        self.index = index
        self.group.button(index).setChecked(True)
        self.currentIndexChanged.emit(index)


class DraggableGear(GearButton):
    """可拖拽的齿轮：按住拖动就搬动整个助手窗口，没拖动则照常弹出面板。

    clicked 不是 GearButton 发的，是 QAbstractButton.mouseReleaseEvent 发的，
    所以拖过之后直接 return 不调 super()，clicked 就不会发，面板不会误弹出。
    用子类重写事件而不是 eventFilter：在 press 上拦截会让按钮看起来是死的。
    Qt 在 press 时会隐式 grab 鼠标，窗口滑出光标下方后仍收得到 move/release。
    """

    def __init__(self,window):
        super().__init__()
        self.window=window
        self.pet=PetAnimation(self, ROOT/"docs/images/logo.png")
        self.origin=None
        self.press_global=None
        self.moved=False

    def paintEvent(self,event):
        if self.pet.enabled:
            self.pet.paint()
        else:
            super().paintEvent(event)

    def enterEvent(self,event):
        self.pet.play('curious')
        super().enterEvent(event)

    def mousePressEvent(self,event):
        if event.button()==C.Qt.LeftButton:
            self.pet.play('heart')
            # 全程 Qt 逻辑坐标：globalPosition/frameGeometry/move 三者同一套。
            self.press_global=event.globalPosition().toPoint()
            self.origin=self.press_global-self.window.frameGeometry().topLeft()
            self.moved=False
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.origin is None or not (event.buttons() & C.Qt.LeftButton):
            super().mouseMoveEvent(event)
            return
        point=event.globalPosition().toPoint()
        if not self.moved:
            if (point-self.press_global).manhattanLength() < W.QApplication.startDragDistance():
                return
            self.moved=True
            self.setDown(False)     # 拖拽中不再显示按下态
        self.window.move(point-self.origin)

    def mouseReleaseEvent(self,event):
        dragging=self.moved
        self.origin=self.press_global=None
        self.moved=False
        if dragging:
            self.setDown(False)     # 不自己清的话按钮会永远停在按下态
            self.window.clamp_to_screen()
            self.window.save()
            return                  # 不调 super() => 不发 clicked
        super().mouseReleaseEvent(event)


class Companion(W.QWidget):
    def __init__(self, demo=None):
        super().__init__(None,C.Qt.Tool | C.Qt.FramelessWindowHint | C.Qt.WindowStaysOnTopHint)
        self.setAttribute(C.Qt.WA_TranslucentBackground)
        self.setAttribute(C.Qt.WA_ShowWithoutActivating)
        self.setWindowTitle('加页手记 · 地图助手')
        self.setStyleSheet(STYLE.replace('__FONT__',css_font()).replace('__ARROW__',ARROW))
        self.overlay = Overlay()
        self.state = ToggleState()
        self.keys = native.Keys()
        self.process = self.connection = None
        self.busy = False
        self.target = None
        self.rect_at_capture = None
        self.pending = None
        self.cached_candidate = None
        self.demo = demo
        self.demo_window = None
        self.started = 0
        # 跟随地图的缩放/移动：交互期间隐藏叠图，停手后重新对齐一次。
        self.mouse = MouseWatcher()
        self.mouse_follow = True
        self.follow_active = False
        self.follow_dirty = False
        # 连续几次手势判定「屏幕上没有地图」。用户单击关掉游戏小地图时，那次松开
        # 照样会触发一次重新匹配，识别到的就只有游戏画面 —— 靠这个计数退出状态。
        self.no_map_streak = 0
        # take_capture 到 capture_after_hide 之间那 60 ms 里 busy 还是 False、
        # pending 还是 None，现有标志盖不住这段窗口。
        self._capturing = False
        self.settings_path = DATA_ROOT/'out/mapmatching/ui_settings.json'
        self.settings = {}
        try:
            self.settings = json.loads(self.settings_path.read_text(encoding='utf-8'))
        except (OSError,ValueError):
            pass
        self.hotkey = self.settings.get('hotkey','G')
        if self.hotkey not in HOTKEYS:
            self.hotkey = 'G'
        self.keys.toggle_key = HOTKEYS[self.hotkey]
        self.hide_hotkey = self.settings.get('hide_hotkey','BACKSPACE')
        if self.hide_hotkey not in HOTKEYS or self.hide_hotkey == self.hotkey:
            self.hide_hotkey = 'BACKSPACE'
        self.keys.hide_key = HOTKEYS[self.hide_hotkey]
        layout = W.QVBoxLayout(self)
        layout.setContentsMargins(3,3,3,3)
        layout.setSpacing(8)
        self.gear = DraggableGear(self)
        self.gear.setObjectName('gear')
        self.gear.pet.enable(self.settings.get("pet_enabled",True))
        self.gear.setToolTip('加页手记 · 设置')
        self.gear.clicked.connect(self.toggle_panel)
        layout.addWidget(self.gear,0,C.Qt.AlignRight)
        self.panel = MistPanel()
        self.panel.setObjectName('panel')
        self.panel.setFixedWidth(360)
        box = W.QVBoxLayout(self.panel)
        box.setContentsMargins(20,18,20,18)
        box.setSpacing(10)
        title = W.QLabel('加页手记')
        title.setObjectName('title')
        box.addWidget(title)
        self.difficulty = ChalkChoice([('困难','hard'),('噩梦','nightmare')])
        self.difficulty.setCurrentIndex(1 if self.settings.get('difficulty') == 'nightmare' else 0)
        difficulty_row=W.QHBoxLayout()
        label=W.QLabel('难度')
        label.setFixedWidth(62)
        difficulty_row.addWidget(label)
        difficulty_row.addWidget(self.difficulty,1)
        box.addLayout(difficulty_row)
        self.party_row = W.QWidget()
        party_layout = W.QHBoxLayout(self.party_row)
        party_layout.setContentsMargins(0,0,0,0)
        party_label=W.QLabel('人数')
        party_label.setFixedWidth(62)
        party_layout.addWidget(party_label)
        self.party = ChalkChoice([('单人','solo'),('多人','duo')])
        self.party.setCurrentIndex(1 if self.settings.get('mode') == 'duo' else 0)
        party_layout.addWidget(self.party,1)
        box.addWidget(self.party_row)
        self.opacity_label = W.QLabel()
        box.addWidget(self.opacity_label)
        self.opacity = ChalkSlider()
        self.opacity.setRange(5,80)
        self.opacity.setValue(max(5,min(80,int(self.settings.get('opacity',30)))))
        box.addWidget(self.opacity)
        self.delay = DelaySlider()
        self.delay.setValue(max(100,min(1000,int(self.settings.get('delay',350)))))
        self.delay_label=W.QLabel()
        self.delay.valueChanged.connect(lambda value: self.delay_label.setText(f'展开等待    {value} ms'))
        self.delay_label.setText(f'展开等待    {self.delay.value()} ms')
        self.enabled = ChalkToggle()
        self.enabled.setChecked(True)
        self.status = W.QLabel('待机')
        self.status.setWordWrap(True)
        self.status.setObjectName('muted')
        self.bound_label = W.QLabel('直接截取当前屏幕 · 无需绑定')
        self.bound_label.setWordWrap(True)
        self.bound_label.setObjectName('muted')
        self.bound_label.hide()
        local = ChalkButton('本地截图')
        local.clicked.connect(self.choose_screenshot)
        enroll = ChalkButton('管理地图')
        enroll.clicked.connect(self.manage_maps)
        self.return_game = ChalkButton('返回屏幕')
        self.return_game.clicked.connect(self.leave_demo)
        self.return_game.hide()
        box.addWidget(self.return_game)
        buttons = W.QHBoxLayout()
        retry = ChalkButton('重新识别')
        retry.clicked.connect(self.retry)
        hide = ChalkButton('隐藏叠图')
        hide.clicked.connect(self.close_map)
        buttons.addWidget(retry)
        buttons.addWidget(hide)
        hide_button_pencil=EditButton()
        hide_button_pencil.clicked.connect(self.edit_hide_hotkey)
        hide_button_pencil.setToolTip('修改隐藏叠图快捷键')
        buttons.addWidget(hide_button_pencil)
        box.addLayout(buttons)
        box.addSpacing(6)
        box.addWidget(self.delay_label)
        box.addWidget(self.delay)
        hotkeys=W.QHBoxLayout()
        self.hotkey_label=W.QLabel(f'启用快捷键({self.hotkey}/esc)')
        hotkeys.addWidget(self.hotkey_label)
        pencil=EditButton()
        pencil.clicked.connect(self.edit_hotkey)
        hotkeys.addWidget(pencil)
        hotkeys.addWidget(self.enabled,1)
        box.addLayout(hotkeys)
        hidekeys=W.QHBoxLayout()
        self.hide_hotkey_label=W.QLabel(f'隐藏叠图({self.hide_hotkey})')
        hidekeys.addWidget(self.hide_hotkey_label)
        hide_pencil=EditButton()
        hide_pencil.clicked.connect(self.edit_hide_hotkey)
        hidekeys.addWidget(hide_pencil)
        box.addLayout(hidekeys)
        # The shortcut editor lives beside the hide button; keep the legacy
        # row out of the panel while retaining its label for compatibility.
        for _widget in (self.hide_hotkey_label, hide_pencil):
            _widget.hide()
        hidekeys.setContentsMargins(0, 0, 0, 0)
        hidekeys.setSpacing(0)
        box.setStretch(box.indexOf(self.status), 1)
        pet_row = W.QHBoxLayout()
        pet_row.addStretch()
        pet_label = W.QLabel("个性外观：")
        pet_label.setStyleSheet('font-size:14px;')
        pet_row.addWidget(pet_label)
        self.pet_enabled = ChalkToggle()
        self.pet_enabled.setFixedSize(88,28)
        pet_font = self.pet_enabled.font()
        pet_font.setPixelSize(14)
        self.pet_enabled.setFont(pet_font)
        self.pet_enabled.setChecked(self.gear.pet.enabled)
        self.pet_enabled.setToolTip("关闭后恢复齿轮；不影响识图和提示")
        self.pet_enabled.toggled.connect(self.set_pet_enabled)
        pet_row.addWidget(self.pet_enabled)
        pet_row.addStretch()
        utilities = W.QHBoxLayout()
        utilities.addWidget(enroll,1)
        utilities.addWidget(local,1)
        box.addLayout(utilities)
        records_row = W.QHBoxLayout()
        self.record_failures = W.QCheckBox('记录识别失败')
        self.record_failures.setChecked(self.settings.get('record_failures', True))
        self.record_failures.setToolTip('保存识别时的完整截图及诊断数据，仅保存在本机；分享前请检查截图中的私人信息')
        self.record_failures.toggled.connect(lambda _: self.save())
        records_row.addWidget(self.record_failures)
        records_button = ChalkButton('打开记录')
        records_button.clicked.connect(self.open_failure_records)
        records_row.addWidget(records_button)
        box.addLayout(records_row)
        box.addWidget(self.status)
        quit_button = W.QPushButton('退出')
        quit_button.setStyleSheet('background:transparent;color:#9fb3c2;border:none;padding:2px;')
        quit_button.clicked.connect(W.QApplication.instance().quit)
        box.addWidget(quit_button)
        box.addLayout(pet_row)
        layout.addWidget(self.panel)
        self.panel.hide()
        self.toast = SpeechBubble()
        self.toast.setStyleSheet('QLabel {color:#dbe5ec;background:transparent;border:0;'
                                'font-size:13px;font-family:'+css_font()+';}')
        self.toast_timer = C.QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self.toast.hide)
        self.timer = C.QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(20)
        self.difficulty.currentIndexChanged.connect(self.context_changed)
        self.party.currentIndexChanged.connect(self.context_changed)
        self.opacity.valueChanged.connect(self.opacity_changed)
        self.enabled.toggled.connect(lambda enabled: self.close_map() if not enabled else None)
        self.opacity_changed()
        self.party_row.setVisible(self.difficulty.currentIndex() == 1)
        self.adjustSize()
        if not self.restore_position():
            # 默认位置也按齿轮而不是窗口来定：窗口宽度随面板开关变化，
            # 只有齿轮的位置才是用户真正看到的那个「右上角」。
            screen = W.QApplication.primaryScreen().availableGeometry()
            self.place_gear(C.QPoint(screen.right()-20-self.gear.width(),screen.top()+30))
        if not self.mouse.register(int(self.winId())):
            # fail open：一个静默失效的监听，远好于一个永远不恢复的叠图。
            self.mouse_follow = False
            C.QTimer.singleShot(0,lambda: self.notify('鼠标监听未启用，跟随缩放/移动已关闭'))
        W.QApplication.instance().aboutToQuit.connect(self.shutdown)
        # Prepare the filtered index while the gear is idle, before the first G.
        C.QTimer.singleShot(0,self.start_worker)

    def event(self,event):
        """点到游戏/桌面时把展开的设置面板收回成齿轮。

        这一类点击我们**收不到鼠标事件** —— 它进了别的进程的消息队列 —— 所以只能靠
        失活来判断。但打开助手自己的对话框同样会让主窗口失活，那不是「回到游戏」，
        收掉面板会让用户关掉对话框后一脸茫然，所以用 own_dialog_open() 排掉。
        toast 和叠图都带 WA_ShowWithoutActivating / WindowDoesNotAcceptFocus，
        弹出它们不会误触发这里。
        """
        if (event.type()==C.QEvent.WindowDeactivate and self.panel.isVisible()
                and not own_dialog_open()):
            self.toggle_panel()
        return super().event(event)

    def toggle_panel(self):
        self.toast.hide()
        right = self.geometry().right()
        self.panel.setVisible(not self.panel.isVisible())
        self.adjustSize()
        self.move(right-self.width()+1,self.y())
        self.clamp_to_screen()

    def gear_pos(self):
        """齿轮的全局左上角（Qt 逻辑坐标）。

        存齿轮而不是窗口左上角：窗口宽度随面板开关变化，齿轮位置不变
        （toggle_panel 始终保住右边缘，齿轮又是右对齐的）。
        """
        return self.gear.mapToGlobal(C.QPoint(0,0))

    def gear_offset(self):
        """齿轮在窗口内的偏移（Qt 逻辑坐标）。

        **必须先让布局跑一遍**：窗口 show() 之前布局从未执行，`gear.pos()` 拿到的是
        控件尚未排版的陈旧几何（实测 (591,217)，而正确值是 (3,3)）。拿它去算窗口位置，
        算出来的窗口就是错的：保存 (1612,36) 会被还原成 (1024,3)，退出时 save() 又把
        这个错值写回去 —— 于是每次启动都错，而且每次错得还不一样。
        `invalidate()` 不能省：尺寸没变时 `activate()` 自己不会重排。
        """
        self.layout().invalidate()
        self.layout().activate()
        return self.gear.pos()

    def place_gear(self,point):
        """把齿轮左上角摆到屏幕逻辑坐标 point 上。"""
        self.move(point-self.gear_offset())
        self.clamp_to_screen()

    def clamp_to_screen(self):
        """把窗口夹进所在屏的可用区域内，免得拔显示器/改分辨率后跑到屏幕外。"""
        frame = self.frameGeometry()
        screen = W.QApplication.screenAt(frame.center()) or W.QApplication.screenAt(self.gear_pos())
        if screen is None:
            screen = W.QApplication.primaryScreen()
        area = screen.availableGeometry()
        x = min(max(frame.left(),area.left()),max(area.left(),area.right()-frame.width()))
        y = min(max(frame.top(),area.top()),max(area.top(),area.bottom()-frame.height()))
        if (x,y) != (frame.left(),frame.top()):
            self.move(x,y)

    def restore_position(self):
        """按上次保存的齿轮位置还原。位置不合法就返回 False，让调用方用默认位置。"""
        point = self.settings.get('pos')
        if not (isinstance(point,list) and len(point) == 2
                and all(isinstance(v,(int,float)) and not isinstance(v,bool) for v in point)):
            return False
        target = C.QPoint(int(point[0]),int(point[1]))
        if W.QApplication.screenAt(target) is None:
            return False            # 那块屏已经不在了，退回默认位置
        # offset 现场算而不是存下来：以后改布局边距也不会错。
        self.place_gear(target)
        return True

    def context(self):
        return ('hard',None) if self.difficulty.currentIndex() == 0 else ('nightmare','solo' if self.party.currentIndex() == 0 else 'duo')

    def save(self):
        difficulty,mode = self.context()
        point = self.gear_pos()
        self.settings_path.parent.mkdir(parents=True,exist_ok=True)
        self.settings_path.write_text(json.dumps(dict(difficulty=difficulty,mode=mode,opacity=self.opacity.value(),delay=self.delay.value(),hotkey=self.hotkey,hide_hotkey=self.hide_hotkey,pet_enabled=self.gear.pet.enabled,record_failures=self.record_failures.isChecked(),pos=[point.x(),point.y()])),encoding='utf-8')

    def set_pet_enabled(self, enabled):
        # Preserve the settings panel under the pointer, rather than the differently
        # sized mascot. Otherwise the very switch being clicked jumps by 86 px.
        expanded = self.panel.isVisible()
        anchor_widget = self.panel if expanded else self.gear
        anchor = anchor_widget.mapToGlobal(C.QPoint(0,0))
        self.gear.pet.enable(enabled)
        self.adjustSize()
        self.layout().invalidate()
        self.layout().activate()
        if expanded:
            self.move(self.pos()+anchor-self.panel.mapToGlobal(C.QPoint(0,0)))
        else:
            self.place_gear(anchor)
        self.clamp_to_screen()
        self.toast.hide()
        self.save()

    def open_failure_records(self):
        directory = DATA_ROOT/'failure-records'
        directory.mkdir(parents=True, exist_ok=True)
        G.QDesktopServices.openUrl(C.QUrl.fromLocalFile(str(directory)))

    def edit_hotkey(self):
        self.close_map()
        dialog=HotkeyDialog(self.hotkey,self)
        if dialog.exec()==W.QDialog.Accepted:
            if dialog.selected == self.hide_hotkey:
                self.notify('快捷键冲突：不能与隐藏叠图快捷键相同')
                return
            self.hotkey=dialog.selected
            self.keys.toggle_key=HOTKEYS[self.hotkey]
            self.hotkey_label.setText(f'启用快捷键({self.hotkey}/esc)')
            self.save()
            self.notify(f'快捷键已改为 {self.hotkey}')

    def edit_hide_hotkey(self):
        dialog=HotkeyDialog(self.hide_hotkey,self,default='BACKSPACE')
        if dialog.exec():
            if dialog.selected == self.hotkey:
                self.notify('快捷键冲突：不能与地图开关快捷键相同')
                return
            self.hide_hotkey=dialog.selected
            self.keys.hide_key=HOTKEYS[self.hide_hotkey]
            self.hide_hotkey_label.setText(f'隐藏叠图({self.hide_hotkey})')
            self.save()
            self.notify(f'隐藏键已改为 {self.hide_hotkey}')

    def opacity_changed(self):
        self.opacity_label.setText(f'不透明度    {self.opacity.value()}%')
        self.overlay.opacity = self.opacity.value()/100
        self.overlay.update()

    def context_changed(self):
        self.cached_candidate = None
        self.close_map()
        self.stop_worker()
        self.party_row.setVisible(self.difficulty.currentIndex() == 1)
        self.adjustSize()
        self.save()
        C.QTimer.singleShot(0,self.start_worker)

    def notify(self,message):
        self.status.setText(message)
        if self.panel.isVisible():
            self.adjustSize()
        brief=message.split('\n')[0]
        for long,short in TOAST_BRIEF.items():
            brief=brief.replace(long,short)
        anchor=self.gear.mapToGlobal(C.QPoint(0,0))
        screen=W.QApplication.screenAt(anchor) or W.QApplication.primaryScreen()
        area=screen.availableGeometry()
        # 框随文字走：先按不换行量一次自然宽度，短句就得到短框。之前写死 320 上限 +
        # 常开 wordWrap，adjustSize() 会按 heightForWidth 挑一个方框，几个字的提示
        # 也撑成一块，白占视野。
        self.toast.setMinimumWidth(0)
        self.toast.setMaximumWidth(16777215)
        self.toast.setWordWrap(False)
        if self.gear.pet.enabled:
            self.gear.pet.play(reaction(message))
        self.toast.setText(brief)
        self.toast.adjustSize()
        natural=self.toast.width()
        # 只有真的超宽才换行，并且把宽度钉死在限额上 —— 否则 adjustSize() 又会
        # 按 heightForWidth 重新挑宽度，绕回上面那个方框。
        limit=max(160,int(area.width()*TOAST_MAX_RATIO))
        self.toast.setWordWrap(natural>limit)
        self.toast.setFixedWidth(min(natural,limit))
        self.toast.adjustSize()
        # Beside the whole expanded panel, or beside the gear when collapsed.
        x=self.geometry().right()+12
        if x+self.toast.width()>area.right()+1:
            x=self.geometry().left()-self.toast.width()-12
        x=max(area.left(),min(x,area.right()+1-self.toast.width()))
        y=max(area.top(),min(anchor.y(),area.bottom()+1-self.toast.height()))
        self.toast.move(x,y)
        self.toast.point_at(anchor+C.QPoint(self.gear.width()//2,24), self.gear.pet.enabled)
        self.toast.show()
        self.toast_timer.start(TOAST_MS)

    def choose_screenshot(self):
        self.close_map()
        path,_ = W.QFileDialog.getOpenFileName(self,'选择游戏截图',str(ROOT/'examples'),
                                             '游戏截图 (*.png *.jpg *.jpeg *.bmp)')
        if path:
            self.open_screenshot(Path(path))

    def import_map(self):
        from .map_import_ui import MapImportDialog
        self.close_map()
        # 传 ROOT 而不是 DATA_ROOT：`maps/` 是**唯一**一个地图库，原图、特征、
        # 登记表都在里面（见 mapstore）。旧版把自建图写进 LocalAppData 是因为
        # 内置图只读、两者本来就是两棵树；现在没有内置/自建之分，只留一棵，
        # 免得「管理界面改的那份」和「匹配实际读的那份」不是同一份。
        dialog=MapImportDialog(ROOT,*self.context(),self)
        if dialog.exec()==W.QDialog.Accepted:
            self.cached_candidate=None
            self.stop_worker()
            self.start_worker()
            record=dialog.result_record
            self.notify(f'已录入：{record["name"]}\n在对应难度 / 人数下自动参与匹配')

    def manage_maps(self):
        from .map_manage_ui import MapManageDialog
        self.close_map()
        # 停 worker 是**必需的**，不是保险：它只在启动时 load() 一次，把 references
        # 攥在进程生命周期里。不重启的话，已删除的地图照样能赢下匹配，然后走到
        # live.py:133 读源图那步抛 FileNotFoundError 并连带杀掉 worker。
        # 放在开框之前而不是每次删除之前，是为了让「打开→改→关」全程没有任何子进程
        # 可能持有句柄 —— Windows 上 os.replace / rmtree 撞上未关闭的句柄会 WinError 32。
        # 代价是关框后重建一次 worker（约 1 秒），和切难度同量级。
        self.stop_worker()
        dialog=MapManageDialog(ROOT,*self.context(),self)
        dialog.exec()
        # 看 changed 而不是 exec() 的返回值：用户完全可能改完再点「关闭」，
        # 那时 exec() 返回 Rejected，但库确实变了。
        if dialog.changed:
            self.cached_candidate=None
            self.notify(f'地图库已更新，可匹配 {dialog.active} 张\n下次匹配生效')
        C.QTimer.singleShot(0,self.start_worker)

    def open_screenshot(self,path):
        pixmap = G.QPixmap(str(path.resolve()))
        if pixmap.isNull():
            self.notify('无法读取截图，请选择 PNG 或 JPG 图片')
            return False
        self.leave_demo()
        window = ScreenshotWindow()
        window.setWindowTitle('加页手记 · 本地截图测试 · G 叠图 / Esc 隐藏')
        window.setPixmap(pixmap)
        window.setScaledContents(True)
        area = W.QApplication.primaryScreen().availableGeometry()
        scale = min(area.width()*.80/pixmap.width(),area.height()*.80/pixmap.height())
        # Keep the original aspect ratio, with no letterbox in captured pixels.
        window.setFixedSize(round(pixmap.width()*scale),round(pixmap.height()*scale))
        window.move(area.x()+10,area.y()+40)
        self.demo = path
        self.demo_window = window
        self.target = int(window.winId())
        window.closed.connect(self.leave_demo)
        window.show()
        window.raise_()
        window.activateWindow()
        self.return_game.show()
        self.bound_label.setText('本地截图：'+path.name)
        self.notify('点击截图窗口，按 G 开始匹配；Esc 隐藏')
        if self.panel.isVisible():
            self.adjustSize()
        return True

    def leave_demo(self):
        self.cached_candidate = None
        self.close_map()
        window = self.demo_window
        self.demo_window = None
        self.demo = None
        self.target = None
        self.rect_at_capture = None
        if window is not None:
            window.closed.disconnect(self.leave_demo)
            window.close()
            window.deleteLater()
        self.return_game.hide()
        self.bound_label.setText('直接截取当前屏幕 · 无需绑定')
        self.adjustSize()

    def is_game(self,hwnd):
        if not hwnd or not win32gui.IsWindow(hwnd) or win32gui.IsIconic(hwnd):
            return False
        if self.demo_window is not None:
            return hwnd == int(self.demo_window.winId())
        # No game title filter or manual binding. G observes the current screen.
        return hwnd not in (int(self.winId()),int(self.overlay.winId()),int(self.toast.winId()))

    def foreground_lost(self):
        """前台既不是游戏、也不是我们自己 —— 只有真的切走了才算丢。

        面板刚被点过（改不透明度/难度）时前台是我们的窗口，但那不代表用户离开了地图；
        take_capture 本来就会 self.hide() 把自己的窗口收掉再截屏。少了这条例外，
        一次跟随重算就会误判「切走了」并 close_map，症状正是「调整之后就不认了」。
        """
        foreground = win32gui.GetForegroundWindow()
        return foreground != int(self.winId()) and not self.is_game(foreground)

    def retry(self):
        self.cached_candidate = None
        if self.demo:
            self.demo_window.raise_()
            self.demo_window.activateWindow()
            self.open_map()
        else:
            self.notify('请切到要识别的画面；1 秒后截屏')
            C.QTimer.singleShot(1000,lambda: self.open_map() if self.is_game(win32gui.GetForegroundWindow()) else self.notify('请先切到截图或游戏画面'))

    def open_map(self):
        self.close_map(silent=True)
        token = self.state.open()
        self.started = time.perf_counter()
        self.target = int(self.demo_window.winId()) if self.demo_window is not None else win32gui.GetForegroundWindow()
        self.status.setText('等待地图展开…')
        C.QTimer.singleShot(self.delay.currentData(),lambda: self.take_capture(token))

    def take_capture(self,token):
        self._capturing = True
        if not self.state.accepts(token):
            self._capturing = False
            return
        if self.foreground_lost():
            self._capturing = False
            self.close_map()
            return
        self.overlay.hide()
        self.toast.hide()
        self.hide()
        # Let DWM remove our own UI before reading desktop pixels.
        C.QTimer.singleShot(60,lambda: self.capture_after_hide(token))

    def capture_after_hide(self,token):
        if not self.state.accepts(token):
            self._capturing = False
            self.show()
            return
        try:
            if self.foreground_lost():
                self.close_map()
                return
            self.rect_at_capture = self.capture_rect()
            pixels = native.capture(self.rect_at_capture)
            self.pending = (token,pixels,self.cached_candidate, dict(
                record_failures=self.record_failures.isChecked(),
                source='local_screenshot' if self.demo_window is not None else 'screen',
                capture_rect=self.rect_at_capture))
            self.status.setText('正在对齐上次地图…' if self.cached_candidate else '正在识别地图并配准…')
            self.start_worker()
        except Exception as error:
            self.close_map(silent=True)
            self.notify('截屏失败：'+str(error))
        finally:
            self._capturing = False
            self.show()

    def capture_rect(self):
        if self.demo_window is not None:
            return native.client_rect(int(self.demo_window.winId()))
        return native.monitor_rect(self.target)

    def start_worker(self):
        if self.process is None:
            parent,child = mp.Pipe()
            self.connection = parent
            self.process = mp.Process(target=worker,args=(child,str(ROOT),*self.context()),daemon=True)
            self.process.start()
            child.close()
            self.ready = False
        # not busy：一次只有一个请求在途。并发发两条会让先回的那条被后回的顶掉，
        # 状态就没法一一对应了。
        if self.ready and self.pending is not None and not self.busy:
            self.connection.send(self.pending)
            self.pending = None
            self.busy = True

    def stop_worker(self):
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=1)
            self.process.close()
            self.connection.close()
        self.process = self.connection = None
        self.busy = False
        self.pending = None
        # 进程没了，就绪状态当然也归零；留着 True 会让下一条请求发给还不存在的 worker。
        self.ready = False

    def close_map(self,silent=False):
        self.state.close()
        self.overlay.hide()
        self.toast.hide()
        self.pending = None
        # close_map 是所有拆卸路径的唯一收口（切难度/离开截图/重新识别/Esc/前台变化/
        # 窗口漂移），跟随状态在这里清就自动覆盖了「交互中途切上下文」等情况。
        self.follow_active = False
        self.follow_dirty = False
        self._capturing = False
        # 状态结束 = 计数归零。下次按 G 是新会话，不该背着上一次的失败次数。
        self.no_map_streak = 0
        if self.busy or (self.process is not None and not getattr(self,'ready',False)):
            self.stop_worker()
        if not silent:
            self.notify('已隐藏')

    def own_window_at_cursor(self):
        """光标是否压在自己的界面上（用来自：拖齿轮/调面板时不该暂停叠图）。

        不能用 QApplication.widgetAt()：叠图铺满整个显示器，它会返回叠图，门控就反了。
        用 Win32 的 WindowFromPoint —— 叠图带 WS_EX_TRANSPARENT，命中测试会被正确跳过。
        GetCursorPos/WindowFromPoint 都是物理像素，150% 缩放下不会和 Qt 的逻辑坐标错位。
        """
        hwnd = self.mouse.window_at_cursor()
        if not hwnd:
            return False
        return hwnd in (int(self.winId()),int(self.overlay.winId()),int(self.toast.winId()))

    def mouse_busy(self):
        """鼠标正在操作中，且跟随功能开着。

        收口成一个判据，好处是关掉 mouse_follow 就整体失效 —— 包括下面结果分支里
        「丢弃交互期间旧帧」那一条，否则基准测试里一次误触仍会让叠图不显示。
        """
        return bool(self.mouse_follow and self.mouse.interacting())

    def follow(self):
        """叠图期间跟随地图的缩放/移动：交互时隐藏，停手后重新对齐一次。

        一次「手势」= 松开左键，或滚轮停稳 WHEEL_HOLD。失败不会结束会话，
        所以用户调整完再松一次手就会自动重试 —— 这是这个功能存在的理由。
        """
        # 本地截图是静态的，没有地图可跟随；关掉快捷键开关就整体停用，语义一致。
        if not (self.mouse_follow and self.enabled.isChecked() and self.demo_window is None):
            return
        if self.mouse_busy():
            if self.own_window_at_cursor():
                # 在自己的齿轮/面板上操作，跟游戏里的地图无关：叠图照常显示，
                # 更不能在按键还按着的时候去 realign（那会中途截屏并隐藏窗口）。
                return
            self.follow_active = True
            self.follow_dirty = True
            self.overlay.hide()
            return
        # 只有鼠标完全空闲才可能走到这里，所以 realign 绝不会在拖动中途发生。
        self.follow_active = False
        if self.follow_dirty and not (self._capturing or self.busy):
            self.realign()

    def realign(self):
        """停手后重新截屏对齐一次。

        **绝不走 open_map()**：它会先 close_map()，而 close_map 在 busy 时会
        stop_worker()，把预加载好的 worker 杀掉，于是每次跟随都重付约 1 秒建索引。

        state.open() 递增 generation，在途的旧请求到达时 accepts() 即为假、
        直接被丢弃 —— 这就是「停止之前的匹配、改配最新一帧」，不必真去
        terminate worker（terminate 每次都要重建约 1 秒的索引）。
        """
        self.follow_dirty = False
        if not self.state.opened:
            return
        self.started = time.perf_counter()
        self.take_capture(self.state.open())

    def confirm_map_closed(self,token):
        if not self.state.accepts(token) or W.QApplication.activeModalWidget() is not None:
            return
        if self.mouse_busy() or self.busy or self._capturing:
            C.QTimer.singleShot(150,lambda:self.confirm_map_closed(token))
            return
        self.realign()

    def tick(self):
        edges = self.keys.edges()
        if W.QApplication.activeModalWidget() is not None:
            edges = set()
        foreground = win32gui.GetForegroundWindow()
        if self.enabled.isChecked():
            if 0x1B in edges:
                self.close_map()
            elif self.keys.hide_key in edges:
                if self.state.opened:
                    self.close_map()
                elif self.is_game(foreground) or self.demo_window is not None:
                    self.open_map()
            elif self.keys.toggle_key in edges and self.is_game(foreground):
                # A game can close its map through multiple inputs. Never invert
                # a guessed boolean: inspect the screen after this key instead.
                # Static local screenshots still need a genuine overlay toggle.
                if self.demo_window is not None and self.state.opened:
                    self.close_map()
                else:
                    self.open_map()
        if self.state.opened:
            # 「前台换成了别的窗口」只有在那个窗口不是我们自己的时候才算丢：
            # 刚点过面板时前台是我们的窗口，但那不代表用户离开了地图。
            own = foreground == int(self.winId())
            if self.foreground_lost() or (not own and foreground != self.target):
                self.close_map()
            elif self.rect_at_capture and self.overlay.isVisible() and self.capture_rect() != self.rect_at_capture:
                self.close_map()
                self.notify('窗口位置或大小已变化，请重新匹配')
            else:
                self.follow()
        if self.connection is not None:
            try:
                if self.connection.poll():
                    kind,payload = self.connection.recv()
                    if kind == 'ready':
                        self.ready = True
                        if not self.state.opened:
                            self.status.setText('就绪')
                        self.start_worker()
                    elif kind == 'error':
                        self.close_map(silent=True)
                        self.stop_worker()
                        self.notify('匹配失败：'+explain_failure(payload))
                    else:
                        self.busy = False
                        token,layer,message,candidate,elapsed,details = payload
                        if self.state.accepts(token):
                            # 两重保护都必要：交互结束的那个 tick 里 follow() 先跑，
                            # 那时结果还没轮询到（busy 仍为 True）所以会推迟，
                            # 随后才轮到结果分支 —— 只有 follow_dirty 挡得住这张
                            # 「交互期间截的旧帧」。
                            stale = self.follow_active or self.follow_dirty or self.mouse_busy()
                            self.last_result = dict(total_ms=(time.perf_counter()-self.started)*1000,
                                                    processing_ms=elapsed,result=details)
                            if stale:
                                # 这张是交互期间截的旧帧，注定被下一帧取代：安静丢弃，
                                # 让 follow() 用最新画面重来。绝不能在这里 notify ——
                                # 那正是「明明调好了却说无法匹配」的来源。
                                self.follow_dirty = True
                            elif layer is not None and not no_map_evidence(details):
                                # 只有真正显示出来的这一帧才配更新记忆身份：被顶掉的
                                # 旧帧若也写进去，会把 cached 门的下限逐帧往下拉 0.05。
                                self.cached_candidate = candidate
                                # 看到地图了，之前攒的「没有地图」次数作废。
                                self.no_map_streak = 0
                                self.overlay.display(layer,self.rect_at_capture,self.opacity.value()/100)
                                floor_label='地下室' if candidate.floor==-1 else f'{candidate.floor}F'
                                self.notify(f'{candidate.map_id.split("/")[-1]} · {floor_label}\n'
                                            f'{message} · {elapsed:.0f} ms')
                            elif no_map_evidence(details):
                                self.overlay.hide()
                                # 屏幕上只有游戏画面、没有地图结构 —— 最典型的是用户单击
                                # 关掉了游戏小地图（那一下松开同样会触发这次重新匹配）。
                                # 一次不算数，连续 NO_MAP_STREAK 次才退出，免得刚进地图
                                # 还没探索时被误判。
                                self.no_map_streak += 1
                                if self.no_map_streak >= NO_MAP_STREAK:
                                    self.close_map()
                                    self.notify('地图已关闭')
                                else:
                                    self.notify('正在确认地图已关闭…')
                                    C.QTimer.singleShot(250,lambda t=token:self.confirm_map_closed(t))
                            else:
                                # A rejected fit cannot establish that the game map
                                # remains open. Stop following ordinary gameplay;
                                # keep the cached identity for the next explicit try.
                                self.close_map(silent=True)
                                self.notify(advise(details,message)+' · 按重新识别重试')
                elif not self.process.is_alive():
                    self.close_map(silent=True)
                    self.stop_worker()
                    self.notify('匹配进程已退出，请重试')
            except (EOFError,OSError,BrokenPipeError) as error:
                self.close_map(silent=True)
                self.stop_worker()
                self.notify('匹配进程中断，请重试')

    def shutdown(self):
        self.mouse.release()        # 先摘监听，再拆窗口
        self.leave_demo()
        self.save()
        self.stop_worker()
        self.overlay.close()
        self.toast.close()


def main():
    parser = argparse.ArgumentParser(description='加页手记悬浮地图助手')
    parser.add_argument('--demo',type=Path,help='用本地截图演示，推理不读取配对答案')
    parser.add_argument('--local-test',action='store_true',help='启动后直接选择本地截图')
    parser.add_argument('--showcase',type=Path,help='保存真实界面截图并在演示后退出')
    args = parser.parse_args()
    if args.showcase and not args.demo:
        parser.error('--showcase requires --demo')
    native.dpi_aware()
    app = W.QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    font_stack()
    lock_path = DATA_ROOT/'out/mapmatching/ui.lock'
    lock_path.parent.mkdir(parents=True,exist_ok=True)
    lock = C.QLockFile(str(lock_path))
    if not lock.tryLock(0):
        W.QMessageBox.information(None,'加页手记','地图助手已经在运行，请点击屏幕右上角齿轮。')
        return
    ui = Companion()
    if args.demo:
        if not ui.open_screenshot(args.demo):
            parser.error('无法读取演示截图')
        if args.showcase:
            C.QTimer.singleShot(500,ui.retry)
    ui.show()
    if args.local_test and not args.demo:
        C.QTimer.singleShot(100,ui.choose_screenshot)
    if args.showcase:
        args.showcase.mkdir(parents=True,exist_ok=True)
        C.QTimer.singleShot(100,lambda: ui.grab().save(str(args.showcase/'gear.png')))
        def finish():
            if not hasattr(ui,'last_result'):
                if time.perf_counter()-ui.started < 30:
                    C.QTimer.singleShot(500,finish)
                    return
                (args.showcase/'error.txt').write_text(ui.status.text(),encoding='utf-8')
            else:
                ui.toggle_panel()
                app.processEvents()
                ui.grab().save(str(args.showcase/'panel.png'))
                app.primaryScreen().grabWindow(0).save(str(args.showcase/'desktop.png'))
                (args.showcase/'result.json').write_text(json.dumps(ui.last_result,ensure_ascii=False,indent=2),encoding='utf-8')
            app.quit()
        C.QTimer.singleShot(2000,finish)
    sys.exit(app.exec())


if __name__ == '__main__':
    mp.freeze_support()
    main()
