"""Compact textured navigation matching the game's horizontal channel strip."""
from PySide6 import QtCore as C,QtGui as G,QtWidgets as W
from .theme import chalk_texture
import math

class ModuleTab(W.QAbstractButton):
    def __init__(self,label,kind,parent):
        super().__init__(parent);self.label=label;self.kind=kind
        self.setCheckable(True);self.setCursor(C.Qt.PointingHandCursor)
        self.setFixedHeight(53);self.setMinimumWidth(52 if kind==2 else 84)
        if kind==2:self.setFixedWidth(52)
        self.setAccessibleName(label or '总体设置');self.setToolTip(label or '总体设置')
    def paintEvent(self,event):
        p=G.QPainter(self);p.setRenderHint(G.QPainter.Antialiasing)
        active=self.isChecked()
        if active and self.kind!=2:
            # Crop past the texture's top/bottom feather so the highlight touches
            # the panel edge and the separator without a transparent inset.
            texture=chalk_texture(self.width(),self.height()+16,'light',.9,'rect',False,False)
            p.setOpacity(.88)
            p.drawImage(C.QRectF(self.rect()),texture,C.QRectF(0,16,self.width()*2,self.height()*2))
            p.setOpacity(1)
        color=G.QColor('#142732' if active and self.kind!=2 else '#d3dfe6' if active or self.underMouse() else '#c2d0db');p.setPen(G.QPen(color,1.6));p.setBrush(C.Qt.NoBrush)
        if self.kind==2:
            x=self.width()/2;y=self.height()/2
            # Same solid eight-tooth silhouette as the non-pet gear, with
            # a truly transparent centre and no button/medallion background.
            gear=G.QPainterPath()
            for i in range(64):
                angle=i*math.tau/64;radius=14 if i%8 in (1,2,3,4) else 10.8
                point=C.QPointF(x+math.cos(angle)*radius,y+math.sin(angle)*radius)
                gear.moveTo(point) if i==0 else gear.lineTo(point)
            gear.closeSubpath()
            hole=G.QPainterPath();hole.addEllipse(C.QPointF(x,y),5.5,5.5)
            p.setPen(C.Qt.NoPen);p.setBrush(color);p.drawPath(gear.subtracted(hole))
        if self.label:
            p.setFont(self.font());p.drawText(self.rect(),C.Qt.AlignCenter,self.label)
        if self.kind!=2:
            p.setPen(G.QPen(G.QColor(180,205,219,38),1));p.drawLine(self.width()-1,0,self.width()-1,self.height())
        if getattr(self,'available',False):
            p.setPen(C.Qt.NoPen);p.setBrush(G.QColor('#e05252'));p.drawEllipse(C.QPointF(self.width()-8,9),3.5,3.5)

    def set_update_available(self,value):
        self.available=value;self.setAccessibleDescription('有可用更新' if value else '');self.update()

class ModuleNavigation(W.QWidget):
    currentIndexChanged=C.Signal(int)
    def __init__(self):
        super().__init__();self.index=0;self.buttons=[];self.setFixedHeight(54)
        layout=W.QHBoxLayout(self);layout.setContentsMargins(0,0,0,1);layout.setSpacing(0)
        self.group=W.QButtonGroup(self)
        # Index 2 stays the settings gear (it is used by number elsewhere); PVP is index 3, drawn before the gear.
        self.buttons=[ModuleTab(label,i,self) for i,label in enumerate(('加页手记','小游戏','','禁选辅助'))]
        for i,stretch in ((0,5),(3,5),(1,4)):
            self.group.addButton(self.buttons[i],i);layout.addWidget(self.buttons[i],stretch)
        layout.addSpacing(12);self.group.addButton(self.buttons[2],2);layout.addWidget(self.buttons[2],0)
        self.buttons[0].setChecked(True);self.group.idClicked.connect(self.setCurrentIndex)
    def last_tab(self):
        """The right-most text tab on show: the dark plate of the strip ends with it."""
        return next(self.buttons[i] for i in (1,3,0) if not self.buttons[i].isHidden())
    def paintEvent(self,event):
        p=G.QPainter(self)
        edge=self.last_tab().geometry().right()
        p.fillRect(C.QRect(0,0,edge+1,self.height()),G.QColor(7,17,27,175))
        p.setPen(G.QPen(G.QColor(183,206,222,65),1))
        p.drawLine(0,self.height()-1,edge,self.height()-1)

    def currentIndex(self):return self.index
    def setCurrentIndex(self,index):
        if index not in (0,1,2,3) or self.buttons[index].isHidden():return
        self.buttons[index].setChecked(True)
        if index!=self.index:self.index=index;self.currentIndexChanged.emit(index)
