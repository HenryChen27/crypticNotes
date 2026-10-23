from PySide6 import QtCore as C,QtWidgets as W
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
        return str(spec.get('version') or spec.get('build','未知'))
    except (OSError,ValueError):return '未读取'


class ModuleCheck(C.QThread):
    result=C.Signal(bool,str)
    def __init__(self,store,parent):super().__init__(parent);self.store=store
    def run(self):
        try:self.result.emit(self.store.update_available(),'')
        except Exception as error:self.result.emit(False,str(error))

class ProviderControls(W.QWidget):
    changed=C.Signal()
    def __init__(self,companion,provider):
        super().__init__();self.companion=companion;self.store=MatchingModule(provider);self.task=None;self.check_task=None;self.available=None
        box=W.QVBoxLayout(self);box.setContentsMargins(0,0,0,0)
        self.title=W.QLabel('凉哈皮地图库' if provider=='lianghapi' else '展十地图库');box.addWidget(self.title)
        row=W.QHBoxLayout();self.download=ChalkButton('');self.remove=ChalkButton('删除')
        row.addWidget(self.download,1);row.addWidget(self.remove);box.addLayout(row)
        self.version_label=W.QLabel();self.version_label.setWordWrap(True);box.addWidget(self.version_label)
        self.status=W.QLabel();self.status.setWordWrap(True);self.status.hide();box.addWidget(self.status)
        self.download.clicked.connect(self.action);self.remove.clicked.connect(self.uninstall)
        self.refresh();W.QApplication.instance().aboutToQuit.connect(self.shutdown)
    def refresh(self):
        installed=self.store.enabled();busy=self.task is not None or self.check_task is not None or bool(getattr(getattr(self.companion,'matching_controls',None),'task',None))
        spec=self.store.latest
        if spec is None:
            import json
            from .paths import ROOT,FROZEN
            try:spec=json.loads((self.store.root()/'maps/packages'/f'{self.store.provider}.json').read_text(encoding='utf8'))
            except (OSError,ValueError):
                if not FROZEN:
                    try:spec=self.store.choose(json.loads((ROOT/'release/matching-module.json').read_text(encoding='utf8')))
                    except (OSError,ValueError,KeyError):pass
        size=spec.get('size',0) if spec else 0
        self.version_label.setText('版本 '+self.store.version()+(f' · 下载 {size/1024**2:.1f} MB' if size else ''))
        self.download.setText('下载' if not installed else '正在检查…' if self.check_task else '更新' if self.available else '已是最新版' if self.available is False else '检查更新')
        self.download.setEnabled(not busy and (not installed or self.available is not False))
        self.remove.setVisible(installed);self.remove.setEnabled(not busy)
    def action(self):
        if not self.store.enabled() or self.available:self.install();return
        if self.check_task:return
        self.status.hide();self.check_task=ModuleCheck(self.store,self)
        self.check_task.result.connect(self.checked);self.check_task.finished.connect(self.check_finished)
        self.refresh();self.check_task.start()
    def checked(self,available,error):
        self.available=None if error else available
        if error:self.status.setText('检查未完成：'+error);self.status.show()
    def check_finished(self):
        task,self.check_task=self.check_task,None;task.deleteLater();self.refresh();self.companion.resize_settings()
    def install(self):
        if self.task or getattr(getattr(self.companion,'matching_controls',None),'task',None):return
        self.companion.close_map(silent=True);self.companion.stop_worker()
        self.task=DownloadTask(self.store,self)
        self.task.progress.connect(lambda n,text:self.status.setText(text))
        self.error='';self.task.result.connect(self.result);self.task.finished.connect(self.finished)
        self.refresh();self.status.show();self.status.setText('正在下载…');self.changed.emit();self.task.start()
    def result(self,error):self.error=error
    def finished(self):
        task,self.task=self.task,None;task.deleteLater();self.available=None if self.error else False;self.refresh()
        self.status.setVisible(bool(self.error))
        if self.error:self.status.setText('安装未完成：'+self.error)
        self.changed.emit()
    def uninstall(self):
        if getattr(getattr(self.companion,'matching_controls',None),'task',None):return
        if W.QMessageBox.question(self.companion,'删除地图库','只删除这个作者的地图库？其他作者、个人地图与设置保留。',W.QMessageBox.Yes|W.QMessageBox.No,W.QMessageBox.No)!=W.QMessageBox.Yes:return
        self.companion.close_map(silent=True);self.companion.stop_worker()
        try:self.store.delete()
        except Exception as error:self.status.setText('删除未完成：'+str(error));self.status.show();return
        self.available=None;self.status.hide();self.refresh();self.changed.emit()
    def shutdown(self):
        if self.check_task:self.check_task.wait()
        if self.task:self.task.requestInterruption();self.task.wait()


class MatchingControls(W.QWidget):
    changed=C.Signal()
    def __init__(self,companion):
        super().__init__();self.store=MatchingModule()
        layout=W.QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.providers=[ProviderControls(companion,p) for p in ('lianghapi','zhanshi')]
        for row in self.providers:layout.addWidget(row);row.changed.connect(self.refresh);row.changed.connect(self.changed.emit)
    @property
    def task(self):return next((row.task for row in self.providers if row.task),None)
    def refresh(self):
        for row in self.providers:row.refresh()
    def shutdown(self):
        for row in self.providers:row.shutdown()
