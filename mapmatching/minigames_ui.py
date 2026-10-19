"""Game download controls; the web runtime lives in an optional subprocess."""
import sys
import json
import time
from PySide6 import QtCore as C, QtWidgets as W, QtGui as G
from .paths import DATA_ROOT
from .theme import ChalkButton
from .minigames import GameStore


def game_profile(controls):
    return DATA_ROOT/'minigame-saves'/getattr(getattr(controls,'store',None),'game_id','jellyfish')


class DownloadTask(C.QThread):
    progress = C.Signal(int, str)
    result = C.Signal(str)

    def __init__(self, store, parent):
        super().__init__(parent)
        self.store = store

    def run(self):
        try:
            self.store.download(self.progress.emit, self.isInterruptionRequested)
            self.result.emit('')
        except InterruptedError:
            self.result.emit('已取消下载')
        except Exception as error:
            self.result.emit('下载未完成：' + str(error))


class GameControls(W.QWidget):
    def __init__(self, companion):
        super().__init__(companion)
        self.companion = companion
        self.store = GameStore(DATA_ROOT)
        from .local_minigames import local_games
        self.stores=[self.store,*local_games(DATA_ROOT)]
        self.task = None
        self.process = C.QProcess(self)
        self.process.setProcessChannelMode(C.QProcess.MergedChannels)
        self.process.finished.connect(self.game_finished)
        self.process.errorOccurred.connect(self.game_error)
        self.process.readyReadStandardOutput.connect(self.read_game_output)
        self.output = bytearray()
        self.ready = False
        self.start_timer = C.QTimer(self)
        self.start_timer.setSingleShot(True)
        self.start_timer.timeout.connect(self.start_timeout)
        self.ready_timer = C.QTimer(self)
        self.ready_timer.setInterval(250)
        self.ready_timer.timeout.connect(self.check_ready)
        self.game_hidden=False
        self.scene_watcher=None
        self.window_timer=C.QTimer(self)
        self.window_timer.setInterval(200)
        self.window_timer.timeout.connect(self.check_window_state)
        layout = W.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.game_rows=[]
        for index,store in enumerate(self.stores):
            title=W.QLabel(getattr(store,'title','合成大水母'))
            layout.addWidget(title)
            row=W.QHBoxLayout()
            download,launch,remove=ChalkButton('下载'),ChalkButton('启动'),ChalkButton('删除')
            for button in (download,launch,remove):row.addWidget(button)
            layout.addLayout(row)
            if index<len(self.stores)-1:layout.addSpacing(10)
            download.clicked.connect(lambda checked=False,i=index:self.row_action(i,'download'))
            launch.clicked.connect(lambda checked=False,i=index:self.row_action(i,'launch'))
            remove.clicked.connect(lambda checked=False,i=index:self.row_action(i,'delete'))
            self.game_rows.append((title,download,launch,remove))
        self.game_title,self.download,self.launch,self.remove=self.game_rows[0]
        self.status=W.QLabel()
        self.status.setObjectName('muted');self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress=W.QProgressBar();self.progress.setRange(0,100);self.progress.hide()
        layout.addWidget(self.progress)
        self.install_engine = ChalkButton('安装系统游戏运行组件')
        self.install_engine.hide()
        self.install_engine.clicked.connect(self.install_system_engine)
        layout.addWidget(self.install_engine)
        W.QApplication.instance().aboutToQuit.connect(self.shutdown)
        self.refresh()

    def row_action(self,index,action):
        if self.task:
            if action=='download' and self.store is self.stores[index]:self.download_game()
            return
        if self.running() and self.store is not self.stores[index]:
            if action=='launch':self.select_game(index)
            return
        self.select_game(index)
        if action=='launch':self.launch_game()
        elif action=='download':self.download_game()
        elif action=='delete':self.delete_game()

    def select_game(self,index):
        if self.task:return
        if self.running():
            if self.store is self.stores[index]:return
            self.pending_game_index=index
            self.status.setText('正在保存并关闭上一款小游戏…')
            self.send_window_command('safe-close')
            C.QTimer.singleShot(15000,self.cancel_game_switch)
            return
        self.store=self.stores[index]
        self.game_title,self.download,self.launch,self.remove=self.game_rows[index]
        self.game_title.setText(getattr(self.store,'title','合成大水母'))
        self.companion.gear.game_icon=G.QPixmap(str(getattr(self.store,'icon',DATA_ROOT/'mapmatching/assets/minigames/fish5.png')))
        self.refresh()

    def cancel_game_switch(self):
        if getattr(self,'pending_game_index',None) is None or not self.running():return
        self.pending_game_index=None
        self.refresh()
        self.status.setText('上一款小游戏尚未安全退出，请处理保存提示后重试')

    def running(self):
        return self.process.state() != C.QProcess.NotRunning

    def check_window_state(self):
        hidden=self.game_hidden if self.running() else False
        if self.running():
            try:
                hidden=bool(json.loads((game_profile(self)/'window-state.json').read_text()).get('hidden'))
            except (OSError,ValueError):
                pass
        if hidden!=self.game_hidden:
            self.game_hidden=hidden
            self.companion.gear.set_game_background(hidden)
            if hidden:self.stop_scene_watch()
            elif self.running():self.start_scene_watch()

    def stop_scene_watch(self):
        watcher=self.scene_watcher;self.scene_watcher=None
        if watcher is not None:watcher.stop();watcher.deleteLater()

    def start_scene_watch(self):
        if sys.platform!='win32' or self.scene_watcher is not None or not self.running() or self.game_hidden:return
        from .game_scene_watch import find_game_window,WindowSceneWatch
        hwnd=find_game_window(getattr(self.companion,'last_external_target',None))
        if not hwnd:
            self.status.setText('小游戏运行中 · 未找到第五人格窗口，自动收起未启动');return
        watcher=WindowSceneWatch(hwnd,self);self.scene_watcher=watcher
        watcher.changed.connect(lambda score:self.scene_changed(watcher,score))
        watcher.failed.connect(lambda message:self.scene_watch_failed(watcher,message))
        try:watcher.start()
        except Exception as error:self.scene_watch_failed(watcher,'画面检测未启动：'+str(error))

    def scene_watch_failed(self,watcher,message):
        if self.scene_watcher is not watcher:return
        self.stop_scene_watch();self.status.setText(message)

    def scene_changed(self,watcher,score):
        if self.scene_watcher is not watcher or not self.running() or self.game_hidden:return
        try:self.send_window_command('auto-hide')
        except OSError as error:
            self.stop_scene_watch();self.status.setText('自动收起失败：'+str(error));return
        self.stop_scene_watch()
        self.companion.notify('游戏画面明显变化，小游戏已收起；5秒内恢复可继续')

    def send_window_command(self,action):
        folder=game_profile(self);target=folder/'window-command.json';temp=folder/'window-command.tmp'
        temp.write_text(json.dumps({'action':action,'id':time.time_ns()}),encoding='utf-8');temp.replace(target)

    def restore_game(self):
        if not self.running():return False
        self.send_window_command('show')
        return True

    def owns_window(self, handle):
        if not self.running() or not handle:
            return False
        pid = int(self.process.processId())
        if sys.platform == 'darwin':
            return int(handle) == pid
        if sys.platform == 'win32':
            import ctypes
            owner = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(ctypes.c_void_p(int(handle)), ctypes.byref(owner))
            return owner.value == pid
        return False

    def refresh(self):
        busy = self.task is not None
        installed = self.store.installed()
        local=getattr(self.store,'local',False)
        switching=getattr(self,'pending_game_index',None) is not None
        for store,(_,download,launch,remove) in zip(self.stores,self.game_rows):
            present=store.installed();source=getattr(store,'local',False);selected=store is self.store
            legacy=present and not store.native()
            download.setEnabled(not source and not self.running() and (not busy or selected))
            download.setText('本地源码' if source else '取消下载' if busy and selected else '升级轻量版' if legacy else '更新游戏' if present else '下载')
            launch.setEnabled(present and not busy and not switching)
            launch.setText('回到游戏' if selected and self.running() else '启动')
            remove.setEnabled(not source and present and not busy and not self.running())
        if not busy:
            self.status.setText(('直接读取本地源码 · 存档独立保存' if installed else '本地源码或公共启动器不存在') if local else f'已下载 · {self.store.size()/1024/1024:.0f} MB' if installed else '按需下载，未启动时不占用游戏运行资源')

    def download_game(self):
        if getattr(self.store,'local',False):return
        if self.task:
            self.task.requestInterruption()
            self.download.setEnabled(False)
            self.status.setText('正在取消下载…')
            return
        self.download_error = ''
        self.task = DownloadTask(self.store, self)
        self.task.progress.connect(self.download_progress)
        self.task.result.connect(self.download_result)
        self.task.finished.connect(self.download_finished)
        self.progress.setValue(0)
        self.progress.show()
        self.refresh()
        self.status.setText('正在查询小游戏包…')
        self.task.start()

    def download_progress(self, percent, text):
        self.progress.setValue(percent)
        self.status.setText(text)

    def download_result(self, error):
        self.download_error = error

    def download_finished(self):
        task, self.task = self.task, None
        task.deleteLater()
        self.progress.hide()
        self.refresh()
        error = getattr(self, 'download_error', '')
        if error:
            self.status.setText('小游戏包尚未上架，请稍后重试。' if 'HTTP Error 404' in error else error)

    def launch_game(self):
        if self.running():
            if self.companion.panel.isVisible():
                self.companion.toggle_panel()
            self.restore_game()
            return
        if not self.store.installed():
            return
        self.companion.close_map(silent=True)
        if self.companion.panel.isVisible():
            self.companion.toggle_panel()
        self.ready = False
        self.output.clear()
        profile = game_profile(self)
        profile.mkdir(parents=True, exist_ok=True)
        for name in ('window-state.json','window-command.json'):
            (profile/name).unlink(missing_ok=True)
        self.ready_file = profile/'ready'
        self.ready_file.unlink(missing_ok=True)
        self.process.setWorkingDirectory(str(self.store.folder))
        arguments = ['--game-root', str(getattr(self.store,'game_root',self.store.folder/'game')), '--profile', str(profile)]
        if self.store.native():
            arguments += ['--title', getattr(self.store,'title','合成大水母')]
        self.process.start(str(self.store.entry()), arguments)
        self.window_timer.start()
        self.start_timer.start(45000)
        self.ready_timer.start()
        self.status.setText('正在启动小游戏…')
        self.launch.setEnabled(False)
        self.remove.setEnabled(False)

    def read_game_output(self):
        self.output.extend(bytes(self.process.readAllStandardOutput()))
        self.output[:] = self.output[-16000:]
    def check_ready(self):
        if self.ready_file.exists() and not self.ready:
            self.ready = True
            if sys.platform=='win32' and getattr(self.store,'window_icon',None):
                from .local_minigames import set_window_icon
                self._native_game_icon=set_window_icon(int(self.process.processId()),self.store.window_icon)
            self.start_timer.stop()
            self.ready_timer.stop()
            self.refresh()
            self.status.setText('运行中 · 拖动顶部窄栏移动，右上角关闭')
            self.start_scene_watch()

    def start_timeout(self):
        if self.running() and not self.ready:
            self.status.setText('小游戏启动较慢，请检查是否已出现窗口')
            self.companion.notify('小游戏启动较慢，请查看游戏窗口')

    def game_error(self, error):
        self.stop_scene_watch()
        self.start_timer.stop()
        self.ready_timer.stop()
        self.refresh()
        self.status.setText('小游戏无法启动，请删除后重新下载')

    def game_finished(self, code, status):
        next_game=getattr(self,'pending_game_index',None)
        self.pending_game_index=None
        self.stop_scene_watch()
        self.window_timer.stop()
        self.game_hidden=False
        self.companion.gear.set_game_background(False)
        self.start_timer.stop()
        self.ready_timer.stop()
        self.refresh()
        if code == 42 and sys.platform == 'win32':
            self.install_engine.show()
            self.status.setText('此电脑缺少 WebView2，安装一次后所有小游戏共用')
        elif code:
            directory = DATA_ROOT/'out/minigames'
            directory.mkdir(parents=True, exist_ok=True)
            (directory/(self.store.game_id+'.log')).write_bytes(bytes(self.output))
            self.status.setText('小游戏已退出，错误日志已保存到 out/minigames')

        if next_game is not None and code==0:
            self.select_game(next_game)
            C.QTimer.singleShot(0,self.launch_game)

    def install_system_engine(self):
        if self.task:
            return
        from .system_webview import EngineInstallTask
        self.download_error = ''
        self.task = EngineInstallTask(self)
        self.task.progress.connect(self.download_progress)
        self.task.result.connect(self.download_result)
        self.task.finished.connect(self.engine_installed)
        self.install_engine.setEnabled(False)
        self.download.setEnabled(False)
        self.launch.setEnabled(False)
        self.status.setText('正在安装微软 WebView2…')
        self.task.start()

    def engine_installed(self):
        task, self.task = self.task, None
        task.deleteLater()
        self.install_engine.setEnabled(True)
        self.refresh()
        error = getattr(self, 'download_error', '')
        if error:
            self.status.setText(error)
        else:
            self.install_engine.hide()
            self.status.setText('系统运行组件已安装，可以启动小游戏')

    def delete_game(self):
        if getattr(self.store,'local',False):return
        if self.task or self.running():
            return
        answer = W.QMessageBox.question(self.companion, '删除小游戏', '删除合成大水母包体？游戏偏好将保留。',
            W.QMessageBox.Yes | W.QMessageBox.No, W.QMessageBox.No)
        if answer != W.QMessageBox.Yes:
            return
        try:
            self.store.delete()
            self.refresh()
        except OSError as error:
            self.status.setText('删除失败：' + str(error))

    def shutdown(self):
        self.stop_scene_watch()
        self.ready_timer.stop()
        if self.task:
            self.task.requestInterruption()
            # QThread cannot be destroyed while a network read is in flight.
            self.task.wait()
        if self.running():
            self.process.terminate()
            if not self.process.waitForFinished(2000):
                self.process.kill()
                self.process.waitForFinished(2000)
