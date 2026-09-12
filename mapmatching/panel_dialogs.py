"""助手自己那些窗口的公共行为：跟主窗口右对齐、点到框外就收起、点条目弹缩略图。

放这里而不是 `theme.py`（那是冻结文件），也不能放 `ui.py` —— 两个使用者都是在
`ui.py` 的方法里被延迟 import 的，反过来 import ui 会成环。
"""
from pathlib import Path
from PySide6 import QtCore as C, QtGui as G, QtWidgets as W
from .theme import MistPanel

# 缩略图最长边。再大就只是白占屏幕边上的地方 —— 这里要的是「认出是哪张图」。
THUMBNAIL = 260
GAP = 10
# 裁到 1F 之后四周留一点白，免得地图内容直接顶到边框上。
FLOOR_MARGIN = 0.02
# 和录入界面 FloorCanvas 同一套楼层配色，看的时候不用重新建立对应关系。
FLOOR_COLOR = {1: '#d8e8f1', 2: '#8fbdcc', -1: '#c0afd2'}


def screen_area():
    return W.QApplication.primaryScreen().availableGeometry()


def own_dialog_open():
    """现在前台是不是助手自己的对话框。

    「用户切回游戏」和「用户打开了我们的框」都会让主窗口失活，但只有前者该把设置
    面板收起来 —— 从面板点开「管理地图」时把面板收掉，用户回来会莫名其妙。
    我们的框都是 exec() 的模态框，所以问 activeModalWidget 就够。
    """
    app = W.QApplication.instance()
    if app is None:
        return False
    widget = app.activeModalWidget()
    return isinstance(widget, W.QDialog) and widget.isVisible()


def align_right(dialog, parent, gap=0):
    """右边缘贴住主窗口右边缘，纵向与主窗口顶对齐，最后夹回屏幕内。

    要右对齐而不是居中：主窗口是往左长的 —— `toggle_panel` 始终保住右边缘、
    宽度随面板开关变化，所以右边缘才是那个不动的锚。
    """
    area = screen_area()
    width, height = dialog.width(), dialog.height()
    if parent is not None and parent.isVisible():
        frame = parent.frameGeometry()
        x, y = frame.right() + 1 - width - gap, frame.top()
    else:
        x, y = area.right() + 1 - width, area.top() + 60
    dialog.move(max(area.left(), min(x, area.right() + 1 - width)),
                max(area.top(), min(y, area.bottom() + 1 - height)))


class PanelDialog(W.QDialog):
    """无边框助手对话框，点到框外或切到别的程序就自动关闭。

    摆放交给子类：大框（管理地图 / 新增地图）右对齐主窗口，确认框保持默认居中。
    """

    def __init__(self, parent, width=None, height=None):
        super().__init__(parent, C.Qt.Dialog | C.Qt.FramelessWindowHint)
        self.setAttribute(C.Qt.WA_TranslucentBackground)
        if width and height:
            area = screen_area()
            self.resize(min(width, area.width()-40), min(height, area.height()-40))
            align_right(self, parent)

    def showEvent(self, event):
        super().showEvent(event)
        app = W.QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def hideEvent(self, event):
        app = W.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        super().hideEvent(event)

    def inside(self, point):
        """这个全局坐标算不算「在框里」。子类可以把手下的弹出小窗也算进来。"""
        return self.geometry().contains(point)

    def eventFilter(self, watched, event):
        # 用应用级过滤器而不是 focusOut：模态框会把框外的点击直接吃掉，
        # 那些点击根本走不到我们自己的任何控件上。
        if event.type() == C.QEvent.MouseButtonPress and W.QApplication.activeModalWidget() is self:
            if not self.inside(event.globalPosition().toPoint()):
                self.reject()
        return False

    def event(self, event):
        # 点到别的进程（游戏、桌面、别的窗口）时那条鼠标事件进了别人的消息队列，
        # 我们什么都收不到，只能靠失活。activeModalWidget 那道判断是为了不误伤
        # 「我们自己又开了一个框」——那时失活的是父框，不该被关掉。
        #
        # **判定必须延到下一轮事件循环**：开子框（确认框）时，`QDialog` 构造完
        # 还没 `show()`，这一刻 `activeModalWidget()` 仍然返回 self、子框也不可见，
        # 当场分不出「用户切到游戏」和「我们自己要开框」。判错的后果是点「移除」
        # 时把整个管理框一起 reject 掉 —— 确认框跟着消失，用户看到的是「框一闪，
        # 列表没了，也没改成」，正是「移除好像没成功」。
        if event.type() == C.QEvent.WindowDeactivate and W.QApplication.activeModalWidget() is self:
            C.QTimer.singleShot(0, self._dismiss_if_alone)
        return super().event(event)

    def _dismiss_if_alone(self):
        """延后一轮再决定收不收，见 `event()`。"""
        if not self.isVisible():
            return
        app = W.QApplication.instance()
        active = app.activeModalWidget() or app.activeWindow()
        # 顶上来的若是我们自己的另一个框（确认框 / 录入框 / 管理框），这次失活是
        # 我们自己造成的，宿主框要留着；切到别的进程时这两个都会是 None。
        if isinstance(active, W.QDialog) and active is not self:
            return
        self.reject()


class ThumbnailPopup(W.QWidget):
    """点地图条目时弹在列表旁边的缩略图小窗，并画出录入时框的楼层。

    刻意不接收激活（WindowDoesNotAcceptFocus + WA_ShowWithoutActivating）：
    否则弹出它本身就会让宿主对话框失活，直接触发「点到框外就收起」把自己关掉。
    """

    def __init__(self, parent=None):
        super().__init__(parent, C.Qt.Tool | C.Qt.FramelessWindowHint | C.Qt.WindowStaysOnTopHint
                         | C.Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(C.Qt.WA_TranslucentBackground)
        self.setAttribute(C.Qt.WA_ShowWithoutActivating)
        outer = W.QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        panel = MistPanel(); outer.addWidget(panel)
        box = W.QVBoxLayout(panel); box.setContentsMargins(12, 12, 12, 10); box.setSpacing(8)
        self.image = W.QLabel()
        self.image.setAlignment(C.Qt.AlignCenter)
        box.addWidget(self.image)
        self.caption = W.QLabel()
        self.caption.setObjectName('muted')
        self.caption.setWordWrap(True)
        self.caption.setFixedWidth(THUMBNAIL)
        box.addWidget(self.caption)

    @staticmethod
    def _boxes(regions):
        """把 regions 里能用的 bbox 拿出来，并返回 1F 那一个。"""
        boxes = []
        for region in regions or []:
            if not isinstance(region, dict):
                continue
            box, floor = region.get('bbox'), region.get('floor')
            if not isinstance(box, (list, tuple)) or len(box) != 4:
                continue
            try:
                boxes.append((tuple(float(v) for v in box), floor))
            except (TypeError, ValueError):
                continue
        return boxes, next((b for b, f in boxes if f == 1), None)

    @staticmethod
    def _clip_rect(box, size):
        """1F 的框 + 一圈留白，夹回图片范围内。"""
        x, y, X, Y = box
        pad = max(6.0, FLOOR_MARGIN*max(X-x, Y-y))
        left, top = max(0, int(x-pad)), max(0, int(y-pad))
        right, bottom = min(size.width(), int(X+pad)), min(size.height(), int(Y+pad))
        rect = C.QRect(left, top, right-left, bottom-top)
        return rect if rect.width() > 4 and rect.height() > 4 else None

    def render(self, source, regions):
        """按缩略图尺寸**解码**，而不是整张读完再缩。

        原图动辄 4000 px 宽：整张解码要几十 MB 和几百毫秒，QImageReader 直接
        按目标尺寸解码则只付缩略图的代价。所以这里不用 QPixmap(path)。

        **只画 1F**：这些原图是「三条楼层竖着拼起来」的长图（829x1915 那种），
        整张缩出来只有一根细条，谁也认不出是哪张。裁到 1F 之后既好认、弹窗也小。
        裁的是 1F 的框（不是「图的上半部分」），所以框画歪了这里就跟着歪 ——
        看到不对就说明录入的框需要改。没有 1F 的图（当前一张都没有）退回整张。
        """
        boxes, first = self._boxes(regions)
        reader = G.QImageReader(str(source))
        reader.setAutoTransform(True)
        size = reader.size()
        if not size.isValid() or not size.width() or not size.height():
            return G.QPixmap()
        clip = self._clip_rect(first, size) if first else None
        shown = clip.size() if clip else size
        if clip:
            reader.setClipRect(clip)
        scale = min(THUMBNAIL/shown.width(), THUMBNAIL/shown.height(), 1.0)
        if scale < 1.0:
            reader.setScaledSize(C.QSize(max(1, int(shown.width()*scale)),
                                         max(1, int(shown.height()*scale))))
        image = reader.read()
        if image.isNull():
            return G.QPixmap()
        pixmap = G.QPixmap.fromImage(image)
        sx, sy = pixmap.width()/shown.width(), pixmap.height()/shown.height()
        painter = G.QPainter(pixmap)
        painter.setRenderHint(G.QPainter.Antialiasing)
        origin_x, origin_y = (clip.left(), clip.top()) if clip else (0, 0)
        for box, floor in boxes:
            # 裁到 1F 时只画 1F 自己：别的楼层根本不在画面里，画了也是画在边上。
            if clip and floor != 1:
                continue
            x, y, X, Y = box
            rect = C.QRectF((x-origin_x)*sx, (y-origin_y)*sy, (X-x)*sx, (Y-y)*sy)
            color = G.QColor(FLOOR_COLOR.get(floor, '#d8e8f1'))
            painter.setPen(G.QPen(color, 2))
            fill = G.QColor(color); fill.setAlpha(30); painter.setBrush(fill)
            painter.drawRect(rect)
            painter.drawText(rect.adjusted(5, 3, -3, -3), C.Qt.AlignTop | C.Qt.AlignLeft,
                             '地下室' if floor == -1 else f'{floor}F')
        painter.end()
        return pixmap

    def show_map(self, source, regions, caption, anchor, beside):
        """`anchor` 是那一行的全局左上角，`beside` 是宿主对话框的 geometry。"""
        pixmap = self.render(Path(source), regions)
        if pixmap.isNull():
            self.image.setPixmap(G.QPixmap())
            self.image.setText('原图读取失败')
            self.image.setFixedSize(THUMBNAIL, 120)
        else:
            self.image.setText('')
            self.image.setPixmap(pixmap)
            self.image.setFixedSize(pixmap.size())
        self.caption.setText(caption)
        self.adjustSize()
        area = screen_area()
        x = beside.left()-self.width()-GAP
        if x < area.left():
            x = beside.right()+1+GAP
        self.move(max(area.left(), min(x, area.right()+1-self.width())),
                  max(area.top(), min(anchor.y(), area.bottom()+1-self.height())))
        self.show()
        self.raise_()
