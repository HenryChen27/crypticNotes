/* Bound mobile rendering work on high-refresh screens, preserving timestamps. */
(()=>{
  const request=window.requestAnimationFrame.bind(window),cancel=window.cancelAnimationFrame.bind(window);
  const jobs=new Map();let nextId=1,lastFrame=-Infinity,nextFrame=-Infinity;
  window.requestAnimationFrame=callback=>{
    const id=nextId++;
    const tick=timestamp=>{
      if(!jobs.has(id))return;
      if(window.__jellyfishHostFrozen){jobs.set(id,request(tick));return;}
      if(timestamp===lastFrame||timestamp+.2>=nextFrame){
        if(timestamp!==lastFrame){nextFrame=Number.isFinite(nextFrame)?Math.max(nextFrame+1000/60,timestamp+.01):timestamp+1000/60;lastFrame=timestamp;}
        jobs.delete(id);callback(timestamp);
      }
      else jobs.set(id,request(tick));
    };
    jobs.set(id,request(tick));return id;
  };
  window.cancelAnimationFrame=id=>{if(jobs.has(id)){cancel(jobs.get(id));jobs.delete(id);}};
})();
