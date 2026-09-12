"""Qt-painted mist, chalk controls and an app-local font; no external renderer."""
from pathlib import Path
import math
import random
from PySide6 import QtCore as C, QtGui as G, QtWidgets as W
from functools import lru_cache


@lru_cache(maxsize=48)
def chalk_texture(width,height,bright=False,roughness=1.0,shape='rect',left_edge=True,right_edge=True):
    """Cached fine grain with a broken, feathered edge, painted at 2x."""
    import numpy as np
    w,h=max(2,width*2),max(2,height*2)
    rng=np.random.default_rng(23)
    yy,xx=np.mgrid[:h,:w]
    edges=[yy,h-1-yy]
    if left_edge:
        edges.append(xx)
    if right_edge:
        edges.append(w-1-xx)
    edge=np.minimum.reduce(edges).astype(float)
    if shape=='circle':
        edge=min(w,h)/2-.5-np.hypot(xx-(w-1)/2,yy-(h-1)/2)
    elif shape=='rounded':
        radius=8  # Four logical pixels; keep adjoining switch edges square.
        dx=np.maximum(radius-xx if left_edge else 0,
                      xx-(w-1-radius) if right_edge else 0)
        dy=np.maximum(radius-yy,yy-(h-1-radius))
        corner=radius-np.hypot(np.maximum(dx,0),np.maximum(dy,0))
        edge=np.minimum(edge,corner)
    grain=rng.normal(0,13,(h,w))
    feather=np.clip((edge-rng.uniform(0,5*roughness,(h,w)))/(9*roughness),0,1)
    rgba=np.zeros((h,w,4),np.uint8)
    dark = bright == 'dark'
    palette = (35,54,70) if dark else ((190,209,219) if bright else (158,181,197))
    gradient = 8*(1-yy/max(1,h-1)) + 5*np.sin(xx/max(1,w-1)*math.pi)-5
    for channel,base in enumerate(palette):
        rgba[:,:,channel]=np.clip(base+grain*(.35 if dark else 1)+gradient,0,255)
    rgba[:,:,3]=np.clip(feather*(235 if bright else 190)+rng.normal(0,8,(h,w))*feather,0,255)
    image=G.QImage(rgba.data,w,h,rgba.strides[0],G.QImage.Format_RGBA8888).copy()
    image.setDevicePixelRatio(2)
    return image


class ChalkButton(W.QPushButton):
    def __init__(self,text):
        super().__init__(text)
        self.setMinimumHeight(39)
        self.setCursor(C.Qt.PointingHandCursor)

    def paintEvent(self,event):
        p=G.QPainter(self)
        p.drawImage(self.rect(),chalk_texture(self.width(),self.height(),self.underMouse() or self.isDown(),.7,'rounded'))
        p.setPen(G.QColor('#152635'))
        p.setFont(self.font())
        p.drawText(self.rect(),C.Qt.AlignCenter,self.text())


class ChalkChoice(W.QWidget):
    """One switch surface; only the selected label has a chalk highlight."""
    currentIndexChanged=C.Signal(int)

    def __init__(self,items):
        super().__init__()
        self.items=list(items)
        self.index=0
        self.setMinimumHeight(42)
        self.setFocusPolicy(C.Qt.StrongFocus)
        self.setCursor(C.Qt.PointingHandCursor)

    def currentIndex(self):
        return self.index

    def currentData(self):
        return self.items[self.index][1]

    def setCurrentIndex(self,index):
        if 0<=index<len(self.items) and index!=self.index:
            self.index=index
            self.update()
            self.currentIndexChanged.emit(index)

    def mousePressEvent(self,event):
        if event.button()==C.Qt.LeftButton:
            self.setCurrentIndex(min(len(self.items)-1,int(event.position().x()*len(self.items)/self.width())))

    def keyPressEvent(self,event):
        if event.key()==C.Qt.Key_Space:
            event.ignore()  # Let the map editor use Space for panning.
        elif event.key() in (C.Qt.Key_Left,C.Qt.Key_Right):
            self.setCurrentIndex((self.index+(-1 if event.key()==C.Qt.Key_Left else 1))%len(self.items))
        else:
            super().keyPressEvent(event)

    def paintEvent(self,event):
        p=G.QPainter(self)
        cell=self.width()/len(self.items)
        for i,(label,_) in enumerate(self.items):
            left=round(i*cell)
            width=round((i+1)*cell)-left
            rect=C.QRectF(left,0,width,self.height())
            p.drawImage(rect,chalk_texture(width,self.height(),True if i==self.index else 'dark',
                                          .7,'rounded',left_edge=i==0,right_edge=i==len(self.items)-1))
            p.setPen(G.QColor('#172938' if i==self.index else '#b5c9d7'))
            p.setFont(self.font())
            p.drawText(rect,C.Qt.AlignCenter,label)


class ChalkToggle(ChalkChoice):
    toggled=C.Signal(bool)

    def __init__(self):
        super().__init__([('开',True),('关',False)])
        self.currentIndexChanged.connect(lambda _: self.toggled.emit(self.isChecked()))

    def isChecked(self):
        return self.currentData()

    def setChecked(self,checked):
        self.setCurrentIndex(0 if checked else 1)


class ChalkSlider(W.QSlider):
    def __init__(self,orientation=C.Qt.Horizontal):
        super().__init__(orientation)
        self.setMinimumHeight(26)
        self.setCursor(C.Qt.PointingHandCursor)

    def paintEvent(self,event):
        option=W.QStyleOptionSlider()
        self.initStyleOption(option)
        style=self.style()
        handle=style.subControlRect(W.QStyle.CC_Slider,option,W.QStyle.SC_SliderHandle,self)
        groove=style.subControlRect(W.QStyle.CC_Slider,option,W.QStyle.SC_SliderGroove,self)
        p=G.QPainter(self)
        track=C.QRect(groove.left(),self.height()//2-5,groove.width(),10)
        p.drawImage(track,chalk_texture(track.width(),10,'dark'))
        filled=C.QRect(track.left(),track.top(),max(1,handle.center().x()-track.left()),10)
        p.drawImage(filled,chalk_texture(filled.width(),10))
        knob=C.QRect(handle.center().x()-10,self.height()//2-10,21,21)
        p.drawImage(knob,chalk_texture(21,21,True,.5,'circle'))


class DelaySlider(ChalkSlider):
    def __init__(self):
        super().__init__(C.Qt.Horizontal)
        self.setRange(100,1000)
        self.setSingleStep(25)
        self.setPageStep(100)
        self.setValue(350)

    def currentData(self):
        return self.value()


def install_font(app):
    path = Path(__file__).resolve().parent/'assets/fonts/HYDiWRGJ.ttf'
    families = []
    if path.exists():
        font_id = G.QFontDatabase.addApplicationFont(str(path))
        families = G.QFontDatabase.applicationFontFamilies(font_id)
    family = families[0] if families else 'Microsoft YaHei UI'
    font = G.QFont(family)
    font.setPixelSize(16)
    app.setFont(font)
    return family, bool(families)


def stylesheet(family):
    return '''
QWidget { color: #d4e1e8; font-family: "%s"; font-size: 16px; }
QLabel { background: transparent; }
QLabel#title { color: #e3edf2; font-size: 29px; }
QLabel#muted { color: #9cadbb; font-size: 13px; }
QLabel#status { background: rgba(8,20,31,100); padding: 12px; border-left: 2px solid #859daf; }
QPushButton, QComboBox { background: rgba(111,143,163,32); border: 1px solid rgba(161,185,202,60); border-radius: 1px; padding: 8px 12px; }
QPushButton:hover, QComboBox:hover { background: rgba(145,172,190,70); color: #eef6fa; border-color: #859dae; }
QPushButton:checked, QPushButton#primary { background: #a7bdca; color: #142534; border-color: #c0d1db; }
QPushButton:checked:hover, QPushButton#primary:hover { background: #c1d2dc; }
QComboBox QAbstractItemView { background: #253b4c; color: #d4e1e8; selection-background-color: #a7bdca; selection-color: #142534; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #859dac; background: #253b4c; }
QCheckBox::indicator:checked { background: #b5c9d5; }
QSlider::groove:horizontal { height: 2px; background: #526a7c; }
QSlider::sub-page:horizontal { background: #acbfce; }
QSlider::handle:horizontal { background: #d0dce4; width: 9px; margin: -5px 0; border-radius: 1px; }
QToolTip { background: #263b4c; color: #d4e1e8; border: 1px solid #718a9c; padding: 6px; }
''' % family


class MistPanel(W.QFrame):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setAttribute(C.Qt.WA_TranslucentBackground)
        self.texture = None

    def paintEvent(self,event):
        if self.texture is None or self.texture.size()!=self.size():
            import numpy as np
            h,w = self.height(),self.width()
            noise = np.random.default_rng(5).integers(0,256,(h,w),dtype=np.uint8)
            rgba = np.zeros((h,w,4),np.uint8)
            rgba[:,:,:3]=noise[:,:,None]
            rgba[:,:,3]=9
            self.texture=G.QImage(rgba.data,w,h,rgba.strides[0],G.QImage.Format_RGBA8888).copy()
        p=G.QPainter(self)
        p.setRenderHint(G.QPainter.Antialiasing)
        rect=C.QRectF(self.rect()).adjusted(1,1,-1,-1)
        gradient=G.QLinearGradient(rect.topLeft(),rect.bottomRight())
        gradient.setColorAt(0,G.QColor(40,61,79,247))
        gradient.setColorAt(.55,G.QColor(30,49,65,247))
        gradient.setColorAt(1,G.QColor(13,27,39,250))
        p.fillRect(rect,gradient)
        p.drawImage(0,0,self.texture)
        glow=G.QRadialGradient(rect.width()*.4,30,rect.width()*.8)
        glow.setColorAt(0,G.QColor(156,183,204,24))
        glow.setColorAt(1,G.QColor(156,183,204,0))
        p.fillRect(rect,glow)
        p.setPen(G.QPen(G.QColor(164,191,207,60),1))
        p.drawLine(18,1,self.width()-18,1)
        p.drawLine(18,self.height()-2,self.width()-18,self.height()-2)
        # Fine worn vertical edges, cached geometry rather than animation.
        rng=random.Random(5)
        for x in (1,self.width()-2):
            for y in range(8,self.height()-8,6):
                p.setPen(G.QColor(156,183,204,rng.randint(15,65)))
                p.drawLine(x,y,x,y+3)


class GearButton(W.QPushButton):
    def __init__(self):
        super().__init__()
        self.setFixedSize(46,46)
        self.setCursor(C.Qt.PointingHandCursor)
        self.setToolTip('加页手记 · 设置')
        self.setAccessibleName('设置')

    def paintEvent(self,event):
        p=G.QPainter(self)
        p.setRenderHint(G.QPainter.Antialiasing)
        p.drawImage(C.QRect(1,1,44,44),chalk_texture(44,44,False,.35,'circle'))
        p.drawImage(C.QRect(2,2,42,42),chalk_texture(42,42,'dark',.35,'circle'))
        p.translate(23,23)
        path=G.QPainterPath()
        for i in range(64):
            a=2*math.pi*i/64
            radius=15 if i%8 in (1,2,3,4) else 11.6
            x,y=radius*math.cos(a),radius*math.sin(a)
            path.moveTo(x,y) if i==0 else path.lineTo(x,y)
        path.closeSubpath()
        p.setPen(C.Qt.NoPen)
        gradient=G.QLinearGradient(0,-15,0,15)
        gradient.setColorAt(0,G.QColor('#e0eaf0' if self.underMouse() else '#c3d3de'))
        gradient.setColorAt(1,G.QColor('#b5c8d5' if self.underMouse() else '#a9becd'))
        p.setBrush(gradient)
        p.drawPath(path)
        p.drawImage(C.QRect(-7,-7,14,14),chalk_texture(14,14,'dark',.2,'circle'))


class EditButton(ChalkButton):
    """铅笔，表示「修改」。

    画实心剪影而不是描边：按钮只有 28×30，3px 描边一上去整支笔就糊成一团。
    沿笔轴取法向 ±2.6 得到笔杆两边，再让它们在前端收成一个 50° 的锥尖。
    比例很要紧：笔杆要细长（约 4:1），笔尖锥要占够长度 —— 短一档就成了电池。
    """

    def __init__(self):
        super().__init__('')
        self.setFixedSize(28,30)
        self.setMinimumHeight(30)
        self.setToolTip('修改快捷键')
        self.setAccessibleName('修改快捷键')

    def paintEvent(self,event):
        p=G.QPainter(self)
        p.setRenderHint(G.QPainter.Antialiasing)
        if self.underMouse():
            p.drawImage(self.rect(),chalk_texture(28,30,'dark',.5,'rounded'))
        body=G.QPainterPath()           # 笔尖朝左下，笔尾平口朝右上
        body.moveTo(21.98,10.70)        # 笔尾 +n 侧
        body.lineTo(11.73,20.95)        # 笔杆前端 +n 侧
        body.lineTo(6.00,23.00)         # 笔尖
        body.lineTo(8.05,17.27)         # 笔杆前端 -n 侧
        body.lineTo(18.30,7.02)         # 笔尾 -n 侧
        body.closeSubpath()
        gradient=G.QLinearGradient(0,7,0,23)
        gradient.setColorAt(0,G.QColor('#e0eaf0' if self.underMouse() else '#c3d3de'))
        gradient.setColorAt(1,G.QColor('#b5c8d5' if self.underMouse() else '#a9becd'))
        p.setPen(C.Qt.NoPen)
        p.setBrush(gradient)
        p.drawPath(body)
        p.setPen(G.QPen(G.QColor(20,33,45,235),1.6))
        p.drawLine(C.QPointF(15.83,9.49),C.QPointF(19.51,13.17))


class SegmentedChoice(W.QWidget):
    currentIndexChanged=C.Signal(int)

    def __init__(self,labels):
        super().__init__()
        self.buttons=[]
        self.index=0
        layout=W.QHBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(7)
        self.group=W.QButtonGroup(self)
        self.group.setExclusive(True)
        for i,label in enumerate(labels):
            button=W.QPushButton(label)
            button.setCheckable(True)
            self.group.addButton(button,i)
            self.buttons.append(button)
            layout.addWidget(button)
        self.buttons[0].setChecked(True)
        self.group.idClicked.connect(self.setCurrentIndex)

    def currentIndex(self):
        return self.index

    def setCurrentIndex(self,index):
        if index!=self.index:
            self.index=index
            self.buttons[index].setChecked(True)
            self.currentIndexChanged.emit(index)
