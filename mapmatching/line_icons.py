"""Single-stroke line icons in the game's map-legend manner: white 1.5 px strokes
on a 24×24 grid, round caps, no fills except small dots.

One table serves both clients: `scripts/generate_line_icons_java.py` writes
`android/.../LineIcon.java` from `ICONS`, so a new icon is added here only.
Primitives: ('L', x1, y1, x2, y2) line, ('P', [(x, y), …]) polyline,
('C', cx, cy, r) circle, ('A', cx, cy, r, start°, span°) arc (Qt angle sense),
('D', cx, cy, r) filled dot.
"""
from PySide6 import QtCore as C, QtGui as G, QtWidgets as W

ICONS = {
    'map':        [('P', [(3, 4), (9, 2), (16, 5), (21, 3), (21, 21), (15, 23), (9, 20), (3, 22), (3, 4)]), ('L', 9, 2, 9, 20), ('L', 16, 5, 16, 22)],
    'author':     [('P', [(4, 20), (14, 6), (19, 4), (17, 9), (8, 18)]), ('L', 4, 20, 10, 14)],
    'difficulty': [('P', [(12, 3), (7, 10), (9, 16), (12, 21), (15, 16), (17, 10), (12, 3)]), ('C', 12, 15, 2.2)],
    'route':      [('P', [(4, 19), (9, 12), (14, 16), (20, 5)]), ('D', 4, 19, 1.6), ('D', 20, 5, 1.6)],
    'party':      [('C', 9, 8, 3), ('C', 16.5, 9, 2.5), ('P', [(3, 20), (4, 15), (9, 13), (14, 15), (15, 20)]), ('P', [(15.5, 18), (17, 15), (20, 15), (21.5, 18)])],
    'opacity':    [('C', 12, 12, 8), ('L', 12, 4, 12, 20), ('L', 12, 8, 19, 10), ('L', 12, 12, 20, 12), ('L', 12, 16, 19, 14)],
    'retry':      [('A', 12, 12, 8, -60, 300), ('P', [(17, 2), (20, 6), (15.5, 6.5)])],
    'hide':       [('P', [(3, 12), (7, 7), (12, 6), (17, 7), (21, 12), (17, 17), (12, 18), (7, 17), (3, 12)]), ('C', 12, 12, 3), ('L', 4, 20, 20, 4)],
    'floor':      [('P', [(12, 4), (21, 9), (12, 14), (3, 9), (12, 4)]), ('P', [(3, 14), (12, 19), (21, 14)])],
    'pet':        [('C', 12, 12, 8), ('L', 8, 9, 10, 11), ('L', 10, 9, 8, 11), ('L', 14, 9, 16, 11), ('L', 16, 9, 14, 11), ('L', 9, 16, 15, 16)],
    'font':       [('P', [(4, 19), (9.5, 5), (15, 19)]), ('L', 6.5, 14, 12.5, 14), ('C', 19, 16, 2.5), ('L', 21.5, 13, 21.5, 19)],
    'key':        [('P', [(4, 7), (20, 7), (20, 17), (4, 17), (4, 7)]), ('L', 8, 12, 16, 12)],
    'record':     [('P', [(3, 8), (9, 8), (11, 5), (13, 5), (15, 8), (21, 8), (21, 19), (3, 19), (3, 8)]), ('C', 12, 13, 3.5)],
    'games':      [('P', [(6, 8), (18, 8), (21, 12), (20, 18), (16, 16), (8, 16), (4, 18), (3, 12), (6, 8)]), ('L', 8, 11, 8, 14), ('L', 6.5, 12.5, 9.5, 12.5), ('D', 16, 11, 1.2), ('D', 18.5, 13.5, 1.2)],
    'library':    [('P', [(4, 4), (14, 4), (16, 6), (16, 20), (4, 20), (4, 4)]), ('L', 7, 8, 13, 8), ('L', 7, 12, 13, 12), ('L', 20, 6, 20, 20)],
    'import':     [('L', 12, 3, 12, 14), ('P', [(8, 10), (12, 14), (16, 10)]), ('P', [(4, 16), (4, 20), (20, 20), (20, 16)])],
    'update':     [('C', 12, 12, 9), ('L', 12, 16.5, 12, 8), ('P', [(8, 11.5), (12, 7.5), (16, 11.5)])],
    'tools':      [('L', 5, 19, 13, 11), ('C', 16, 8, 4), ('L', 14, 10, 19, 5)],
    'exit':       [('P', [(10, 3), (4, 3), (4, 21), (10, 21)]), ('L', 8, 12, 20, 12), ('P', [(16, 8), (20, 12), (16, 16)])],
    'remove':     [('L', 5, 7, 19, 7), ('P', [(7, 7), (8, 21), (16, 21), (17, 7)]), ('P', [(9, 7), (10, 4), (14, 4), (15, 7)]), ('L', 11, 10.5, 11, 18), ('L', 13, 10.5, 13, 18)],
    'check':      [('P', [(4, 13), (9.5, 18.5), (20, 6)])],
    'question':   [('P', [(8, 9), (9, 6), (12, 5), (15, 6), (16, 9), (13.5, 12), (12, 14), (12, 16)]), ('D', 12, 20, 1.5)],
    'warn':       [('P', [(12, 3), (21, 20), (3, 20), (12, 3)]), ('L', 12, 10, 12, 15), ('D', 12, 17.8, 1.3)],
    'timer':      [('C', 12, 12, 8), ('P', [(12, 7), (12, 12), (16, 14)])],
    'pin':        [('P', [(12, 21), (6, 13), (6, 9), (12, 3), (18, 9), (18, 13), (12, 21)]), ('C', 12, 9, 2.5)],
    'power':      [('P', [(5, 19), (5, 12), (10, 6), (19, 5), (18, 14), (12, 19), (5, 19)]), ('L', 5, 19, 15, 9)],
    'folder':     [('P', [(3, 6), (9, 6), (11, 8), (21, 8), (21, 19), (3, 19), (3, 6)])],
    'image':      [('P', [(3, 4), (21, 4), (21, 20), (3, 20), (3, 4)]), ('P', [(4, 18), (9, 12), (13, 16), (16, 13), (20, 18)]), ('C', 16, 8.5, 1.8)],
    'more':       [('D', 5, 12, 1.7), ('D', 12, 12, 1.7), ('D', 19, 12, 1.7)],
    'edit':       [('P', [(4, 20), (5, 15), (16, 4), (20, 8), (9, 19), (4, 20)]), ('L', 13, 7, 17, 11)],
    'search':     [('C', 10, 10, 6), ('L', 14.5, 14.5, 21, 21)],
    'filter':     [('P', [(3, 5), (21, 5), (14, 13), (14, 20), (10, 18), (10, 13), (3, 5)])],
}
DANGER = ('exit', 'remove')          # the only red icons, like the game's 异象


def paint_icon(painter, name, x, y, size, color=None, width=1.5):
    """Draw `name` with its top-left corner at (x, y), scaled to `size` px."""
    shapes = ICONS.get(name)
    if not shapes:
        return
    painter.save()
    painter.setRenderHint(G.QPainter.Antialiasing)
    painter.translate(x, y)
    painter.scale(size/24., size/24.)
    colour = G.QColor(color or ('#d97977' if name in DANGER else '#dbe5ec'))
    pen = G.QPen(colour, width*24./size)
    pen.setCapStyle(C.Qt.RoundCap)
    pen.setJoinStyle(C.Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(C.Qt.NoBrush)
    for shape in shapes:
        kind = shape[0]
        if kind == 'L':
            painter.drawLine(C.QPointF(shape[1], shape[2]), C.QPointF(shape[3], shape[4]))
        elif kind == 'P':
            painter.drawPolyline(G.QPolygonF([C.QPointF(px, py) for px, py in shape[1]]))
        elif kind == 'C':
            painter.drawEllipse(C.QPointF(shape[1], shape[2]), shape[3], shape[3])
        elif kind == 'A':
            cx, cy, r, start, span = shape[1:]
            painter.drawArc(C.QRectF(cx-r, cy-r, 2*r, 2*r), int(start*16), int(span*16))
        elif kind == 'D':
            painter.setBrush(colour)
            painter.setPen(C.Qt.NoPen)
            painter.drawEllipse(C.QPointF(shape[1], shape[2]), shape[3], shape[3])
            painter.setPen(pen)
            painter.setBrush(C.Qt.NoBrush)
    painter.restore()


def icon_pixmap(name, size=20, color=None, dpr=1.):
    pixmap = G.QPixmap(int(size*dpr), int(size*dpr))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(C.Qt.transparent)
    painter = G.QPainter(pixmap)
    paint_icon(painter, name, 0, 0, size, color)
    painter.end()
    return pixmap


class IconLabel(W.QWidget):
    """A field label with its legend icon in front, as the game lists its
    landmarks: icon, then the word. Replaces a bare QLabel in a row."""

    def __init__(self, text, icon, width=None, size=18):
        super().__init__()
        self.icon, self.size, self._text = icon, size, text
        box = W.QHBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        box.addSpacing(size+2)
        self.label = W.QLabel(text)
        box.addWidget(self.label, 1)
        if width:
            self.setFixedWidth(width)

    def setText(self, text):
        self.label.setText(text)

    def text(self):
        return self.label.text()

    def paintEvent(self, event):
        painter = G.QPainter(self)
        paint_icon(painter, self.icon, 0, (self.height()-self.size)/2, self.size,
                   color=None if self.isEnabled() else '#8294a1')


class KeyCap(W.QWidget):
    """The PC client's key hint: a small outlined cap with the key name."""

    def __init__(self, key='G', muted=False):
        super().__init__()
        self.key, self.muted = key, muted
        self.setFixedHeight(20)
        self.setMinimumWidth(26)

    def setKey(self, key):
        self.key = key
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        metrics = G.QFontMetrics(self.font())
        return C.QSize(max(26, metrics.horizontalAdvance(self.key)+14), 20)

    def paintEvent(self, event):
        painter = G.QPainter(self)
        painter.setRenderHint(G.QPainter.Antialiasing)
        colour = G.QColor('#8294a1' if self.muted else '#d3dfe6')
        rect = C.QRectF(self.rect()).adjusted(.5, .5, -.5, -1.5)
        painter.setPen(G.QPen(colour, 1))
        painter.setBrush(G.QColor(17, 33, 46, 150))
        painter.drawRoundedRect(rect, 3, 3)
        painter.setPen(G.QPen(G.QColor(colour.red(), colour.green(), colour.blue(), 110), 1))
        painter.drawLine(rect.left()+3, rect.bottom()+1, rect.right()-3, rect.bottom()+1)
        font = self.font()
        font.setPixelSize(11)
        painter.setFont(font)
        painter.setPen(colour)
        painter.drawText(rect, C.Qt.AlignCenter, self.key)
