"""Bake the existing desktop doll matching loop for lightweight Android loading."""
import os,sys
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6 import QtWidgets as W,QtGui as G,QtCore as C
from mapmatching.appearance.player import PetAnimation
app=W.QApplication.instance() or W.QApplication([])
class Frame(W.QWidget):
    progress=0.
    factor=1
    def paintEvent(self,event):self.animation.paint(self.progress,render_scale=.34*self.factor,origin=(8*self.factor,22*self.factor))
w=Frame();w.setAttribute(C.Qt.WA_TranslucentBackground);w.setFixedSize(128,144);w.matching=True;w.animation=PetAnimation(w);w.animation.mood='matching';w.animation.timer.stop()
sheet=G.QImage(128*8,144*6,G.QImage.Format_RGBA8888);sheet.fill(C.Qt.transparent)
for i in range(44):
 w.progress=i/44
 frame=G.QPixmap(128,144);frame.fill(C.Qt.transparent);w.render(frame)
 painter=G.QPainter(sheet);painter.drawPixmap((i%8)*128,(i//8)*144,frame);painter.end()
out=ROOT/'android/app/src/main/assets/loading';out.mkdir(parents=True,exist_ok=True);sheet.save(str(out/'doll-matching.png'))
# Android 9+ decodes a high-resolution animated WebP one frame at a time.
# Keep the small sheet only as the Android 8 fallback.
from PIL import Image
high=[]
w.setFixedSize(384,432)
w.factor=3
for i in range(44):
 w.progress=i/44
 frame=G.QPixmap(384,432);frame.fill(C.Qt.transparent);w.render(frame)
 q=frame.toImage().convertToFormat(G.QImage.Format_RGBA8888)
 high.append(Image.frombytes('RGBA',(q.width(),q.height()),bytes(q.constBits())))
high[0].save(out/'doll-matching.webp',save_all=True,append_images=high[1:],duration=50,loop=0,lossless=True,method=4)

print('Doll loading loop:',(out/'doll-matching.png').stat().st_size,'bytes, 44 frames / 2200ms')
