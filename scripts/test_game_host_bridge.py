"""Exercise async success/failure transport without closing the page early."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page()
    page.route('https://bridge.test/',lambda route:route.fulfill(body='<html></html>',content_type='text/html'))
    page.goto('https://bridge.test/')
    page.evaluate("()=>{window.messages=[];window.__jellyfishHostPost=m=>messages.push(m);localStorage.setItem('jellyfish.session.v1','progress');localStorage.setItem('other','private');window.close=()=>{window.earlyClose=true};}")
    page.add_script_tag(content=(ROOT/'scripts/game_launcher/safe-exit.js').read_text(encoding='utf-8'))
    page.evaluate("window.JellyfishGame={safeSaveAndExit:async()=>{await new Promise(r=>setTimeout(r,30));window.close();return {saved:true,closed:false,reason:'close_blocked'}}}")
    page.evaluate('__jellyfishHostSave(1)')
    result=page.evaluate('messages.pop()')
    assert result=={'type':'safe-exit','id':1,'saved':True,'json':'{"jellyfish.session.v1":"progress"}'},result
    assert not page.evaluate('!!window.earlyClose')
    page.evaluate("window.JellyfishGame={safeSaveAndExit:async()=>({saved:false,reason:'save_failed'})};__jellyfishHostSave(2)")
    result=page.evaluate('messages.pop()')
    assert result['saved'] is False and result['reason']=='save_failed' and 'json' not in result,result
    page.evaluate('delete window.JellyfishGame;__jellyfishHostSave(3)')
    assert page.evaluate('messages.pop().saved') is False
    assert (ROOT/'android/app/src/main/assets/safe-exit.js').read_bytes()==(ROOT/'scripts/game_launcher/safe-exit.js').read_bytes()
    browser.close()
print('Host bridge passed: awaited save, prevented early close, filtered storage, retained failure.')
