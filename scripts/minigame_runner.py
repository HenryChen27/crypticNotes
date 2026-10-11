"""Optional standalone Qt WebEngine host. Never imported by the map plugin."""
import argparse
import functools
import http.server
import json
import mimetypes
import secrets
import threading
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit
from PySide6 import QtCore as C, QtGui as G, QtWidgets as W
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript, QWebEngineUrlRequestInterceptor
from PySide6.QtWebEngineWidgets import QWebEngineView


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        prefix = '/' + self.server.token + '/'
        relative = Path(path[len(prefix):]) if path.startswith(prefix) else None
        if relative is None or relative.is_absolute() or '..' in relative.parts or '\\' in path:
            self.send_error(404)
            return
        target = (self.server.root / relative).resolve()
        if not target.is_relative_to(self.server.root) or not target.is_file():
            self.send_error(404)
            return
        try:
            data = target.read_bytes()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', mimetypes.guess_type(str(target))[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self'; connect-src 'self'; object-src 'none'")
        self.end_headers()
        self.wfile.write(data)


class LocalRequests(QWebEngineUrlRequestInterceptor):
    def __init__(self, prefix, parent):
        super().__init__(parent)
        self.prefix = prefix

    def interceptRequest(self, info):
        url = info.requestUrl().toString()
        if not url.startswith(self.prefix) and not url.startswith(('data:', 'blob:', 'about:')):
            info.block(True)


class Page(QWebEnginePage):
    def __init__(self, profile, prefix, parent):
        super().__init__(profile, parent)
        self.prefix = prefix

    def acceptNavigationRequest(self, url, kind, main):
        return url.toString().startswith(self.prefix)

    def createWindow(self, kind):
        return None


class DragBar(W.QWidget):
    def mousePressEvent(self, event):
        if event.button() == C.Qt.LeftButton:
            self.offset = event.globalPosition().toPoint() - self.window().pos()

    def mouseMoveEvent(self, event):
        if event.buttons() & C.Qt.LeftButton and hasattr(self, 'offset'):
            self.window().move(event.globalPosition().toPoint() - self.offset)


class Window(W.QWidget):
    def __init__(self, game_root, profile_dir):
        super().__init__(None, C.Qt.Window | C.Qt.FramelessWindowHint | C.Qt.WindowStaysOnTopHint)
        self.setWindowTitle('合成大水母')
        self.profile_dir = profile_dir
        profile_dir.mkdir(parents=True, exist_ok=True)
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.server.root = game_root.resolve()
        self.server.token = secrets.token_urlsafe(24)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        prefix = f'http://127.0.0.1:{self.server.server_port}/{self.server.token}/'
        self.setStyleSheet('background:#17232f;color:#aec5d2;')
        layout = W.QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        bar = DragBar()
        bar.setFixedHeight(26)
        row = W.QHBoxLayout(bar)
        row.setContentsMargins(10, 0, 4, 0)
        title = W.QLabel('合成大水母')
        title.setAttribute(C.Qt.WA_TransparentForMouseEvents)
        row.addWidget(title)
        row.addStretch()
        close = W.QPushButton('×')
        close.setFixedSize(28, 24)
        close.setToolTip('关闭小游戏')
        close.setStyleSheet('QPushButton{border:0;background:transparent;font-size:20px;} QPushButton:hover{background:#783d49;}')
        close.clicked.connect(self.close)
        row.addWidget(close)
        layout.addWidget(bar)
        self.view = QWebEngineView()
        self.view.setContextMenuPolicy(C.Qt.NoContextMenu)
        # An ephemeral engine profile avoids leaving a browser cache behind.
        # Keep only the game's original sound preferences in a separate file.
        self.profile = QWebEngineProfile(self)
        self.interceptor = LocalRequests(prefix, self.profile)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        page = Page(self.profile, prefix, self.view)
        self.view.setPage(page)
        page.setBackgroundColor(G.QColor('#17232f'))
        self.profile.downloadRequested.connect(lambda download: download.cancel())
        try:
            saved = json.loads((profile_dir/'audio.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            saved = {}
        script = QWebEngineScript()
        script.setInjectionPoint(QWebEngineScript.DocumentCreation)
        script.setWorldId(QWebEngineScript.MainWorld)
        script.setSourceCode('localStorage.setItem("jellyfish.audioSettings",' + json.dumps(json.dumps(saved)) + ');')
        page.scripts().insert(script)
        layout.addWidget(self.view, 1)
        grip = W.QSizeGrip(self)
        grip.setFixedHeight(10)
        layout.addWidget(grip, 0, C.Qt.AlignRight)
        self.setMinimumSize(480, 304)
        area = W.QApplication.primaryScreen().availableGeometry()
        width = min(1160, int(area.width() * .72), int((area.height() * .78 - 38) * 2559 / 1441))
        self.resize(max(480, width), max(304, int(width * 1441 / 2559) + 38))
        self.move(area.center() - self.rect().center())
        self.view.loadFinished.connect(self.loaded)
        self.view.load(C.QUrl(prefix + 'index.html'))
        self.save_timer = C.QTimer(self)
        self.save_timer.timeout.connect(self.save_audio)
        self.save_timer.start(1000)

    def loaded(self, ok):
        if ok:
            (self.profile_dir/'ready').write_text('ready', encoding='utf-8')
        else:
            W.QMessageBox.warning(self, '合成大水母', '游戏资源加载失败，请重新下载小游戏包。')

    def save_audio(self):
        self.view.page().runJavaScript('localStorage.getItem("jellyfish.audioSettings")', self.store_audio)

    def store_audio(self, value):
        if isinstance(value, str) and len(value) < 4096:
            try:
                settings = json.loads(value)
                if isinstance(settings, dict):
                    (self.profile_dir/'audio.json').write_text(json.dumps(settings), encoding='utf-8')
            except (OSError, ValueError):
                pass

    def closeEvent(self, event):
        self.save_timer.stop()
        self.view.page().setAudioMuted(True)
        self.server.shutdown()
        self.server.server_close()
        # Destroy the page before its profile (Qt WebEngine lifetime rule).
        self.view.page().deleteLater()
        event.accept()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--game-root', required=True, type=Path)
    parser.add_argument('--profile', required=True, type=Path)
    parser.add_argument('--smoke-report', type=Path)
    args = parser.parse_args()
    app = W.QApplication([])
    window = Window(args.game_root, args.profile)
    window.show()
    if sys.platform == 'darwin':
        import objc
        from AppKit import NSWindowCollectionBehaviorCanJoinAllSpaces, NSWindowCollectionBehaviorFullScreenAuxiliary, NSFloatingWindowLevel
        view = objc.objc_object(c_void_p=int(window.winId()))
        panel = view.window()
        if panel is not None:
            panel.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorFullScreenAuxiliary)
            panel.setLevel_(NSFloatingWindowLevel)
    if args.smoke_report:
        def report():
            window.grab().save(str(args.smoke_report.with_suffix('.png')))
            window.view.page().runJavaScript(
                'JSON.stringify({canvas:!!document.getElementById("gameCanvas"),matter:typeof Matter!=="undefined",width:innerWidth,height:innerHeight})',
                lambda result: (args.smoke_report.write_text(result or '{}', encoding='utf-8'), window.close()))
        C.QTimer.singleShot(12000, report)
    app.exec()


if __name__ == '__main__':
    main()
