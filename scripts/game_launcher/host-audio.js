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
  // Route Web Audio effects through a temporary host master bus as well.
  const buses=new Map();
  if(window.AudioNode){
    const connect=AudioNode.prototype.connect,disconnect=AudioNode.prototype.disconnect;
    const bus=context=>{
      if(!buses.has(context)){
        const gain=context.createGain();gain.gain.value=muted?0:1;
        connect.call(gain,context.destination);buses.set(context,gain);
        context.addEventListener('statechange',()=>{if(context.state==='closed')buses.delete(context);});
      }
      return buses.get(context);
    };
    AudioNode.prototype.connect=function(target,...args){
      if(target===this.context.destination){connect.call(this,bus(this.context),...args);return target;}
      return connect.call(this,target,...args);
    };
    AudioNode.prototype.disconnect=function(target,...args){
      if(target===this.context.destination&&buses.has(this.context))return disconnect.call(this,buses.get(this.context),...args);
      return arguments.length?disconnect.call(this,target,...args):disconnect.call(this);
    };
  }
  window.__jellyfishSetMuted=value=>{
    muted=!!value;
    for(const gain of buses.values())gain.gain.value=muted?0:1;
    for(const media of tracked){
      if(muted){if(!prior.has(media))prior.set(media,media.muted);media.muted=true;}
      else if(prior.has(media)){media.muted=prior.get(media);prior.delete(media);}
    }
  };
})();
