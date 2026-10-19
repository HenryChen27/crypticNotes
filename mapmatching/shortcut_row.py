from PySide6 import QtCore as C,QtGui as G,QtWidgets as W
from .theme import ChalkToggle

# Reuse the original desktop shortcut editor icon.
from .theme import EditButton
WrenchButton=EditButton

class ShortcutRow(W.QWidget):
    def __init__(self,label,key,edit,toggle=None):
        super().__init__();box=W.QHBoxLayout(self);box.setContentsMargins(0,0,0,0);box.setSpacing(5)
        self.label=W.QLabel();self.label.setMinimumWidth(0)
        self.label.setSizePolicy(W.QSizePolicy.Expanding,W.QSizePolicy.Preferred)
        self.edit=WrenchButton();self.edit.clicked.connect(edit)
        self.toggle=toggle if toggle is not None else ChalkToggle();self.toggle.setFixedSize(54,28)
        box.addWidget(self.label,1);box.addWidget(self.edit);box.addWidget(self.toggle)
        self.set_key(label,key)
    def set_key(self,label,key):self.label.setText(label+'（'+key+'）')
