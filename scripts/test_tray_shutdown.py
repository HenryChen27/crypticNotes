"""Local UI exit smoke test, without changing saved preferences."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def main():
    from PySide6 import QtCore as C, QtWidgets as W
    from mapmatching.ui import Companion, font_stack, native
    native.dpi_aware()
    app = W.QApplication([])
    app.setQuitOnLastWindowClosed(False)
    font_stack()
    ui = Companion()
    ui.save = lambda: None
    ui.show()
    def check():
        assert ui.tray.isVisible()
        assert ui.tray_menu.actions()[-1].text() == '\u9000\u51fa'
        ui.tray_menu.actions()[-1].trigger()
    C.QTimer.singleShot(1800, check)
    app.exec()
    assert ui.process is None
    assert not ui.tray.isVisible()
    assert not ui.overlay.isVisible()
    assert not ui.gear.exit_zone.isVisible()
    assert not ui.timer.isActive()
    print('PASS: tray Exit released recognition worker, timers and auxiliary windows')

if __name__ == '__main__':
    main()
