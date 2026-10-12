"""Actual HWND capture while a different window covers the target completely."""
import sys
from pathlib import Path
from PySide6 import QtCore as C,QtGui as G,QtWidgets as W
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mapmatching.game_scene_watch import WindowSceneWatch

app=W.QApplication([])
target=W.QLabel();target.setWindowTitle('Scene watch local fixture');target.setScaledContents(True);target.resize(900,540);target.move(50,80)
target.setPixmap(G.QPixmap(str(ROOT/'out/before.png')));target.show()
cover=W.QWidget(None,C.Qt.Window|C.Qt.FramelessWindowHint|C.Qt.WindowStaysOnTopHint)
cover.setStyleSheet('background:#47dd82;');cover.setGeometry(50,80,900,540)
watch=WindowSceneWatch(int(target.winId()))
result={'stage':'before','triggered':False,'error':None}
def matched(score):
    result['triggered']=True;result['at_stage']=result['stage'];result['score']=score;watch.stop();app.quit()
def failed(message):result['error']=message;watch.stop();app.quit()
watch.changed.connect(matched);watch.failed.connect(failed)
def before2():target.setPixmap(G.QPixmap(str(ROOT/'out/before2.png')))
def after():result['stage']='after';target.setPixmap(G.QPixmap(str(ROOT/'out/after.png')))
C.QTimer.singleShot(200,lambda:(cover.show(),cover.raise_()))
C.QTimer.singleShot(2500,before2)
C.QTimer.singleShot(5500,after)
C.QTimer.singleShot(15000,lambda:(watch.stop(),app.quit()))
watch.start();app.exec();cover.close();target.close()
assert not result['error'],result
assert result['triggered'] and result['at_stage']=='after',result
print('Passed HWND capture under full occlusion; only matching event triggered:',result,flush=True)
