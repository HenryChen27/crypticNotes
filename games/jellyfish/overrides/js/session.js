/* Local-only pause, resumable runs and personal records. Shared by all hosts. */
(() => {
  'use strict';
  const SAVE='jellyfish.savedRun.v1', RANK='jellyfish.records.v1';
  let api, panel, content, mode, records=[], saved=null, lastSave=0;
  const read=(key,fallback)=>{try{return JSON.parse(localStorage.getItem(key)) || fallback;}catch(e){return fallback;}};
  const finite=v=>typeof v==='number'&&Number.isFinite(v);
  function valid(s) {
    return s && s.version===1 && typeof s.runId==='string' && s.runId.length<100
      && ['score','totalScore','clipX','nextLevel'].every(k=>finite(s[k]))
      && s.score>=0 && s.nextLevel>=1 && s.nextLevel<=5
      && (s.dropLevel===null || Number.isInteger(s.dropLevel)&&s.dropLevel>=1&&s.dropLevel<=5)
      && Array.isArray(s.fish)&&s.fish.length<=1000
      && s.fish.every(f=>Number.isInteger(f.level)&&f.level>=1&&f.level<=11
        && ['x','y','angle','vx','vy','av'].every(k=>finite(f[k]))
        && Math.abs(f.x)<20000&&Math.abs(f.y)<20000&&Math.abs(f.vx)<1000&&Math.abs(f.vy)<1000);
  }
  function storage() {
    const data={};
    for(let i=0;i<localStorage.length;i++) {
      const k=localStorage.key(i); if(k.startsWith('jellyfish.')) data[k]=localStorage.getItem(k);
    }
    return JSON.stringify(data);
  }
  let request=0;
  function persist(exit=false) {
    const json=storage();
    if(window.NativeGame && window.NativeGame.saveStorage) {
      const result=window.NativeGame.saveStorage(json,exit);
      if(result!=='ok') throw new Error(result||'保存失败');
      return Promise.resolve();
    }
    const host=window.chrome&&window.chrome.webview || window.webkit&&window.webkit.messageHandlers.game;
    if(host) return new Promise((resolve,reject)=>{
      const id=++request, timer=setTimeout(()=>{delete pending[id];reject(new Error('保存超时，请重试'));},8000);
      pending[id]=(error)=>{clearTimeout(timer);delete pending[id];error?reject(new Error(error)):resolve();};
      host.postMessage({type:'save-storage',id,json,exit});
    });
    if(exit) { hide(); window.close(); }
    return Promise.resolve();
  }
  const pending={};
  window.JellyfishSaveAck=(id,error)=>{if(pending[id])pending[id](error);};
  function remember() {
    if(!api || api.state.phase!=='playing') return;
    const next=api.snapshot(); if(!valid(next)) throw new Error('当前进度无法保存');
    next.savedAt=Date.now();localStorage.setItem(SAVE,JSON.stringify(next));saved=next;
  }
  function hide() {panel.hidden=true;mode=null;}
  function button(text,fn) {
    const b=document.createElement('button'); b.textContent=text; b.type='button';
    b.onclick=async()=>{b.disabled=true;try{await fn();}catch(e){showError(e.message);}finally{b.disabled=false;}};
    content.append(b);return b;
  }
  function showError(message) {
    let e=content.querySelector('.session-error');if(!e){e=document.createElement('p');e.className='session-error';content.append(e);}e.textContent=message;
  }
  function show(title) {
    content.replaceChildren();const h=document.createElement('h2');h.textContent=title;content.append(h);panel.hidden=false;
  }
  function resume() {hide();api.resume();}
  function pause() {
    if(!api || !api.pause())return;
    mode='pause';show('休息一下');
    button('继续游戏',resume);
    button('保存并退出',async()=>{if(api.state.phase==='playing')remember();await persist(true);});
    button('个人排行榜',()=>rank(true));
    button('重新开始',()=>{if(newGame()){hide();api.restart();}});
  }
  function rank(fromPause=false) {
    if(!api)return;
    if(api.state.phase==='playing')api.pause();
    mode=fromPause?'rank-pause':'rank'; show('我的排行榜');
    const hint=document.createElement('p');hint.textContent='仅在本机保存 · 记录已结束的对局';content.append(hint);
    const list=document.createElement('ol');list.className='session-records';
    for(const row of records.slice(0,20)) {
      const li=document.createElement('li');li.textContent=`${row.score} 分 · ${new Date(row.date).toLocaleDateString()} · ${row.maxLevel}级水母`;list.append(li);
    }
    if(!records.length){const p=document.createElement('p');p.textContent='完成第一局后，就会留下成绩。';content.append(p);}
    content.append(list);
    button('返回',()=>{if(fromPause||api.state.phase==='playing')pause();else hide();});
  }
  function newGame() {
    if((saved||api&&api.state.phase==='playing')&&!confirm('开始新一局会替换当前存档，确定吗？'))return false;
    localStorage.removeItem(SAVE);saved=null;return true;
  }
  window.JellyfishSession={
    valid, newGame,
    beginRun(){localStorage.removeItem(SAVE);saved=null;return Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);},
    completeRun(){
      if(!api||!api.state.runId)return;
      const g=api.state;
      if(!records.some(r=>r.id===g.runId)) {
        records.push({id:g.runId,score:g.score,date:Date.now(),maxLevel:Math.max(1,...g.items.map(i=>i.level))});
        records.sort((a,b)=>b.score-a.score||b.date-a.date);records=records.slice(0,50);
        localStorage.setItem(RANK,JSON.stringify(records));
      }
      localStorage.removeItem(SAVE);saved=null;persist().catch(()=>{});
    },
    pause, remember,
    beforeClose(){if(api){api.pause();remember();}return storage();},
    install(adapter){
      api=adapter;saved=read(SAVE,null);if(!valid(saved))saved=null;
      if(window.__JELLYFISH_TEST)window.JellyfishTest=api;
      if(window.__JELLYFISH_TEST)window.JellyfishTest=api;
      records=read(RANK,[]);if(!Array.isArray(records))records=[];
      records=records.filter(r=>r&&finite(r.score)&&finite(r.date)&&Number.isInteger(r.maxLevel)&&typeof r.id==='string').slice(0,50);
      const toolbar=document.createElement('div');toolbar.className='session-ui session-toolbar';
      const p=document.createElement('button');p.textContent='暂停';p.onclick=pause;
      const r=document.createElement('button');r.textContent='我的排行';r.onclick=()=>rank();toolbar.append(p,r);document.body.append(toolbar);
      panel=document.createElement('div');panel.className='session-ui session-shade';panel.hidden=true;
      content=document.createElement('section');content.className='session-card';panel.append(content);document.body.append(panel);
      if(saved){mode='load';show('上次还没玩完');
        const note=document.createElement('p');note.textContent=`${saved.score} 分 · ${new Date(saved.savedAt).toLocaleString()}`;content.append(note);
        button('继续上次游戏',()=>{api.restore(saved);resume();});
        button('开始新游戏',()=>{if(newGame()){hide();api.restart();}});
      }
      document.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();if(mode==='pause')resume();else if(!mode)pause();} },true);
      window.addEventListener('blur',()=>{if(api.state.phase==='playing'){pause();try{remember();persist().catch(()=>{});}catch(e){showError(e.message);}}});
      document.addEventListener('visibilitychange',()=>{if(document.hidden&&api.state.phase==='playing'){pause();try{remember();persist().catch(()=>{});}catch(e){showError(e.message);}}});
      window.addEventListener('pagehide',()=>{try{remember();}catch(e){}});
      setInterval(()=>{if(api.state.phase==='playing'&&!api.state.paused&&Date.now()-lastSave>3000){try{remember();lastSave=Date.now();persist().catch(()=>{});}catch(e){}}},1000);
      window.dispatchEvent(new Event('jellyfish-session-ready'));
    }
  };
})();
