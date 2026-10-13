/* Native display pacing; pause only while showing the resize snapshot. */
(()=>{
  const request=window.requestAnimationFrame.bind(window),cancel=window.cancelAnimationFrame.bind(window);
  const jobs=new Map();let nextId=1,lastFrame=-Infinity,frames=0,started=0,worstGap=0;
  window.requestAnimationFrame=callback=>{
    const id=nextId++;
    const tick=timestamp=>{
      if(!jobs.has(id))return;
      if(window.__jellyfishHostFrozen){jobs.set(id,request(tick));return;}
      if(timestamp!==lastFrame){
        if(Number.isFinite(lastFrame))worstGap=Math.max(worstGap,timestamp-lastFrame);
        lastFrame=timestamp;frames++;if(!started)started=timestamp;
        if(timestamp-started>=5000){
          const stats={rafFps:Math.round(frames*10000/(timestamp-started))/10,worstGapMs:Math.round(worstGap),capped:false};
          window.__jellyfishFrameStats=stats;
          if(window.NativeGame?.reportFrameStats)window.NativeGame.reportFrameStats(JSON.stringify(stats));
          frames=0;started=timestamp;worstGap=0;
        }
      }
      jobs.delete(id);callback(timestamp);
    };
    jobs.set(id,request(tick));return id;
  };
  window.cancelAnimationFrame=id=>{if(jobs.has(id)){cancel(jobs.get(id));jobs.delete(id);}};
})();
