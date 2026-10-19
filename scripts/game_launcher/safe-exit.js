// Namespace local game storage for compatibility with the existing launcher.
(()=>{
 const map=k=>String(k).startsWith('bone-gift-')?'jellyfish.local.'+k:k;
 for(const name of ['getItem','setItem','removeItem']){
  const original=Storage.prototype[name];
  Storage.prototype[name]=function(key,...args){return original.call(this,map(key),...args)};
 }
})();
/* Host transport; game owns saving and gameplay UI. */
window.__jellyfishHostSave = async function(id) {
  const close = window.close;
  try {
    window.close = function() {};
    const api=window.JellyfishGame;
    if(typeof window.MinesweeperGame?.prepareToClose==='function') {
      const result=await window.MinesweeperGame.prepareToClose();
      if(!result?.ok || !result?.readyToClose)throw new Error(result?.error || 'Game save failed');
    } else if(typeof api?.safeSaveAndExit==='function') {
      const result=await api.safeSaveAndExit();
      if(!result?.saved)throw new Error(result?.reason || '游戏保存失败');
    } else if(typeof api?.save==='function') {
      const result=await api.save();
      if(result!==true && result?.saved!==true)throw new Error(result?.reason || '游戏保存失败');
    } else throw new Error('小游戏缺少保存接口');
    window.__jellyfishHostFrozen=true;
    const values = {};
    for (let i=0;i<localStorage.length;i++) {
      const key=localStorage.key(i);
      if(key.startsWith('jellyfish.')) values[key]=localStorage.getItem(key);
    }
    window.__jellyfishHostPost({type:'safe-exit',id,saved:true,json:JSON.stringify(values)});
  } catch(e) {
    window.__jellyfishHostFrozen=false;
    if(window.MinesweeperGame?.resume) await window.MinesweeperGame.resume();
    window.__jellyfishHostPost({type:'safe-exit',id,saved:false,reason:String(e.message||e)});
  } finally { window.close=close; }
};
