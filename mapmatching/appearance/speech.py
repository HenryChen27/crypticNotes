import sys
from PySide6 import QtCore as C, QtGui as G, QtWidgets as W

class SpeechBubble(W.QLabel):
    """Non-activating, click-through speech with a tail aimed at the mascot."""
    def __init__(self):
        super().__init__('', None, C.Qt.Tool | C.Qt.FramelessWindowHint |
                         C.Qt.WindowStaysOnTopHint | C.Qt.WindowDoesNotAcceptFocus |
                         C.Qt.WindowTransparentForInput)
        self.setAttribute(C.Qt.WA_TranslucentBackground)
        self.setAttribute(C.Qt.WA_ShowWithoutActivating)
        if sys.platform == 'darwin':
            # Qt::Tool hides itself whenever the app loses focus; a hint the user
            # never gets to read is worse than none.
            self.setAttribute(C.Qt.WA_MacAlwaysShowToolWindow)
        self.setTextFormat(C.Qt.PlainText)
        self.setContentsMargins(19, 12, 19, 12)
        self.tail = 'right'
        self.tail_y = 22
        self.setStyleSheet('color:#dbe5ec;background:transparent;border:0;font-size:13px;')

    def point_at(self, point, enabled=True):
        self.tail = ('left' if point.x() < self.x() else 'right') if enabled else None
        self.tail_y = max(15, min(self.height()-15, point.y()-self.y()))
        self.update()

    def paintEvent(self, event):
        # Same chalk surface as the settings panel's controls (feathered,
        # grainy, no hard outline), so the bubble reads as the doll's own
        # voice rather than a system tooltip. The tail is a short hand-drawn
        # wedge in the surface's own ink.
        from ..theme import chalk_texture
        p = G.QPainter(self)
        p.setRenderHint(G.QPainter.Antialiasing)
        p.setRenderHint(G.QPainter.SmoothPixmapTransform)
        rect = C.QRect(8, 1, self.width()-17, self.height()-2)
        p.drawImage(rect, chalk_texture(rect.width(), rect.height(), 'deep', 1.0, 'rounded'))
        if self.tail:
            wedge = G.QPainterPath()
            x = rect.left()+3 if self.tail == 'left' else rect.right()-3
            tip = 0 if self.tail == 'left' else self.width()-1
            wedge.moveTo(x, self.tail_y-7)
            wedge.quadTo((x+tip)/2, self.tail_y-3, tip, self.tail_y)
            wedge.quadTo((x+tip)/2, self.tail_y+2, x, self.tail_y+5)
            wedge.closeSubpath()
            p.setPen(C.Qt.NoPen)
            p.setBrush(G.QColor(19, 32, 43, 232))
            p.drawPath(wedge)
        p.end()
        super().paintEvent(event)

