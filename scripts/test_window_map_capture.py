import sys,time
from pathlib import Path
import numpy as np
from PySide6 import QtCore as C,QtWidgets as W
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mapmatching.window_map_capture import WindowSnapshot
app=W.QApplication([])
w=W.QLabel('Capture test');w.setWindowTitle('Window snapshot fixture');w.setStyleSheet('background:rgb(30,70,130)');w.resize(640,400);w.move(80,100);w.show();hwnd=int(w.winId())
for _ in range(20):app.processEvents();time.sleep(.03)
cover=W.QWidget(None,C.Qt.Window|C.Qt.FramelessWindowHint|C.Qt.WindowStaysOnTopHint);cover.setStyleSheet('background:red');cover.setGeometry(50,50,800,600);cover.show();app.processEvents()
s=WindowSnapshot(hwnd)
for _ in range(100):
 app.processEvents();time.sleep(.03)
 if s.result is not None:break
assert s.result is not None,s.error
pixels,rect=s.result
assert pixels.shape[:2]==(rect[3],rect[2])
b,g,r=np.median(pixels[50:-30,30:-30],axis=(0,1));assert b>100 and r<60,(b,g,r)
print('PASS: covered window, physical coordinates',rect,pixels.shape)
cover.close();w.close()
