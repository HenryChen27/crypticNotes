/* Temporary host mute: never overwrite the player's saved audio settings. */
(()=>{
  let muted=false;
  const tracked=new Set(), prior=new WeakMap(), watched=new WeakSet();
  const play=HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play=function(...args){
    tracked.add(this);
    if(!watched.has(this)){watched.add(this);this.addEventListener('ended',()=>tracked.delete(this));}
    if(muted){if(!prior.has(this))prior.set(this,this.muted);this.muted=true;}
    return play.apply(this,args);
  };
  window.__jellyfishSetMuted=value=>{
    muted=!!value;
    for(const media of tracked){
      if(muted){if(!prior.has(media))prior.set(media,media.muted);media.muted=true;}
      else if(prior.has(media)){media.muted=prior.get(media);prior.delete(media);}
    }
  };
})();
