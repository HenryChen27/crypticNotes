from PySide6 import QtCore as C, QtGui as G, QtWidgets as W

class SpeechBubble(W.QLabel):
    """Non-activating, click-through speech with a tail aimed at the mascot."""
    def __init__(self):
        super().__init__('', None, C.Qt.Tool | C.Qt.FramelessWindowHint |
                         C.Qt.WindowStaysOnTopHint | C.Qt.WindowDoesNotAcceptFocus |
                         C.Qt.WindowTransparentForInput)
        self.setAttribute(C.Qt.WA_TranslucentBackground)
        self.setAttribute(C.Qt.WA_ShowWithoutActivating)
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
        p = G.QPainter(self)
        p.setRenderHint(G.QPainter.Antialiasing)
        rect = C.QRectF(8, 1, self.width()-17, self.height()-2)
        path = G.QPainterPath()
        path.addRoundedRect(rect, 11, 11)
        if self.tail:
            triangle = G.QPainterPath()
            x = rect.left() if self.tail == 'left' else rect.right()
            tip = 1 if self.tail == 'left' else self.width()-2
            triangle.moveTo(x, self.tail_y-6)
            triangle.lineTo(tip, self.tail_y)
            triangle.lineTo(x, self.tail_y+6)
            triangle.closeSubpath()
            path = path.united(triangle)
        gradient = G.QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, G.QColor(45,61,73,248))
        gradient.setColorAt(1, G.QColor(22,33,43,248))
        p.setBrush(gradient)
        p.setPen(G.QPen(G.QColor(153,177,190,150), 1))
        p.drawPath(path)
        p.end()
        super().paintEvent(event)

