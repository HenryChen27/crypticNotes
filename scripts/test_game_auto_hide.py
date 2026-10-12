"""Local real WebView2 tests: safe auto-close and restoration cancellation."""
import json,subprocess,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'build/local-scene-test'

def wait_for(predicate,timeout=30):
    end=time.monotonic()+timeout
    while not predicate():
        if time.monotonic()>end:raise TimeoutError('Native launcher did not reach expected state')
        time.sleep(.05)

def state(folder):
    try:return json.loads((folder/'window-state.json').read_text())
    except (OSError,ValueError):return {}

def command(folder,action):
    temp=folder/'command.tmp';temp.write_text(json.dumps({'action':action,'id':time.time_ns()}));temp.replace(folder/'window-command.json')

def run(cancel):
    folder=BASE/('auto-cancel' if cancel else 'auto-close')/str(time.time_ns());folder.mkdir(parents=True)
    script=folder/'start.js';script.write_text("localStorage.setItem('jellyfish.autoHideTest','keep');document.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));({waitForExit:true})")
    proc=subprocess.Popen([str(BASE/'GameLauncher.exe'),'--game-root',str(ROOT/'minigames/jellyfish/game'),'--profile',str(folder),'--smoke-report',str(folder/'loaded.json'),'--test-script',str(script)])
    try:
        wait_for(lambda:(folder/'loaded.json').exists())
        time.sleep(6)
        command(folder,'auto-hide');wait_for(lambda:state(folder).get('hidden') is True)
        started=time.monotonic()
        if cancel:
            time.sleep(1);command(folder,'show');wait_for(lambda:state(folder).get('hidden') is False)
            time.sleep(5.2);assert proc.poll() is None,'Restored game was still auto-closed'
            command(folder,'safe-close')
        assert proc.wait(timeout=15)==0
        if not cancel:assert time.monotonic()-started>=4.8,'Closed before the 5-second grace period'
        saved=json.loads((folder/'local-storage.json').read_text())
        assert saved['jellyfish.autoHideTest']=='keep'
        assert 'jellyfish.session.v1' in saved,'Gameplay progress was not saved'
        print('Passed:', 'restore cancelled automatic close' if cancel else 'automatic close saved gameplay after 5 seconds',flush=True)
    finally:
        if proc.poll() is None:command(folder,'safe-close');proc.wait(timeout=15)

if __name__=='__main__':run(False);run(True)
