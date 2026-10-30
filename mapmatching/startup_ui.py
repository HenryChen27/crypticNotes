"""Noninteractive desktop startup pet; no badge, text or progress icon."""
from PySide6 import QtCore as C,QtWidgets as W
from .appearance.player import PetAnimation

class StartupPet(W.QWidget):
    def __init__(self):
        super().__init__(None,C.Qt.Tool|C.Qt.FramelessWindowHint|C.Qt.WindowStaysOnTopHint|C.Qt.WindowTransparentForInput|C.Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(C.Qt.WA_TranslucentBackground)
        self.setAttribute(C.Qt.WA_ShowWithoutActivating)
        self.setAttribute(C.Qt.WA_TransparentForMouseEvents)
        self.matching=True
        self.pet=PetAnimation(self);self.pet.enable(True);self.pet.play('matching')
        area=W.QApplication.primaryScreen().availableGeometry()
        self.move(area.right()-20-self.width(),area.top()+30)
    def paintEvent(self,event):self.pet.paint()
    def closeEvent(self,event):self.pet.timer.stop();super().closeEvent(event)
