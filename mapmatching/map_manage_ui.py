"""地图库浏览器：列出每一张地图，把它们从匹配里移除或恢复。

**删除就是移除** —— 原图和特征文件原地不动，只是把登记条目收起来，随时可以恢复。
内置和用户录入的图没有区别，所以「删除」按钮已经没有，确认框也不再写「无法撤销」。
"""
from pathlib import Path
from PySide6 import QtCore as C, QtGui as G, QtWidgets as W
from .theme import MistPanel, ChalkButton, ChalkChoice, chalk_texture
from .panel_dialogs import PanelDialog, ThumbnailPopup
from .src.map_admin import context_text, floor_text, list_maps, set_enabled

FILTERS = [('全部', ''), ('困难', 'hard'), ('噩梦·单人', 'nightmare/solo'), ('噩梦·双人', 'nightmare/duo')]
SECTIONS = [('active', '可用'), ('disabled', '已停用')]


class MapRow(W.QWidget):
    """一行地图条目。点行身（不是右侧的按钮）弹缩略图。"""

    picked = C.Signal()

    def mousePressEvent(self, event):
        if event.button() == C.Qt.LeftButton:
            self.picked.emit()
        super().mousePressEvent(event)


class RowButton(ChalkButton):
    """Row-sized chalk button. The stock one is 39px tall — 59 of those is 2300px."""

    def __init__(self, text, width=68):
        super().__init__(text)
        self.setFixedSize(width, 30)

    def paintEvent(self, event):
        if self.isEnabled():
            super().paintEvent(event)
            return
        # ChalkButton paints itself, so a plain setEnabled(False) would still look live.
        p = G.QPainter(self)
        p.setOpacity(.32)
        p.drawImage(self.rect(), chalk_texture(self.width(), self.height(), False, .7, 'rounded'))
        p.setPen(G.QColor('#152635'))
        p.setFont(self.font())
        p.drawText(self.rect(), C.Qt.AlignCenter, self.text())


class ConfirmDialog(PanelDialog):
    def __init__(self, title, body, action, parent):
        super().__init__(parent)          # 不传尺寸：确认框保持默认居中，不右对齐
        self.setFixedWidth(360)
        outer = W.QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        panel = MistPanel(); outer.addWidget(panel)
        layout = W.QVBoxLayout(panel); layout.setContentsMargins(22, 22, 22, 22); layout.setSpacing(14)
        heading = W.QLabel(title); heading.setObjectName('title'); layout.addWidget(heading)
        text = W.QLabel(body); text.setWordWrap(True); text.setObjectName('muted'); layout.addWidget(text)
        row = W.QHBoxLayout()
        # NoFocus on both: with focus on a button, Enter would fire it, and Enter must not delete.
        for label, slot in (('取消', self.reject), (action, self.accept)):
            button = ChalkButton(label)
            button.setFocusPolicy(C.Qt.NoFocus)
            button.clicked.connect(slot)
            row.addWidget(button)
        layout.addLayout(row)


class MapManageDialog(PanelDialog):
    def __init__(self, root, difficulty, mode, parent=None):
        super().__init__(parent, 780, 620)
        self.root = root
        self.context = (difficulty, mode)
        self.changed = False
        self.total = 0
        self.active = 0
        self.picked_id = None
        self.picked_row = None
        # 建完列表要滚过去的那一行（新增/恢复之后用），和本次建出来的 map_id → 行。
        self._reveal = None
        self._row_of = {}
        self.popup = ThumbnailPopup(self)
        outer = W.QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        panel = MistPanel(); panel.setObjectName('panel'); outer.addWidget(panel)
        box = W.QVBoxLayout(panel); box.setContentsMargins(22, 18, 22, 18); box.setSpacing(10)
        title = W.QLabel('管理地图'); title.setObjectName('title'); box.addWidget(title)
        self.filter = ChalkChoice(FILTERS)
        self.filter.currentIndexChanged.connect(lambda _: self.rebuild())
        box.addWidget(self.filter)
        self.summary = W.QLabel(''); self.summary.setObjectName('muted'); box.addWidget(self.summary)
        self.scroll = W.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(W.QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(C.Qt.ScrollBarAlwaysOff)
        self.scroll.setFocusPolicy(C.Qt.NoFocus)
        self.body = W.QWidget(); self.body.setObjectName('mapbody')
        self.rows = W.QVBoxLayout(self.body)
        self.rows.setContentsMargins(0, 0, 8, 0); self.rows.setSpacing(4)
        self.rows.addStretch(1)
        self.scroll.setWidget(self.body)
        box.addWidget(self.scroll, 1)
        self.status = W.QLabel('移除只是从匹配里摘掉，原图和楼层信息都会保留，随时可以恢复。')
        self.status.setWordWrap(True); self.status.setObjectName('muted'); box.addWidget(self.status)
        row = W.QHBoxLayout()
        add = ChalkButton('新增地图'); add.clicked.connect(self.add_map); row.addWidget(add)
        row.addStretch(1)
        close = ChalkButton('关闭'); close.clicked.connect(self.accept); row.addWidget(close)
        box.addLayout(row)
        self.reload()

    # ---- data -----------------------------------------------------------
    def reload(self):
        self.records = list_maps(self.root)
        self.total = len(self.records)
        # total 把「已停用」也算进去了，所以它不能拿去当「能匹配几张」报给用户。
        self.active = sum(1 for r in self.records if r['state'] == 'active')
        self.rebuild()

    def visible(self):
        key = self.filter.currentData()
        if not key:
            return list(self.records)
        difficulty, _, mode = key.partition('/')
        return [r for r in self.records if r['difficulty'] == difficulty and (r['mode'] or '') == mode]

    def remaining(self, record):
        """同难度/人数下还剩几张可匹配的 —— 删到 0 那个模式就没法匹配了。"""
        return len([r for r in self.records if r['state'] == 'active' and r['difficulty'] == record['difficulty']
                    and r['mode'] == record['mode']])

    def focus_on(self, map_id, difficulty=None, mode=None):
        """重建列表，并把 `map_id` 那一行滚进视野。

        没有这一步时新增的图排在列表最末尾（第 60 行、约 2800 px 之下），而滚动位置
        停在顶部，用户看到的是「录入完了但列表里没有这张」。恢复同理：它会回到原来
        那一行，可能在视野外，也可能在「已停用」那一组里。

        当前筛选把这张图挡在外面时先切到看得见它的那一档 —— 否则滚到哪儿都没用。
        `difficulty`/`mode` 只有在 caller 已经知道时才传（新增那条路），未知就从
        刚读到的 records 里查。
        """
        self._reveal = map_id
        self.reload()
        if map_id in self._row_of or not self.filter.currentData():
            return                       # 已经看得见，或本来就是「全部」
        if difficulty is None:
            record = next((r for r in self.records if r['map_id'] == map_id), None)
            if record is None:
                return
            difficulty, mode = record['difficulty'], record['mode']
        key = f'{difficulty}/{mode}' if mode else difficulty
        # setCurrentIndex 会发 currentIndexChanged，那边接着 rebuild，_reveal 还在。
        self.filter.setCurrentIndex(next((i for i, (_, data) in enumerate(FILTERS) if data == key), 0))

    def reveal_row(self):
        """把 `_reveal` 那一行滚进视野；没找到就留着，等筛选变了再试。

        **必须推到下一轮事件循环**：rebuild 把老行 `deleteLater()` 掉，那些行要到
        下一轮才真正死。当场 `ensureWidgetVisible` 其实滚对了，但紧接着老行一死、
        列表重新排版，滚动位置被重新算回顶部附近 —— 实测停在第 47 px，等于没滚。
        """
        if self._reveal is None:
            return
        row = self._row_of.get(self._reveal)
        if row is None:
            return
        self._reveal = None
        C.QTimer.singleShot(0, lambda: self._scroll_to(row))

    def _scroll_to(self, row):
        if row.parent() is None or not self.isVisible():
            return                       # 这一轮重建已经把它换掉了
        self.rows.activate()
        self.scroll.ensureWidgetVisible(row, 0, 40)

    def rebuild(self):
        # 行是重建的，缩略图锚在旧行上，一律先收掉；选中态也跟着没有意义了。
        self.hide_popup()
        while self.rows.count() > 1:
            widget = self.rows.takeAt(0).widget()
            if widget is not None:
                # takeAt only unmanages it; without setParent(None) the stale row keeps
                # painting at its old geometry until the event loop gets around to it.
                widget.setParent(None)
                widget.deleteLater()
        self._row_of = {}
        shown = self.visible()
        # 内置和自建不再分开列 —— 它们本来就躺在同一棵树里、进同一张表，
        # 再分两组只会让「同名的两张图」看起来像两回事。
        groups = {'active': [r for r in shown if r['state'] == 'active'],
                  'disabled': [r for r in shown if r['state'] == 'disabled']}
        position = 0
        for key, heading in SECTIONS:
            group = groups[key]
            if not group:
                continue
            self.rows.insertWidget(position, self.section(f'{heading} {len(group)}')); position += 1
            for record in group:
                widget = self.line(record)
                self._row_of[record['map_id']] = widget
                self.rows.insertWidget(position, widget); position += 1
        counts = [sum(1 for r in self.records if r['state'] == 'active'),
                  sum(1 for r in self.records if r['state'] == 'disabled')]
        self.summary.setText(f'共 {self.total} 张 · 可用 {counts[0]} · 已停用 {counts[1]}')
        self.reveal_row()

    def section(self, text):
        label = W.QLabel(text); label.setObjectName('section')
        return label

    def line(self, record):
        widget = MapRow()
        widget.setObjectName('maprow-on' if record['map_id'] == self.picked_id else 'maprow')
        widget.setCursor(C.Qt.PointingHandCursor)
        widget.setToolTip('点击查看缩略图')
        widget.picked.connect(lambda: self.pick(record, widget))
        line = W.QHBoxLayout(widget); line.setContentsMargins(12, 5, 12, 5); line.setSpacing(10)
        name = W.QLabel(record['name']); name.setObjectName('mapname')
        name.setToolTip(record['map_id'])
        line.addWidget(name, 1)
        context = context_text(record['difficulty'], record['mode'])
        if not record['writable']:
            context += ' · 只读'
        quality = W.QLabel(context); quality.setObjectName('muted'); quality.setFixedWidth(104)
        line.addWidget(quality)
        floors = W.QLabel(floor_text(record['floors']) or '—')
        floors.setObjectName('muted'); floors.setFixedWidth(104)
        line.addWidget(floors)
        if record['stale']:
            # 几何改过但索引还没跟上。不是「重新录入」—— 图和框都还在，
            # 缺的只是把特征重抽一遍（`python -m mapmatching build-index`）。
            stale = W.QLabel('需重建索引'); stale.setObjectName('muted'); stale.setFixedWidth(88)
            line.addWidget(stale)
        line.addWidget(self.action(record))
        return widget

    def action(self, record):
        # 没有「删除」按钮了：任何一张图的移除都是可恢复的（原图和特征都留在盘上）。
        button = RowButton('恢复' if record['state'] == 'disabled' else '移除', 68)
        button.clicked.connect(lambda: self.mutate(record, restore=record['state'] == 'disabled'))
        if not record['writable']:
            button.setEnabled(False)
            button.setCursor(C.Qt.ArrowCursor)
            button.setToolTip('这一份在程序目录里，只读')
        return button

    # ---- thumbnail ------------------------------------------------------
    def hide_popup(self):
        row = self.picked_row
        self.picked_id = None
        self.picked_row = None
        self.popup.hide()
        # 选中态挂在 objectName 上，收起时不还原的话那一行会一直亮着。
        if row is not None:
            row.setObjectName('maprow')
            row.style().unpolish(row); row.style().polish(row)

    def on_picked_row(self, point):
        row = self.picked_row
        return row is not None and C.QRect(row.mapToGlobal(C.QPoint(0, 0)), row.size()).contains(point)

    def pick(self, record, widget):
        """点行身：换一张就弹它的缩略图，点的是同一张就收起。"""
        if record['map_id'] == self.picked_id:
            self.hide_popup()
            return
        previous = self.picked_row
        self.picked_id = record['map_id']
        self.picked_row = widget
        for row, name in ((previous, 'maprow'), (widget, 'maprow-on')):
            if row is not None:
                row.setObjectName(name)
                # 改了 objectName 必须重新 polish，否则 QSS 里那条选中样式不会生效。
                row.style().unpolish(row); row.style().polish(row)
        source = Path(self.root)/str(record.get('source') or '')
        caption = f'{record["name"]}  ·  {floor_text(record["floors"]) or "未标注楼层"}'
        self.popup.show_map(source, record.get('regions'), caption,
                            widget.mapToGlobal(C.QPoint(0, 0)), self.geometry())

    def inside(self, point):
        # 缩略图小窗算这个框的一部分：点它不该被当成点到框外、把整个框关掉。
        return super().inside(point) or (self.popup.isVisible() and self.popup.geometry().contains(point))

    def eventFilter(self, watched, event):
        if event.type() == C.QEvent.MouseButtonPress and self.popup.isVisible():
            point = event.globalPosition().toPoint()
            # 点在别的地方就收起缩略图。点在它自己那一行上不在这里收 —— 那是
            # 「再点一次收起」，交给 pick()，否则会先收掉再被 pick() 弹回来。
            if not self.popup.geometry().contains(point) and not self.on_picked_row(point):
                self.hide_popup()
        return super().eventFilter(watched, event)

    def hideEvent(self, event):
        self.hide_popup()
        super().hideEvent(event)

    # ---- actions --------------------------------------------------------
    def confirm(self, record, restore):
        if restore:
            return ConfirmDialog('恢复地图', f'确定恢复「{record["name"]}」？\n它会重新参与匹配。', '恢复', self)
        body = f'确定从匹配中移除「{record["name"]}」？\n原图和已录入的楼层信息都会保留，随时可以恢复。'
        if self.remaining(record) <= 1:
            body += f'\n\n这是「{context_text(record["difficulty"], record["mode"])}」的最后一张可用地图，移除后该模式将无法匹配。'
        return ConfirmDialog('管理地图', body, '移除', self)

    def mutate(self, record, restore):
        dialog = self.confirm(record, restore)
        if dialog.exec() != W.QDialog.Accepted:
            return
        try:
            set_enabled(self.root, record['map_id'], restore)
        except Exception as error:
            self.status.setText(str(error))
            return
        self.changed = True
        verb = '已恢复' if restore else '已移除'
        self.status.setText(f'{verb}：{record["name"]}')
        # 恢复会回到原来那一行，可能在视野外 —— 让用户看得见它回来了。
        if restore:
            self.focus_on(record['map_id'])
        else:
            self.reload()

    def add_map(self):
        from .map_import_ui import MapImportDialog
        difficulty, mode = self.context
        dialog = MapImportDialog(self.root, difficulty, mode, self)
        if dialog.exec() == W.QDialog.Accepted:
            self.changed = True
            self.status.setText(f'已录入：{dialog.result_record["name"]}')
            # 新条目排在列表最后，滚过去让用户看见 —— 否则像是没录进去。
            self.focus_on(dialog.result_record['map_id'], difficulty, mode)

    def keyPressEvent(self, event):
        if event.key() == C.Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)
