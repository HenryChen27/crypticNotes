"""Actual Windows desktop test against a local example window, no game input."""
import json
from pathlib import Path
import sys
import time
import traceback
import psutil


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--screenshot',type=Path,default=Path('examples/0/example.png'))
    parser.add_argument('--expected-map',default='hard/北-T门')
    parser.add_argument('--output',type=Path,default=Path('out/mapmatching/ui_showcase/local_integration.json'))
    args=parser.parse_args()
    from mapmatching.ui import C,G,W,Companion,native,ROOT
    import win32gui
    import win32con
    import numpy as np
    native.dpi_aware()
    app=W.QApplication([])
    app.setQuitOnLastWindowClosed(False)
    ui=Companion()
    # 跟随功能会监听真实鼠标，而最后两个 phase 跑在真实桌面上：测试期间任何一次
    # 真实的滚轮/按键都会让叠图暂停，fullscreen_result 的断言就会随机失败。
    # 只关掉测试进程里的行为，产品行为不受影响。
    ui.mouse_follow=False
    ui.difficulty.setCurrentIndex(0)
    ui.show()
    assert ui.open_screenshot(ROOT/args.screenshot)
    screen=ui.demo_window
    assert not ui.state.opened, 'Opening a local image waits for G'
    assert ui.target==int(screen.winId()), 'No manual binding needed'
    edges=[]
    ui.keys.edges=lambda: edges.pop(0) if edges else set()
    process=psutil.Process()
    report={'checks':[],'rss_peak_combined_mb':0,'runs':[],'dpi':app.primaryScreen().devicePixelRatio()}
    started=time.perf_counter()
    phase='ready'
    idle_start=None
    idle_cpu=None
    stop_deadline=None
    baseline=None
    out=ROOT/args.output

    def cpu_total():
        total=0
        for proc in [process]+process.children(recursive=True):
            try:
                t=proc.cpu_times()
                total+=t.user+t.system
            except psutil.NoSuchProcess:
                pass
        return total

    def focus():
        screen.raise_()
        screen.activateWindow()
        app.processEvents()
        if win32gui.GetForegroundWindow()!=int(screen.winId()):
            try:
                win32gui.SetForegroundWindow(int(screen.winId()))
            except Exception:
                return False
        return win32gui.GetForegroundWindow()==int(screen.winId())

    def check(condition,message):
        if not condition:
            raise AssertionError(message)
        report['checks'].append(message)

    def finish(error=None):
        report['error']=error
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=True,indent=2),flush=True)
        timer.stop()
        app.exit(1 if error else 0)

    def step():
        nonlocal phase,idle_start,idle_cpu,stop_deadline,baseline,screen
        try:
            # Do not include repeated psutil process enumeration in idle CPU.
            if phase=='idle' and time.perf_counter()-idle_start<5:
                return
            rss=0
            for proc in [process]+process.children(recursive=True):
                try:
                    rss+=proc.memory_info().rss/1024**2
                except psutil.NoSuchProcess:
                    pass
            report['rss_peak_combined_mb']=max(report['rss_peak_combined_mb'],rss)
            if time.perf_counter()-started>45:
                raise TimeoutError(f'phase={phase}, status={ui.status.text()}')
            if phase=='ready' and getattr(ui,'ready',False):
                report['preparation_ms']=(time.perf_counter()-started)*1000
                report['idle_before_match_rss_mb']=rss
                if not focus():
                    return
                baseline=native.capture(native.client_rect(int(screen.winId())))
                edges.append({0x47})
                phase='first'
            elif phase=='first' and hasattr(ui,'last_result'):
                check(ui.overlay.isVisible(),'real desktop capture -> automatic match -> visible overlay')
                check(ui.last_result['result']['candidates'][0]['map_id']==args.expected_map,'scaled captured example matches reviewed expected identity')
                check(ui.last_result['result']['diagnostics']['pipeline']=='recognition','first open performs identity recognition')
                check(native.client_rect(int(ui.overlay.winId()))==ui.rect_at_capture,'overlay physical client rectangle equals capture at current DPI')
                style=win32gui.GetWindowLong(int(ui.overlay.winId()),win32con.GWL_EXSTYLE)
                check(bool(style & win32con.WS_EX_TRANSPARENT) and bool(style & win32con.WS_EX_NOACTIVATE),'overlay mouse-through and no-activation flags')
                check(win32gui.GetForegroundWindow()==int(screen.winId()),'showing overlay preserves foreground window')
                x,y,w,h=ui.rect_at_capture
                check(win32gui.WindowFromPoint((x+w//2,y+h//2))==int(screen.winId()),'hit-testing passes through overlay to underlying screenshot window')
                from mapmatching.src.live import raw_layer,composite
                from mapmatching.src.reference import Reference,read_image
                from mapmatching.src.types import Candidate,Pose
                from mapmatching.src import mapstore
                data=ui.last_result['result']['candidates'][0].copy()
                data['pose']=Pose(**data['pose'])
                candidate=Candidate(**data)
                # source/regions/exclude_regions 现在只在 floors.json 里；index.json 只剩特征指针。
                record=next(e for e in mapstore.read_manifest(mapstore.maps_dir(ROOT)) if e['map_id']==candidate.map_id)
                ref=Reference(candidate.map_id,'hard',None,record['source'],None,None,record.get('regions',[]),record.get('exclude_regions',[]))
                layer=raw_layer(baseline.shape,read_image(ROOT/ref.source),ref,candidate,
                                ui.last_result['result']['diagnostics'].get('excluded_panel_boxes',[]))
                expected=composite(baseline,layer,ui.opacity.value()/100)
                actual=native.capture(ui.rect_at_capture)
                error=np.abs(expected.astype(float)-actual.astype(float))[layer[:,:,3]>250]
                report['display_pixel_error_p95']=float(np.percentile(error,95))
                check(report['display_pixel_error_p95']<=3,'actual displayed original-color 30% blend matches expected physical pixels (p95 <= 3)')
                report['runs'].append(ui.last_result)
                edges.append({0x47})
                phase='closed'
            elif phase=='closed':
                check(not ui.state.opened and not ui.overlay.isVisible(),'second G hides overlay and closes matching session')
                del ui.last_result
                edges.append({0x47})
                phase='second'
            elif phase=='second' and hasattr(ui,'last_result'):
                check(ui.overlay.isVisible(),'next G rematches with persistent worker')
                check(ui.last_result['result']['diagnostics']['pipeline']=='cached_registration','second open only registers the remembered map')
                report['runs'].append(ui.last_result)
                edges.append({0x1B})
                phase='escape'
            elif phase=='escape':
                check(not ui.state.opened and not ui.overlay.isVisible(),'Esc hides overlay')
                idle_start=time.perf_counter()
                idle_cpu=cpu_total()
                phase='idle'
            elif phase=='idle' and time.perf_counter()-idle_start>=5:
                report['idle_after_match_rss_mb']=rss
                report['idle_cpu_percent_one_core']=(cpu_total()-idle_cpu)/(time.perf_counter()-idle_start)*100
                report['idle_cpu_percent_whole_machine']=report['idle_cpu_percent_one_core']/psutil.cpu_count()
                # Force actual work then cancel its process; result must not return.
                pixels=native.capture(native.client_rect(int(screen.winId())))
                token=ui.state.open()
                ui.pending=(token,pixels)
                ui.start_worker()
                pid=ui.process.pid
                check(ui.busy,'work request was in flight before cancellation')
                ui.close_map()
                check(not psutil.pid_exists(pid),'closing during work terminates matching process')
                stop_deadline=time.perf_counter()+.7
                phase='cancelled'
            elif phase=='cancelled' and time.perf_counter()>stop_deadline:
                check(not ui.overlay.isVisible() and not ui.state.opened,'cancelled result never reappears')
                ui.toggle_panel()
                ui.difficulty.setCurrentIndex(1)
                check(ui.party_row.isVisible(),'Nightmare displays party selector')
                ui.difficulty.setCurrentIndex(0)
                check(not ui.party_row.isVisible(),'Hard hides party selector')
                check(ui.cached_candidate is None,'difficulty change clears remembered map')
                check(not ui.open_screenshot(ROOT/'examples/missing.png'),'invalid image is rejected')
                check(ui.demo_window is screen,'invalid image preserves current screenshot')
                ui.state.open()
                screen.close()
                check(ui.demo is None and ui.target is None and not ui.state.opened,'closing screenshot stops matching and returns to game mode')
                check(ui.open_screenshot(ROOT/'examples/1/example2.png'),'another screenshot can be opened')
                ui.leave_demo()
                check(ui.demo_window is None and not ui.return_game.isVisible(),'return to game mode closes local screenshot')
                screen=W.QLabel()
                screen.setWindowTitle('普通图片查看器')
                screen.setPixmap(G.QPixmap(str((ROOT/args.screenshot).resolve())))
                screen.setScaledContents(True)
                screen.showFullScreen()
                del ui.last_result
                phase='fullscreen_ready'
            elif phase=='fullscreen_ready':
                if not focus():
                    return
                check(ui.is_game(int(screen.winId())),'screen capture accepts a normal image viewer without game title or binding')
                edges.append({0x47})
                phase='fullscreen_result'
            elif phase=='fullscreen_result' and hasattr(ui,'last_result'):
                check(ui.overlay.isVisible(),'direct full-screen capture produces overlay')
                check(ui.rect_at_capture==native.monitor_rect(int(screen.winId())),'direct capture uses physical monitor bounds')
                check(ui.last_result['result']['candidates'][0]['map_id']==args.expected_map,'full-screen image viewer identifies same reviewed map')
                report['screen_mode_run']=ui.last_result
                screen.close()
                finish()
        except Exception:
            finish(traceback.format_exc())

    timer=C.QTimer()
    timer.timeout.connect(step)
    timer.start(50)
    sys.exit(app.exec())


if __name__=='__main__':
    main()
