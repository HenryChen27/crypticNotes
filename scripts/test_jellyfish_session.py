"""Real browser checks using the packaged game, including Matter state."""
from pathlib import Path
import functools
import http.server
import json
import threading
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args): pass

def main():
    game=ROOT/'out/minigames-native/jellyfish/game'
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(game)))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            page=browser.new_page(viewport={'width':1160,'height':670})
            page.add_init_script("window.__JELLYFISH_TEST=true; window.NativeGame={saveStorage:(json,exit)=>{window.lastPersist={json,exit};return 'ok'}}")
            page.goto(f'http://127.0.0.1:{server.server_port}/index.html')
            page.wait_for_function('!!window.JellyfishTest',timeout=60000)
            state={'version':1,'runId':'test-restore','score':100,'totalScore':100,'clipX':1250,'dropLevel':2,'nextLevel':4,
                   'fish':[{'level':3,'x':1250,'y':950,'angle':.3,'vx':0,'vy':1,'av':.01,'sleeping':False}]}
            page.evaluate('(s)=>{JellyfishTest.restore(s);JellyfishSession.pause()}',state)
            before=page.evaluate('JellyfishTest.snapshot()')
            page.wait_for_timeout(1200)
            assert before==page.evaluate('JellyfishTest.snapshot()'),'pause changed physics'
            page.get_by_role('button',name='保存并退出',exact=True).click()
            assert page.evaluate('lastPersist.exit')
            saved=json.loads(page.evaluate("localStorage.getItem('jellyfish.savedRun.v1')"))
            assert saved['fish']==before['fish'] and saved['nextLevel']==4 and saved['score']==100
            page.reload();page.wait_for_function('!!window.JellyfishTest',timeout=60000)
            page.evaluate("()=>{[...document.querySelectorAll('.session-card button')].find(b=>b.textContent==='继续上次游戏').click();JellyfishSession.pause()}")
            restored=page.evaluate('JellyfishTest.snapshot()')
            assert restored['fish']==saved['fish'] and restored['score']==100, (restored,saved)
            page.evaluate("JellyfishTest.state.phase='gameover';JellyfishSession.completeRun();JellyfishSession.completeRun()")
            records=json.loads(page.evaluate("localStorage.getItem('jellyfish.records.v1')"))
            assert len(records)==1 and records[0]['score']==100
            assert page.evaluate("localStorage.getItem('jellyfish.savedRun.v1')")==None
            assert not page.evaluate('JellyfishSession.valid({version:1,fish:[]})')
            # Pending merge snapshots must contain the result, not two ghosts.
            state['runId']='merge';state['score']=0;state['totalScore']=0
            state['fish']=[dict(state['fish'][0],level=1,x=1250,y=950,vx=0,vy=0,av=0),dict(state['fish'][0],level=1,x=1252,y=950,vx=0,vy=0,av=0)]
            page.evaluate('(s)=>{JellyfishTest.restore(s);JellyfishTest.resume()}',state)
            page.wait_for_function('JellyfishTest.state.merges.length>0',timeout=5000)
            merged=page.evaluate('()=>{JellyfishTest.pause();return JellyfishTest.snapshot()}')
            assert len(merged['fish'])==1 and merged['fish'][0]['level']==2 and merged['score']>0,merged
            page.evaluate('(s)=>{JellyfishTest.restore(s);JellyfishTest.pause()}',merged)
            assert page.evaluate('JellyfishTest.state.score')==merged['score']
            page.screenshot(path=str(ROOT/'out/minigames-native/session-ui.png'))
            (ROOT/'out/minigames-native/session-test.json').write_text(json.dumps({'ok':True,'pause':True,'restore':True,'exit':True,'rank_deduplicated':True,'merge_restore':True},indent=2))
            browser.close()
    finally:server.shutdown()
    print('Pause, save/exit, restore, pending merge and local records passed.')

if __name__=='__main__':main()
