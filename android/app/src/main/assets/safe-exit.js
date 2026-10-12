/* Host transport; game owns saving and gameplay UI. */
window.__jellyfishHostSave = async function(id) {
  const close = window.close;
  try {
    if (!window.JellyfishGame?.safeSaveAndExit) throw new Error('安全存档接口尚未准备好');
    window.close = function() {};
    const result = await window.JellyfishGame.safeSaveAndExit();
    if (!result?.saved) throw new Error(result?.reason || '游戏保存失败');
    const values = {};
    for (let i=0;i<localStorage.length;i++) {
      const key=localStorage.key(i);
      if(key.startsWith('jellyfish.')) values[key]=localStorage.getItem(key);
    }
    window.__jellyfishHostPost({type:'safe-exit',id,saved:true,json:JSON.stringify(values)});
  } catch(e) {
    window.__jellyfishHostPost({type:'safe-exit',id,saved:false,reason:String(e.message||e)});
  } finally { window.close=close; }
};
