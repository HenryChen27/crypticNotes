"""Game download controls; the web runtime lives in an optional subprocess."""
import sys
import json
import time
from PySide6 import QtCore as C, QtWidgets as W, QtGui as G
from .paths import DATA_ROOT
from .game_icons import game_pixmap,cache_catalog_icons
from .theme import ChalkButton, FoldSection
from .minigames import GameStore, CollectionGameStore, read_collection, read_catalog, package_info, platform_key,game_title,LauncherStore


def game_profile(controls):
    return DATA_ROOT/'minigame-saves'/getattr(getattr(controls,'store',None),'game_id','jellyfish')


def compact_game_caption(version, size):
    version=('v'+str(version).lstrip('vV')) if version else '版本待同步'
    amount=(f'{size/1048576:.1f}'.rstrip('0').rstrip('.')+'MB') if size else '大小待同步'
    return version+' · '+amount


class GameTaskStatus(W.QLabel):
    def setText(self,text):
        super().setText(text)
        self.setVisible(bool(text))


class GameListCard(W.QWidget):
    """Reserve action width; long titles must never push the launch button out."""
    def __init__(self,title):
        super().__init__()
        self.row=W.QHBoxLayout(self);self.row.setContentsMargins(0,7,0,7);self.row.setSpacing(10)
        self.icon=W.QLabel();self.icon.setFixedSize(38,38);self.icon.setAlignment(C.Qt.AlignCenter);self.row.addWidget(self.icon)
        text=W.QWidget();column=W.QVBoxLayout(text);column.setContentsMargins(0,0,0,0);column.setSpacing(3)
        text.setSizePolicy(W.QSizePolicy.Ignored,W.QSizePolicy.Preferred)
        self.title=W.QLabel(title);self.title.setSizePolicy(W.QSizePolicy.Ignored,W.QSizePolicy.Preferred)
        self.subtitle=W.QLabel();self.subtitle.setSizePolicy(W.QSizePolicy.Ignored,W.QSizePolicy.Preferred)
        self.subtitle.setStyleSheet('color:rgba(187,204,216,145);font-size:12px;background:transparent;')
        column.addWidget(self.title);column.addWidget(self.subtitle);self.row.addWidget(text,1)
        self.launch=ChalkButton('启动');self.download=ChalkButton('下载')
        for button in (self.launch,self.download):
            button.setFixedWidth(84);button.setStyleSheet('font-size:15px;');self.row.addWidget(button)


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


class CatalogTask(C.QThread):
    result=C.Signal(object,str)
    def run(self):
        try:
            catalog=read_collection();cache_catalog_icons(catalog);catalog['_launcher']=package_info(read_catalog(),platform_key())
            self.result.emit(catalog,'')
        except Exception as error:self.result.emit(None,str(error))


class GameControls(W.QWidget):
    def __init__(self, companion):
        super().__init__(companion)
        self.companion = companion
        self.store = GameStore(DATA_ROOT)
        from .local_minigames import local_games
        self.local_stores=local_games(DATA_ROOT)
        self.catalog_cache=DATA_ROOT/'out/minigames/catalog.json'
        try:cached=json.loads(self.catalog_cache.read_text(encoding='utf-8'));specs=cached['games']
        except (OSError,ValueError,KeyError):cached={};specs={}
        remote=[CollectionGameStore(DATA_ROOT,spec) for spec in specs.values()]
        for store in remote:store.launcher_info=cached.get('_launcher')
        self.stores=remote or [self.store]
        ids={store.game_id for store in self.stores}
        self.stores += [store for store in self.local_stores if store.game_id not in ids]
        ids={store.game_id for store in self.stores}
        for metadata in (DATA_ROOT/'minigames').glob('*/package.json'):
            try:
                spec=json.loads(metadata.read_text(encoding='utf-8'));key=spec['id']
                if key in ids or key in ('runtime','game-launcher'):continue
                store=GameStore(DATA_ROOT,key);store.title=game_title(key,spec.get('name'));store.withdrawn=True
                if store.installed():self.stores.append(store);ids.add(key)
            except (OSError,ValueError,KeyError):continue
        self.store=self.stores[0]
        self.preferences_path=DATA_ROOT/'out/minigames/preferences.json'
        try:self.preferences=json.loads(self.preferences_path.read_text(encoding='utf-8'))
        except (OSError,ValueError):self.preferences={}
        self.catalog_task=None
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
        self.sync_button=ChalkButton('同步游戏列表 / 检查更新')
        self.sync_button.clicked.connect(self.sync_catalog)
        self.version_section=FoldSection('版本')
        self.shortcut_section=FoldSection('快捷键')
        for fold in (self.version_section,self.shortcut_section):fold.changed.connect(lambda:C.QTimer.singleShot(0,self.companion.resize_settings))
        self.rows_widget=W.QWidget();self.rows_layout=W.QVBoxLayout(self.rows_widget)
        self.rows_layout.setContentsMargins(0,0,0,0);layout.addWidget(self.rows_widget)
        self.rebuild_rows()
        self.status=GameTaskStatus();self.status.setText('')
        self.status.setObjectName('muted');self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress=W.QProgressBar();self.progress.setRange(0,100);self.progress.hide()
        layout.addWidget(self.progress)
        self.install_engine = ChalkButton('安装系统游戏运行组件')
        self.install_engine.hide()
        self.install_engine.clicked.connect(self.install_system_engine)
        layout.addWidget(self.install_engine)
        W.QApplication.instance().aboutToQuit.connect(self.shutdown)
        from .theme import FrostCheckBox
        self.sound=FrostCheckBox('小游戏声音')
        self.sound.setChecked(self.preferences.get('sound',True));self.sound.toggled.connect(self.save_preferences)
        layout.addWidget(self.sound)
        self.detect=FrostCheckBox('第五人格画面明显变化时自动收起')
        self.detect.setChecked(self.preferences.get('detect',True));self.detect.toggled.connect(self.save_preferences)
        layout.addWidget(self.detect)
        self.shortcut_buttons={};self.shortcut_rows={}
        from .shortcut_row import ShortcutRow
        for action,label in [('restore','显隐'),('mute','静音'),('close','关闭')]:
            key=self.preferences.get(action+'_key','未设置')
            row=ShortcutRow(label+'快捷键',key,lambda a=action:self.edit_shortcut(a))
            row.toggle.setChecked(self.preferences.get(action+'_enabled',key!='未设置'))
            row.toggle.toggled.connect(lambda enabled,a=action:self.set_shortcut_enabled(a,enabled))
            self.shortcut_rows[action]=row;self.shortcut_buttons[action]=(row.edit,label)
            self.shortcut_section.body.addWidget(row)
        layout.addWidget(self.shortcut_section);layout.addWidget(self.version_section)
        self.update_shortcut_labels()
        self.refresh()
        C.QTimer.singleShot(1200,self.sync_catalog)

    def rebuild_rows(self):
        # Keep the sync control alive while rebuilding per-game version rows.
        if hasattr(self,'sync_button'):self.version_section.body.removeWidget(self.sync_button);self.sync_button.setParent(self)
        for target in (self.rows_layout,self.version_section.body):
            while target.count():
                item=target.takeAt(0)
                if item.widget():item.widget().deleteLater()
        self.launcher_version=W.QLabel();self.launcher_version.setWordWrap(True);self.version_section.body.addWidget(self.launcher_version)
        self.game_rows=[];self.row_layouts=[];self.version_cards=[];self.size_labels=[];self.game_icon_labels=[];self.game_cards=[]
        for index,store in enumerate(self.stores):
            card=GameListCard(getattr(store,'title','小游戏'));self.game_cards.append(card)
            self.game_icon_labels.append(card.icon);title=card.title;launch=card.launch
            download,remove=ChalkButton('下载'),ChalkButton('删除')
            self.rows_layout.addWidget(card)
            version=W.QWidget();vbox=W.QVBoxLayout(version);vbox.setContentsMargins(0,0,0,6)
            size_label=W.QLabel();size_label.setWordWrap(True);size_label.setStyleSheet('color:rgba(187,204,216,145);font-size:12px;background:transparent;');vbox.addWidget(size_label);self.size_labels.append(size_label)
            actions=W.QHBoxLayout();actions.addWidget(download,1);actions.addWidget(remove);vbox.addLayout(actions)
            self.version_section.body.addWidget(version)
            for button,action in ((download,'download'),(card.download,'download'),(launch,'launch'),(remove,'delete')):
                button.clicked.connect(lambda checked=False,i=index,a=action:self.row_action(i,a))
            self.game_rows.append((title,download,launch,remove));self.row_layouts.append(card.row);self.version_cards.append((version,actions))
        self.version_section.body.addWidget(self.sync_button)
        index=self.stores.index(self.store) if self.store in self.stores else 0
        self.game_title,self.download,self.launch,self.remove=self.game_rows[index]

    def sync_catalog(self):
        if getattr(self,"closing",False) or self.catalog_task or self.task:return
        self.sync_button.setEnabled(False);self.sync_button.setText('正在同步…')
        self.catalog_task=CatalogTask(self)
        self.catalog_task.result.connect(self.catalog_received)
        self.catalog_task.finished.connect(self.catalog_finished);self.catalog_task.start()

    def catalog_received(self,catalog,error):
        if not error:self.sync_catalog()
        if error:
            self.status.setText('同步失败，保留已有游戏：'+error);return
        self.catalog_cache.parent.mkdir(parents=True,exist_ok=True)
        temp=self.catalog_cache.with_suffix('.tmp');temp.write_text(json.dumps(catalog,ensure_ascii=False),encoding='utf-8');temp.replace(self.catalog_cache)
        if self.running() or self.task:
            self.status.setText('列表已同步，退出游戏后刷新显示');return
        old_id=self.store.game_id
        stores=[CollectionGameStore(DATA_ROOT,spec) for spec in catalog['games'].values()]
        for store in stores:store.launcher_info=catalog.get('_launcher')
        ids={store.game_id for store in stores}
        for store in self.stores:
            if store.game_id not in ids and store.installed():
                store.withdrawn=True;stores.append(store)
        ids={store.game_id for store in stores}
        stores += [store for store in self.local_stores if store.game_id not in ids]
        if not stores:return
        self.stores=stores;self.store=next((x for x in stores if x.game_id==old_id),stores[0])
        self.rebuild_rows();self.refresh();C.QTimer.singleShot(0,self.companion.resize_settings)

    def catalog_finished(self):
        task,self.catalog_task=self.catalog_task,None
        task.deleteLater();self.sync_button.setEnabled(True);self.sync_button.setText('同步游戏列表 / 检查更新')

    def save_preferences(self):
        self.preferences.update(sound=self.sound.isChecked(),detect=self.detect.isChecked())
        self.preferences_path.parent.mkdir(parents=True,exist_ok=True)
        self.preferences_path.write_text(json.dumps(self.preferences),encoding='utf-8')
        if self.running():self.send_window_command('sound-on' if self.sound.isChecked() else 'sound-off')
        if not self.detect.isChecked():self.stop_scene_watch()
        elif self.running():self.start_scene_watch()

    def set_shortcut_enabled(self,action,enabled):
        self.preferences[action+'_enabled']=enabled;self.save_preferences()

    def update_shortcut_labels(self):
        from .ui import hotkey_text
        for action,(_,label) in self.shortcut_buttons.items():
            self.shortcut_rows[action].set_key(label+'快捷键',hotkey_text(self.preferences.get(action+'_key','未设置')))

    def edit_shortcut(self,action):
        from .ui import HotkeyDialog,HOTKEYS
        current=self.preferences.get(action+'_key','F8')
        dialog=HotkeyDialog(current,self.companion)
        if dialog.exec()!=W.QDialog.Accepted:return
        key=dialog.selected
        reserved={HOTKEYS[k] for k in (self.companion.hotkey,self.companion.close_hotkey,self.companion.hide_hotkey)}
        if HOTKEYS[key] in reserved or any(HOTKEYS.get(self.preferences.get(a+'_key'))==HOTKEYS[key] for a in self.shortcut_buttons if a!=action):
            self.status.setText('快捷键已被使用，请选择其他按键');return
        self.preferences[action+'_key']=key;self.preferences[action+'_enabled']=True
        self.shortcut_rows[action].toggle.setChecked(True);self.update_shortcut_labels();self.save_preferences()

    def shortcut_keys(self):
        from .ui import HOTKEYS
        return {HOTKEYS[k] for a in self.shortcut_buttons if self.preferences.get(a+'_enabled',True) and (k:=self.preferences.get(a+'_key')) in HOTKEYS}

    def handle_shortcuts(self,edges):
        if not self.running():return
        from .ui import HOTKEYS
        for action in self.shortcut_buttons:
            if not self.preferences.get(action+'_enabled',True):continue
            if HOTKEYS.get(self.preferences.get(action+'_key')) not in edges:continue
            if action=='restore':self.send_window_command('show' if self.game_hidden else 'hide')
            elif action=='mute':self.sound.setChecked(not self.sound.isChecked())
            elif action=='close':self.send_window_command('safe-close')

    def row_action(self,index,action):
        if self.task:
            if action=='download' and self.store is self.stores[index]:self.download_game()
            return
        if self.running() and self.store is not self.stores[index]:
            if action=='launch':self.select_game(index)
            return
        self.select_game(index)
        if action=='launch':self.launch_game()
        elif action=='download':
            if self.store.installed() and not hasattr(self.store,'spec') and not getattr(self.store,'local',False):self.sync_catalog()
            else:self.download_game()
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
        self.companion.gear.game_icon=game_pixmap(self.store)
        self.companion.gear.update()
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
        if not self.preferences.get('detect',True):return
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
        launcher=LauncherStore(DATA_ROOT)
        self.launcher_version.setText('公共小游戏启动器版本 '+str(launcher.version() or '未安装'))
        for index,(store,(_,download,launch,remove)) in enumerate(zip(self.stores,self.game_rows)):
            self.game_icon_labels[index].setPixmap(game_pixmap(store).scaled(36,36,C.Qt.KeepAspectRatio,C.Qt.SmoothTransformation))
            present=store.installed();source=getattr(store,'local',False);selected=store is self.store
            installed_size=store.size() if present else 0
            download_size=getattr(store,'spec',{}).get('size',0)
            current=getattr(store,'version',lambda:None)() if present else None
            latest=getattr(store,'spec',{}).get('version')
            caption=compact_game_caption(current or latest,download_size or installed_size)
            title=self.game_rows[index][0];title.setText(getattr(store,'title','小游戏'))
            card=self.game_cards[index];card.subtitle.setText(caption)
            details='当前版本：'+str(current or '未安装')+'\n最新版本：'+str(latest or '待同步')
            details+='\n已安装：'+f'{installed_size/1048576:.1f}MB'+'\n安装包：'+(f'{download_size/1048576:.1f}MB' if download_size else '待同步')
            card.setToolTip(details)
            self.size_labels[index].setText(getattr(store,'title','小游戏')+' · '+caption)
            legacy=present and not store.native()
            available=getattr(store,'update_available',lambda:True)()
            download.setEnabled(not source and not getattr(store,'withdrawn',False) and not self.running() and (not busy or selected) and (not present or available or (busy and selected)))
            download.setText('本地源码' if source else '已下架' if getattr(store,'withdrawn',False) else '取消下载' if busy and selected else '升级轻量版' if legacy else '更新' if present and available else '已是最新版' if present else '下载')
            launch.setEnabled(present and not busy and not switching)
            launch.setText('回到游戏' if selected and self.running() else '启动')
            remove.setEnabled(not source and present and not busy and not self.running())
            # Keep launch and management controls in their own permanent layouts.
            # Reparenting a download button during refresh can hide it in Qt.
            payload=(getattr(store,'game_root',store.folder/'game')/'index.html').is_file()
            show_launch=present or payload
            launch.setVisible(show_launch)
            launch.setToolTip('' if present else '公共启动器尚未就绪，请在版本管理中重新下载或更新')
            card.download.setVisible(not show_launch)
            card.download.setEnabled(download.isEnabled());card.download.setText(download.text())
            remove.setVisible(show_launch);self.version_cards[index][0].setVisible(show_launch)
        any_installed=any(store.installed() or (getattr(store,'game_root',store.folder/'game')/'index.html').is_file() for store in self.stores)
        for widget in (self.sound,self.detect,self.shortcut_section,self.version_section):widget.setVisible(any_installed)
        C.QTimer.singleShot(0,self.companion.resize_settings)
        if not busy:
            self.status.setText('')

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
        if not self.preferences.get('sound',True):arguments += ['--muted']
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
            if sys.platform=='win32':
                from .local_minigames import set_window_icon
                icon_path=DATA_ROOT/'out/minigames/icons'/f'{self.store.game_id}.ico'
                try:
                    icon_path.parent.mkdir(parents=True,exist_ok=True)
                    if game_pixmap(self.store,64).save(str(icon_path),'ICO'):
                        self._native_game_icon=set_window_icon(int(self.process.processId()),icon_path)
                except OSError:pass
            self.start_timer.stop()
            self.ready_timer.stop()
            self.refresh()
            self.status.setText('运行中 · 拖动顶部窄栏移动，右上角关闭')
            self.send_window_command('sound-on' if self.sound.isChecked() else 'sound-off')
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
        if sys.platform=='win32' and getattr(self,'_native_game_icon',None):
            import ctypes
            ctypes.windll.user32.DestroyIcon(ctypes.c_void_p(self._native_game_icon))
            self._native_game_icon=None
        next_game=getattr(self,'pending_game_index',None)
        self.pending_game_index=None
        self.stop_scene_watch()
        self.window_timer.stop()
        self.game_hidden=False
        self.companion.module_tabs.buttons[0].show()
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

        if next_game is None:C.QTimer.singleShot(0,self.sync_catalog)
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
        answer = W.QMessageBox.question(self.companion, '删除小游戏', '删除'+getattr(self.store,'title','小游戏')+'包体？存档和偏好将保留。',
            W.QMessageBox.Yes | W.QMessageBox.No, W.QMessageBox.No)
        if answer != W.QMessageBox.Yes:
            return
        try:
            self.store.delete()
            self.refresh()
        except OSError as error:
            self.status.setText('删除失败：' + str(error))

    def shutdown(self):
        if getattr(self,"closing",False):return
        self.closing=True;self.pending_game_index=None
        self.stop_scene_watch()
        self.ready_timer.stop()
        if self.catalog_task:self.catalog_task.wait()
        if self.task:
            self.task.requestInterruption()
            # QThread cannot be destroyed while a network read is in flight.
            self.task.wait()
        if self.running():
            self.process.terminate()
            if not self.process.waitForFinished(2000):
                self.process.kill()
                self.process.waitForFinished(2000)
