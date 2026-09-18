"""Manual single-image map enrollment; coordinates always refer to source pixels."""
from pathlib import Path
import math
from PySide6 import QtCore as C, QtGui as G, QtWidgets as W
from .theme import MistPanel, ChalkButton, ChalkChoice
from .panel_dialogs import PanelDialog
from .src.map_library import add_map


class FloorCanvas(W.QWidget):
    changed=C.Signal()

    def __init__(self):
        super().__init__()
        self.setMinimumSize(360,300)
        self.setSizePolicy(W.QSizePolicy.Expanding,W.QSizePolicy.Expanding)
        self.pixmap=G.QPixmap()
        self.boxes={}
        self.floor=1
        self.start=None
        self.drag=None
        self.zoom=1.0
        self.pan=C.QPointF()
        self.space=False
        self.pan_start=None
        self.guide_position=None
        self.setMouseTracking(True)
        self.setFocusPolicy(C.Qt.StrongFocus)
        self.setCursor(C.Qt.CrossCursor)

    def image_rect(self):
        if self.pixmap.isNull():
            return C.QRectF()
        size=self.pixmap.size().scaled(self.size()-C.QSize(12,12),C.Qt.KeepAspectRatio)
        width,height=size.width()*self.zoom,size.height()*self.zoom
        return C.QRectF((self.width()-width)/2+self.pan.x(),(self.height()-height)/2+self.pan.y(),width,height)

    def fit(self):
        self.zoom=1.0; self.pan=C.QPointF()
        self.start=self.drag=self.pan_start=None
        self.update()

    def zoom_at(self,position,factor):
        if self.pixmap.isNull() or self.start is not None:
            return
        before=self.image_rect()
        anchor=C.QPointF((position.x()-before.x())/before.width(),(position.y()-before.y())/before.height())
        self.zoom=max(.5,min(20.,self.zoom*factor))
        after=self.image_rect()
        self.pan+=position-C.QPointF(after.x()+anchor.x()*after.width(),after.y()+anchor.y()*after.height())
        self.update()

    def wheelEvent(self,event):
        self.setFocus()
        self.zoom_at(event.position(),1.2**(event.angleDelta().y()/120))
        event.accept()

    def keyPressEvent(self,event):
        if event.key()==C.Qt.Key_Space:
            self.space=True
            self.setCursor(C.Qt.OpenHandCursor)
            self.update()
            event.accept()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self,event):
        if event.key()==C.Qt.Key_Space and not event.isAutoRepeat():
            self.space=False
            self.setCursor(C.Qt.CrossCursor)
            self.update()
            event.accept()
        else:
            super().keyReleaseEvent(event)

    def focusOutEvent(self,event):
        self.space=False; self.pan_start=None; self.start=self.drag=None
        self.setCursor(C.Qt.CrossCursor)
        self.guide_position=None
        self.update()
        super().focusOutEvent(event)

    def leaveEvent(self,event):
        self.guide_position=None
        self.update()
        super().leaveEvent(event)

    def point(self,p):
        r=self.image_rect()
        return C.QPointF(max(0,min(self.pixmap.width(),(p.x()-r.x())/r.width()*self.pixmap.width())),
                         max(0,min(self.pixmap.height(),(p.y()-r.y())/r.height()*self.pixmap.height())))

    def mousePressEvent(self,event):
        self.setFocus()
        self.guide_position=event.position()
        self.update()
        if event.button()==C.Qt.MiddleButton or (event.button()==C.Qt.LeftButton and self.space):
            self.pan_start=event.position()
            self.setCursor(C.Qt.ClosedHandCursor)
            return
        if event.button()==C.Qt.LeftButton and self.image_rect().contains(event.position()):
            self.start=self.point(event.position())
            self.drag=C.QRectF(self.start,self.start)

    def mouseMoveEvent(self,event):
        self.guide_position=event.position()
        self.update()
        if self.pan_start is not None:
            self.pan+=event.position()-self.pan_start
            self.pan_start=event.position()
            self.update()
            return
        if self.start is not None:
            self.drag=C.QRectF(self.start,self.point(event.position())).normalized()
            self.update()

    def mouseReleaseEvent(self,event):
        self.guide_position=event.position() if self.rect().contains(event.position().toPoint()) else None
        self.update()
        if self.pan_start is not None:
            self.pan_start=None
            self.setCursor(C.Qt.OpenHandCursor if self.space else C.Qt.CrossCursor)
            return
        if event.button()==C.Qt.LeftButton and self.start is not None:
            rect=C.QRectF(self.start,self.point(event.position())).normalized()
            if rect.width()>=20 and rect.height()>=20:
                self.boxes[self.floor]=[math.floor(rect.left()),math.floor(rect.top()),math.ceil(rect.right()),math.ceil(rect.bottom())]
                self.changed.emit()
            self.start=self.drag=None
            self.update()

    def paintEvent(self,event):
        p=G.QPainter(self)
        p.setRenderHint(G.QPainter.SmoothPixmapTransform)
        r=self.image_rect()
        if self.pixmap.isNull():
            p.setPen(G.QColor('#b9cbd7'))
            p.drawText(self.rect(),C.Qt.AlignCenter,'选择原图，再拖动框选楼层')
            return
        p.drawPixmap(r,self.pixmap,C.QRectF(self.pixmap.rect()))
        sx,sy=r.width()/self.pixmap.width(),r.height()/self.pixmap.height()
        boxes=dict(self.boxes)
        if self.drag is not None:
            boxes[self.floor]=[self.drag.left(),self.drag.top(),self.drag.right(),self.drag.bottom()]
        for floor,(x,y,X,Y) in boxes.items():
            color=G.QColor({1:'#d8e8f1',2:'#8fbdcc',-1:'#c0afd2'}[floor])
            p.setPen(G.QPen(color,2))
            fill=G.QColor(color); fill.setAlpha(28); p.setBrush(fill)
            rect=C.QRectF(r.x()+x*sx,r.y()+y*sy,(X-x)*sx,(Y-y)*sy)
            p.drawRect(rect)
            p.drawText(rect.adjusted(6,3,-3,-3),C.Qt.AlignTop|C.Qt.AlignLeft,'地下室' if floor==-1 else f'{floor}F')
        # Screen-space guides stay thin at any zoom and never affect source boxes.
        if self.guide_position is not None and not self.space and self.pan_start is None:
            visible=r.intersected(C.QRectF(self.rect()))
            if visible.contains(self.guide_position):
                pos=self.guide_position
                p.save()
                p.setClipRect(visible)
                for color,width in (('#172631',3),('#d8e8f1',1)):
                    pen=G.QPen(G.QColor(color),width,C.Qt.DashLine)
                    pen.setCosmetic(True)
                    pen.setDashPattern([5/width,4/width])
                    p.setPen(pen)
                    p.drawLine(C.QPointF(visible.left(),pos.y()),C.QPointF(visible.right(),pos.y()))
                    p.drawLine(C.QPointF(pos.x(),visible.top()),C.QPointF(pos.x(),visible.bottom()))
                p.restore()


class ImportJob(C.QThread):
    completed=C.Signal(object)
    failed=C.Signal(str)

    def __init__(self,args,parent):
        super().__init__(parent)
        self.args=args

    def run(self):
        try:
            self.completed.emit(add_map(*self.args))
        except Exception as error:
            self.failed.emit(str(error))


class MapImportDialog(PanelDialog):
    def __init__(self,root,difficulty,mode,parent=None):
        super().__init__(parent,880,720)     # 右对齐主窗口、点到框外自动关，见 panel_dialogs
        self.root=root
        self.path=None
        self.job=None
        self.result_record=None
        outer=W.QVBoxLayout(self); outer.setContentsMargins(0,0,0,0)
        panel=MistPanel(); outer.addWidget(panel)
        box=W.QVBoxLayout(panel); box.setContentsMargins(22,18,22,18)
        title=W.QLabel('录入新地图'); title.setObjectName('title'); box.addWidget(title)
        row=W.QHBoxLayout()
        self.name=W.QLineEdit(); self.name.setPlaceholderText('地图名称'); self.name.setMaxLength(60)
        self.name.setStyleSheet('background:rgba(20,35,49,160);padding:8px;border:1px solid #607789;border-radius:4px;')
        row.addWidget(self.name,1)
        choose=ChalkButton('选择原图'); choose.clicked.connect(self.choose); row.addWidget(choose)
        box.addLayout(row)
        row=W.QHBoxLayout()
        self.difficulty=ChalkChoice([('困难','hard'),('噩梦','nightmare')])
        self.difficulty.setCurrentIndex(int(difficulty=='nightmare'))
        self.party=ChalkChoice([('单人','solo'),('多人','duo')])
        self.party.setCurrentIndex(int(mode=='duo'))
        row.addWidget(self.difficulty); row.addWidget(self.party); box.addLayout(row)
        self.party.setVisible(difficulty=='nightmare')
        self.difficulty.currentIndexChanged.connect(lambda i:self.party.setVisible(i==1))
        self.canvas=FloorCanvas(); box.addWidget(self.canvas,1)
        row=W.QHBoxLayout()
        self.floor=ChalkChoice([('1F',1),('2F',2),('地下室',-1)])
        self.floor.currentIndexChanged.connect(self.floor_changed)
        row.addWidget(self.floor,1)
        whole=ChalkButton('整张为此层'); whole.clicked.connect(self.whole); row.addWidget(whole)
        clear=ChalkButton('清除此层'); clear.clicked.connect(self.clear); row.addWidget(clear)
        fit=ChalkButton('适应窗口'); fit.clicked.connect(self.canvas.fit); row.addWidget(fit)
        box.addLayout(row)
        hint=W.QLabel('滚轮缩放 · 空格 + 拖动 / 中键平移 · 左键框选楼层')
        hint.setObjectName('muted'); box.addWidget(hint)
        self.status=W.QLabel('框选完整楼层，避开图例和小缩略图；多层图片请逐层框选。')
        self.status.setWordWrap(True); self.status.setObjectName('muted'); box.addWidget(self.status)
        self.canvas.changed.connect(self.summary)
        row=W.QHBoxLayout()
        cancel=ChalkButton('取消'); cancel.clicked.connect(self.reject); row.addWidget(cancel)
        self.save_button=ChalkButton('保存并入库'); self.save_button.clicked.connect(self.save_map); row.addWidget(self.save_button)
        box.addLayout(row)

    def choose(self):
        path,_=W.QFileDialog.getOpenFileName(self,'选择完整地图原图',str(self.root),'地图图片 (*.png *.jpg *.jpeg *.bmp)')
        if not path:
            return
        pixmap=G.QPixmap(path)
        if pixmap.isNull():
            self.status.setText('无法读取这张图片')
            return
        self.path=Path(path)
        self.canvas.pixmap=pixmap; self.canvas.boxes={}; self.canvas.fit()
        self.name.setText(self.path.stem[:60]); self.summary()

    def floor_changed(self,index):
        self.canvas.floor=self.floor.currentData(); self.canvas.update()

    def keyPressEvent(self,event):
        if event.key()==C.Qt.Key_Space:
            self.canvas.setFocus()
            self.canvas.keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def whole(self):
        if not self.canvas.pixmap.isNull():
            self.canvas.boxes[self.canvas.floor]=[0,0,self.canvas.pixmap.width(),self.canvas.pixmap.height()]
            self.canvas.update(); self.summary()

    def clear(self):
        self.canvas.boxes.pop(self.canvas.floor,None); self.canvas.update(); self.summary()

    def summary(self):
        labels=['地下室' if f==-1 else f'{f}F' for f in self.canvas.boxes]
        self.status.setText('已标注：'+('、'.join(labels) if labels else '无，请拖动框选楼层'))

    def save_map(self):
        if self.path is None:
            self.status.setText('请先选择原图'); return
        regions=[dict(floor=f,bbox=b) for f,b in self.canvas.boxes.items()]
        difficulty=self.difficulty.currentData()
        args=(self.root,self.path,self.name.text(),difficulty,self.party.currentData() if difficulty=='nightmare' else None,regions)
        self.job=ImportJob(args,self)
        self.job.completed.connect(self.saved)
        self.job.failed.connect(self.failed)
        self.setEnabled(False)
        self.status.setText('正在提取结构并入库…')
        self.job.start()

    def saved(self,record):
        self.job.wait()
        self.result_record=record
        self.accept()

    def failed(self,message):
        self.job.wait()
        self.setEnabled(True); self.status.setText(message)

    def reject(self):
        if self.job is None or not self.job.isRunning():
            super().reject()

    def closeEvent(self,event):
        if self.job is not None and self.job.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)
