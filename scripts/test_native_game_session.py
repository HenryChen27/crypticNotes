"""Windows native bridge must persist, exit, then import a saved run."""
import json
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
def main():
    out=ROOT/'out/minigames-native'
    test=ROOT/'out/native-session-test'/str(time.time_ns());test.mkdir(parents=True)
    profile=test/'profile'
    command=[str(out/'windows-x64/GameLauncher.exe'),'--game-root',str(out/'jellyfish/game'),'--profile',str(profile)]
    state={'version':1,'runId':'native-test','score':321,'totalScore':321,'clipX':1250,'dropLevel':2,'nextLevel':4,
           'fish':[{'level':3,'x':1250,'y':950,'angle':.3,'vx':0,'vy':1,'av':.01,'sleeping':False}]}
    first=test/'first.js';report=test/'first.json'
    first.write_text("(()=>{if(!JellyfishTest)throw Error('Not ready');JellyfishTest.restore("+json.dumps(state)+");JellyfishSession.pause();[...document.querySelectorAll('.session-card button')].find(b=>b.textContent==='保存并退出').click();return {waitForExit:true,ok:true}})()",encoding='utf-8')
    result=subprocess.run(command+['--test-script',str(first),'--smoke-report',str(report)],timeout=30)
    assert result.returncode==0,result.returncode
    storage=json.loads((profile/'local-storage.json').read_text(encoding='utf-8-sig'))
    saved=json.loads(storage['jellyfish.savedRun.v1'])
    assert saved['score']==321 and saved['fish']==state['fish'],saved
    # Make sure the subsequent launch imports the explicit persisted file.
    second=test/'second.js';report=test/'second.json'
    second.write_text("(()=>{if(!document.querySelector('.session-shade:not([hidden])'))throw Error('No continue prompt');[...document.querySelectorAll('.session-card button')].find(b=>b.textContent==='继续上次游戏').click();JellyfishSession.pause();return JellyfishTest.snapshot()})()",encoding='utf-8')
    result=subprocess.run(command+['--test-script',str(second),'--smoke-report',str(report)],timeout=30)
    assert result.returncode==0,result.returncode
    restored=json.loads(report.read_text(encoding='utf-8-sig'))
    assert restored['fish']==saved['fish'] and restored['score']==321,restored
    print('Native save acknowledgment, exit, restart and restore passed:',test)

if __name__=='__main__':main()
