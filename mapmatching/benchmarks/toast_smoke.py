"""Exercise actual Qt status surfaces and result delivery without game input."""
from types import SimpleNamespace
from pathlib import Path
import numpy as np
from mapmatching.ui import Companion,W,C,native,font_stack,TOAST_MS,TOAST_MAX_RATIO


class Preview(Companion):
    def start_worker(self): pass
    def save(self): pass


def main():
    native.dpi_aware()
    app=W.QApplication([]); font_stack()
    ui=Preview(); ui.timer.stop(); ui.show(); app.processEvents()
    ui.keys.edges=lambda:set()
    ui.follow=lambda:None
    ui.foreground_lost=lambda:False
    ui.mouse_busy=lambda:False
    ui.target=native.user32.GetForegroundWindow()
    ui.rect_at_capture=(0,0,200,200)
    ui.capture_rect=lambda:ui.rect_at_capture
    checks=0
    for expanded in (False,True):
        if ui.panel.isVisible()!=expanded:
            ui.toggle_panel()
        for success in (True,False):
            ui.overlay.hide()
            token=ui.state.open()
            ui.target=native.user32.GetForegroundWindow()
            candidate=SimpleNamespace(map_id='hard/test',floor=1)
            layer=np.zeros((200,200,4),np.uint8) if success else None
            message='试用叠图' if success else '没有找到可靠匹配'
            payload=(token,layer,message,candidate,123,{'diagnostics':{'anchors':20}})
            ui.connection=SimpleNamespace(poll=lambda:True,recv=lambda:('result',payload))
            ui.tick(); app.processEvents()
            assert ui.toast.isVisible()
            assert ('test' in ui.toast.text()) if success else ('未匹配' in ui.toast.text() or message in ui.toast.text())
            assert ui.toast_timer.interval()==TOAST_MS
            area=(W.QApplication.screenAt(ui.toast.pos()) or W.QApplication.primaryScreen()).availableGeometry()
            assert area.contains(ui.toast.geometry())
            assert ui.toast.width()<=int(area.width()*TOAST_MAX_RATIO)
            ui.connection=None
            checks+=1
    # 框随文字走：同一句话，短的就该得到更窄的框，而不是一律撑到限额。
    widths=[]
    for text in ('已隐藏','鼠标监听未启用','匹配中断，请重试'):
        ui.notify(text)
        app.processEvents()
        widths.append(ui.toast.width())
    assert widths==sorted(widths) and widths[0]<widths[-1],f'提示框没有随文字自适应：{widths}'
    checks+=1
    # 超过限额的长句必须换行收进限额，而不是横向溢出屏幕。
    ui.notify('很长的一句提示'*20)
    app.processEvents()
    area=(W.QApplication.screenAt(ui.toast.pos()) or W.QApplication.primaryScreen()).availableGeometry()
    assert ui.toast.width()<=int(area.width()*TOAST_MAX_RATIO) and area.contains(ui.toast.geometry())
    checks+=1
    # 失焦把展开的设置面板收回成齿轮。真实点游戏的鼠标事件进了别的进程，
    # 我们收不到，只能靠失活 —— 这里直接把那个事件喂进去，验的是判断本身。
    def deactivate():
        W.QApplication.sendEvent(ui,C.QEvent(C.QEvent.WindowDeactivate))
        app.processEvents()
    if not ui.panel.isVisible():
        ui.toggle_panel()
    deactivate()
    assert not ui.panel.isVisible(),'点到游戏时展开的设置面板应当收回成齿轮'
    checks+=1
    # 但「失活」也可能是因为我们自己开了个模态框，那不是回到游戏，不能跟着收。
    ui.toggle_panel()
    box=W.QDialog(ui); box.setModal(True); box.show(); app.processEvents()
    assert W.QApplication.activeModalWidget() is box
    deactivate()
    assert ui.panel.isVisible(),'自己开对话框导致的失活不该把设置面板收掉'
    box.close(); app.processEvents()
    deactivate()
    assert not ui.panel.isVisible()
    checks+=1
    ui.close_map(); app.processEvents()
    assert ui.toast.isVisible() and ui.toast.text()=='已隐藏'
    stale=(token,None,'过期结果',None,123,{})
    ui.connection=SimpleNamespace(poll=lambda:True,recv=lambda:('result',stale))
    ui.tick()
    assert ui.toast.text()=='已隐藏'
    ui.connection=None
    out=Path(__file__).resolve().parents[2]/'out/mapmatching/toast'
    out.mkdir(parents=True,exist_ok=True)
    ui.toast.grab().save(str(out/'status.png'))
    ui.shutdown(); ui.close()
    print(f'PASS: {checks} success/failure + expanded/collapsed cases, screen bounds, close toast, stale result ignored\n'
          f'  toast widths {widths} px, duration {TOAST_MS} ms')


if __name__=='__main__': main()
