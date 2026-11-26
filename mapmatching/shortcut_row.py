from PySide6 import QtCore as C,QtGui as G,QtWidgets as W
from .theme import ChalkToggle
from .line_icons import KeyCap

# Reuse the original desktop shortcut editor icon.
from .theme import EditButton
WrenchButton=EditButton

class ShortcutRow(W.QWidget):
    def __init__(self,label,key,edit,toggle=None):
        super().__init__();box=W.QHBoxLayout(self);box.setContentsMargins(0,0,0,0);box.setSpacing(5)
        self.label=W.QLabel();self.label.setMinimumWidth(0)
        self.label.setSizePolicy(W.QSizePolicy.Expanding,W.QSizePolicy.Preferred)
        # The key itself is drawn as a cap, as the PC client labels its buttons.
        self.cap=KeyCap(key)
        self.edit=WrenchButton();self.edit.clicked.connect(edit)
        self.toggle=toggle if toggle is not None else ChalkToggle();self.toggle.setFixedSize(54,28)
        box.addWidget(self.label,1);box.addWidget(self.cap);box.addWidget(self.edit);box.addWidget(self.toggle)
        self.set_key(label,key)
    def set_key(self,label,key):self.label.setText(label);self.cap.setKey(key)


from .theme import FoldSection


class BanShortcuts(FoldSection):
    labels={'scan':'开始 / 停止识别','manual':'手动选择'}

    def __init__(self,companion):
        from .ui import HOTKEYS,keycap_text
        super().__init__('快捷键');self.companion=companion;self.rows={};self.bindings={}
        prefs=companion.settings
        for action,label in self.labels.items():
            saved=prefs.get('ban_'+action+'_key')
            defaults=(companion.hotkey,'G') if action=='scan' else ('F8','F9')
            key=next(name for name in (saved,*defaults) if name in HOTKEYS and all(HOTKEYS[name]!=HOTKEYS[other] for other in self.bindings.values()))
            self.bindings[action]=key
            row=ShortcutRow(label,keycap_text(key),lambda checked=False,which=action:self.edit(which));self.rows[action]=row
            row.toggle.setChecked(prefs.get('ban_'+action+'_enabled',True));self.body.addWidget(row)
            row.toggle.toggled.connect(lambda enabled,which=action:self.persist(which,enabled))

    def edit(self,action):
        from .ui import HOTKEYS,HotkeyDialog,keycap_text
        dialog=HotkeyDialog(self.bindings[action],self.companion,default='G' if action=='scan' else 'F8')
        if dialog.exec()!=W.QDialog.Accepted:return
        if any(HOTKEYS[key]==HOTKEYS[dialog.selected] for other,key in self.bindings.items() if other!=action):
            self.companion.notify('禁选辅助中已有这个快捷键');return
        self.bindings[action]=dialog.selected;row=self.rows[action];row.set_key(self.labels[action],keycap_text(dialog.selected))
        if row.toggle.isChecked():self.persist(action,True)
        else:row.toggle.setChecked(True)

    def persist(self,action,enabled):
        self.companion.settings.update({'ban_'+action+'_key':self.bindings[action],'ban_'+action+'_enabled':enabled})
        self.companion.save()

    def binding(self,action):
        return self.bindings[action] if self.rows[action].toggle.isChecked() else None

    def active(self):
        from .ui import HOTKEYS
        return {HOTKEYS[key]:action for action in self.labels if (key:=self.binding(action))}
