/* Reuse sprite animation phases on mobile; preserve assets, physics and silhouette. */
(()=>{
  function install(){
    if(typeof JellyfishAnimation==='undefined')return;
    const original=JellyfishAnimation.draw,cache=new WeakMap(),steps=48,maxSide=160;
    JellyfishAnimation.draw=function(ctx,item,profile,time=performance.now()){
      if(item.level===1||item.level===2){
        ctx.drawImage(item.sprite,-item.w/2,-item.h/2,item.w,item.h);return;
      }
      if(!item.sprite||!profile||!profile.period)return original(ctx,item,profile,time);
      let entry=cache.get(item.sprite);
      if(!entry||entry.profile!==profile||entry.w!==item.w||entry.h!==item.h){
        entry={profile,w:item.w,h:item.h,frames:[]};cache.set(item.sprite,entry);
      }
      const cycle=time/profile.period+(item.breathPhase||0)/(Math.PI*2);
      const phase=((Math.round(cycle*steps)%steps)+steps)%steps;
      let frame=entry.frames[phase];
      if(!frame){
        const scale=Math.min(1,maxSide/Math.max(item.w,item.h));
        frame=document.createElement('canvas');frame.width=Math.max(1,Math.round(item.w*scale));frame.height=Math.max(1,Math.round(item.h*scale));
        const target=frame.getContext('2d');target.translate(frame.width/2,frame.height/2);
        original(target,{...item,w:frame.width,h:frame.height,breathPhase:0},profile,phase*profile.period/steps);
        entry.frames[phase]=frame;
      }
      ctx.drawImage(frame,-item.w/2,-item.h/2,item.w,item.h);
    };
  }
  if(document.readyState==='complete')install();else window.addEventListener('load',install,{once:true});
})();
