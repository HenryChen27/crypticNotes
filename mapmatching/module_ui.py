from PySide6 import QtCore as C,QtWidgets as W
from copy import copy
from time import monotonic
from .package_ui import PackageCaption,package_action
from .theme import ChalkButton
from .matching_module import MatchingModule
from .minigames_ui import DownloadTask

def application_version():
    import json,sys
    from .paths import ROOT,FROZEN
    if not FROZEN:return '本地源码'
    if sys.platform=='darwin':
        import plistlib
        from pathlib import Path
        try:
            info=plistlib.loads((Path(sys.executable).resolve().parents[1]/'Info.plist').read_bytes())
            return str(info.get('CFBundleShortVersionString','未知'))+' ('+str(info.get('CFBundleVersion',''))+')'
        except (OSError,ValueError):return '未读取'
    try:
        spec=json.loads((ROOT/'windows-build.json').read_text(encoding='utf-8-sig'))
    except (OSError,ValueError):return '未读取'
    return windows_version_text(spec)

def windows_version_text(spec):
    """Windows builds only carry ``build``, a ``time.time_ns()`` stamp from
    finalize_release. Shown raw it is a 19-digit number that cannot wrap and
    widened the whole settings page past its viewport, clipping every row on
    the right; show the build time instead."""
    import datetime
    if spec.get('version'):return str(spec['version'])
    try:build=int(spec['build'])
    except (KeyError,TypeError,ValueError):return '未知'
    try:return datetime.datetime.fromtimestamp(build/1e9).strftime('%Y.%m.%d %H:%M')
    except (OverflowError,OSError,ValueError):return str(build)


class ModuleCheck(C.QThread):
    result=C.Signal(bool,object,str)
    def __init__(self,store,parent):super().__init__(parent);self.store=copy(store)
    def run(self):
        try:self.result.emit(self.store.update_available(),self.store.latest,'')
        except Exception as error:self.result.emit(False,None,str(error))

class ProviderControls(W.QWidget):
    changed=C.Signal()
    availabilityChanged=C.Signal()
    def __init__(self,companion,provider):
        from .pvp_package import PvpPackage
        from .desktop_modules import GamesCore
        super().__init__();self.companion=companion;self.key=provider;self.core=provider in ('notes','pvp','games')
        self.store=PvpPackage() if provider=='pvp' else GamesCore() if provider=='games' else MatchingModule(None if provider=='notes' else provider);self.task=None;self.check_task=None;self.available=None
        box=W.QVBoxLayout(self);box.setContentsMargins(0,0,0,0)
        self.check_failed=False;self.last_check=None;self.identity=None
        self.name={'lianghapi':'凉哈皮地图库','zhanshi':'展十地图库','notes':'加页手记主程序','games':'小游戏主程序','pvp':'禁选辅助主程序'}[provider]
        self.caption=PackageCaption(self.name);box.addWidget(self.caption)
        row=W.QHBoxLayout();self.download=ChalkButton('');self.remove=ChalkButton('删除')
        row.addWidget(self.download,1);row.addWidget(self.remove);box.addLayout(row)
        self.status=W.QLabel();self.status.setWordWrap(True);self.status.hide();box.addWidget(self.status)
        self.download.clicked.connect(self.action);self.remove.clicked.connect(self.uninstall)
        self.refresh();W.QApplication.instance().aboutToQuit.connect(self.shutdown)
    def refresh(self):
        installed=self.store.enabled();receipt=self.store.receipt() if installed else {};spec=self.store.latest or {}
        identity=(receipt.get('sha256') or receipt.get('downloadSha256') or self.store.version()) if installed else None
        if self.identity!=identity:self.identity=identity;self.available=None;self.last_check=None;self.check_failed=False
        remote_version=spec.get('version') or spec.get('sha256','')[:12]
        size=(receipt.get('size') or receipt.get('downloadSize') or (spec.get('size') if self.available is False else 0)) if installed else spec.get('size')
        self.caption.describe(installed,self.store.version() if installed else remote_version,size or 0)
        text,enabled=package_action(installed,self.available,self.check_task is not None,self.check_failed)
        busy=self.task is not None or self.companion.packages_busy()
        self.download.setText('处理中…' if self.task else text);self.download.setEnabled(enabled and not busy)
        self.download.set_update_available(installed and self.available is True)
        self.remove.setVisible(installed);self.remove.setEnabled(not busy and self.check_task is None)
    def action(self):
        if self.companion.packages_busy():return
        if not self.store.enabled() or self.available:self.install();return
        if self.available is None:self.check()
    def check(self,silent=False):
        if self.check_task or self.task or (silent and self.last_check is not None and monotonic()-self.last_check<60):return
        self.refresh();self.silent=silent;self.checked_identity=self.identity;self.last_check=monotonic()
        self.status.hide();self.check_task=ModuleCheck(self.store,self)
        self.check_task.result.connect(self.checked);self.check_task.finished.connect(self.check_finished)
        self.refresh();self.check_task.start()
    def checked(self,available,spec,error):
        self.refresh()
        if self.task or self.identity!=self.checked_identity:return
        self.check_failed=bool(error);self.available=available if not error and self.identity is not None else None
        if spec:self.store.latest=spec
        if error and not self.silent:self.status.setText('检查未完成：'+error);self.status.show()
        self.availabilityChanged.emit()
    def check_finished(self):
        task,self.check_task=self.check_task,None;task.deleteLater();self.refresh();self.companion.resize_settings()
    def install(self):
        if self.companion.packages_busy() or (self.check_task and self.store.enabled()):return
        if self.key=='games' and self.companion.minigames.running():self.companion.notify('请先退出小游戏');return
        if self.key=='pvp' and self.companion.pvp is not None:self.companion.pvp.leave()
        if self.key in ('notes','lianghapi','zhanshi'):self.companion.close_map(silent=True);self.companion.stop_worker()
        self.fresh=not self.store.enabled()
        self.task=DownloadTask(self.store,self)
        self.task.progress.connect(lambda n,text:self.status.setText(text))
        self.error='';self.task.result.connect(self.result);self.task.finished.connect(self.finished)
        self.refresh();self.status.show();self.status.setText('正在下载…');self.changed.emit();self.task.start()
    def result(self,error):self.error=error
    def finished(self):
        task,self.task=self.task,None;task.deleteLater();self.refresh()
        self.available=None if self.error else False;self.check_failed=bool(self.error);self.last_check=monotonic();self.refresh()
        self.status.setVisible(bool(self.error))
        if self.error:self.status.setText('安装未完成：'+self.error)
        if self.key=='notes' and self.fresh and not self.error:self.companion.select_original()
        if self.key=='games' and not self.error:self.companion.minigames.sync_catalog()
        self.changed.emit()
    def uninstall(self):
        if self.companion.packages_busy() or self.check_task:return
        if self.key=='games' and self.companion.minigames.running():self.companion.notify('请先退出小游戏');return
        message='删除'+self.name+'？'+('本栏已下载的可选包将一起移除。' if self.core else '')+'个人地图、存档和设置保留。'
        if W.QMessageBox.question(self.companion,'删除可选包',message,W.QMessageBox.Yes|W.QMessageBox.No,W.QMessageBox.No)!=W.QMessageBox.Yes:return
        if self.key=='pvp' and self.companion.pvp is not None:self.companion.pvp.leave()
        if self.key in ('notes','lianghapi','zhanshi'):self.companion.close_map(silent=True);self.companion.stop_worker()
        try:self.store.delete()
        except Exception as error:self.status.setText('删除未完成：'+str(error));self.status.show();return
        if self.key in ('notes',self.companion.provider()):self.companion.select_original()
        self.available=None;self.status.hide();self.refresh();self.changed.emit()
    def shutdown(self):
        if self.check_task:self.check_task.wait()
        if self.task:self.task.requestInterruption();self.task.wait()


class MatchingControls(W.QWidget):
    changed=C.Signal()
    def __init__(self,companion,module='notes'):
        from .theme import FoldSection
        super().__init__();self.outer=W.QVBoxLayout(self);self.outer.setContentsMargins(0,0,0,0)
        self.fold=FoldSection('版本');self.outer.addWidget(self.fold);self.fold.changed.connect(companion.resize_settings)
        self.providers=[ProviderControls(companion,key) for key in ((module,'lianghapi','zhanshi') if module=='notes' else (module,))]
        self.core=self.providers[0];self.store=self.core.store
        self.fold.header.toggled.connect(lambda opened:self.probe() if opened else None)
        for row in self.providers:self.fold.body.addWidget(row);row.changed.connect(self.changed.emit);row.availabilityChanged.connect(companion.package_badges)
        self.refresh()
    @property
    def task(self):return next((row.task for row in self.providers if row.task),None)
    def probe(self):
        for row in self.providers:
            if row.core or self.store.enabled():row.check(silent=True)
    def refresh(self):
        installed=self.store.enabled();layout=self.fold.body if installed else self.outer
        if layout.indexOf(self.core)<0:layout.insertWidget(0,self.core);self.core.show()
        self.fold.setVisible(installed)
        for row in self.providers:row.refresh()
    def shutdown(self):
        for row in self.providers:row.shutdown()
