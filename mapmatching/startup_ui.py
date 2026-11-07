"""Noninteractive desktop startup pet: the body in its matching pose with the
skin's spinner turning, shown where the pet was last left so the real one can
take over in place."""
import json
from PySide6 import QtCore as C,QtGui as G,QtWidgets as W
from .paths import DATA_ROOT
from .appearance import create_pet, skin_name

class StartupPet(W.QWidget):
    def __init__(self):
        super().__init__(None,C.Qt.Tool|C.Qt.FramelessWindowHint|C.Qt.WindowStaysOnTopHint|C.Qt.WindowTransparentForInput|C.Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(C.Qt.WA_TranslucentBackground)
        self.setAttribute(C.Qt.WA_ShowWithoutActivating)
        self.setAttribute(C.Qt.WA_TransparentForMouseEvents)
        self.matching=True
        try:settings=json.loads((DATA_ROOT/'out/mapmatching/ui_settings.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):settings={}
        self.pet=create_pet(self,skin_name(settings))
        try:self.pet.set_scale(max(.75,min(1.5,float(settings.get('pet_scale',1.)))))
        except (TypeError,ValueError,AttributeError):pass
        self.pet.enable(True);self.pet.play('matching')
        self.clock=C.QElapsedTimer();self.clock.start()
        self.spin=C.QTimer(self);self.spin.setInterval(33);self.spin.timeout.connect(self.update);self.spin.start()
        self.move(saved_position(settings,self.size()))
    def paintEvent(self,event):
        self.pet.paint()
        p=G.QPainter(self);self.pet.paint_waiting(p,self.clock.elapsed());p.end()
    def closeEvent(self,event):self.pet.timer.stop();self.spin.stop();super().closeEvent(event)


def saved_position(settings,size):
    """The gear's last saved top-left, when it is still on a screen; otherwise
    the default top-right corner the companion also falls back to."""
    point=settings.get('pos')
    if (isinstance(point,list) and len(point)==2
            and all(isinstance(v,(int,float)) and not isinstance(v,bool) for v in point)):
        target=C.QPoint(int(point[0]),int(point[1]))
        if W.QApplication.screenAt(target) is not None:
            return target
    area=W.QApplication.primaryScreen().availableGeometry()
    return C.QPoint(area.right()-20-size.width(),area.top()+30)
