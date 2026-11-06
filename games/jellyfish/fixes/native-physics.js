// Planck 1.5.1 integration. Matter body objects remain the render/save model;
// all dynamics and contacts are solved here with native circle colliders.
const NativePhysics=(()=>{
  const SCALE=100;
  function create(engine) {
    const pl=planck;
    pl.Settings.maxPolygonVertices=32;
    const world=new pl.World({gravity:pl.Vec2(CONFIG.PHYSICS.gravity.x*10,CONFIG.PHYSICS.nativeGravity),allowSleep:true});
    const entries=new Map();let began=[];
    const pair=contact=>({bodyA:contact.getFixtureA().getBody().getUserData(),bodyB:contact.getFixtureB().getBody().getUserData()});
    world.on('begin-contact',contact=>began.push(pair(contact)));
    function shape(body) {
      if(body.isStatic)return pl.Box((body.bounds.max.x-body.bounds.min.x)/SCALE/2,(body.bounds.max.y-body.bounds.min.y)/SCALE/2);
      const def=CONFIG.JELLYFISH[body.jellyfishLevel-1];
      if(def.type==='circle')return pl.Circle(Math.max(def.width,def.height)/SCALE/2);
      return pl.Polygon(Array.from({length:32},(_,i)=>{
        const a=i*Math.PI*2/32;return pl.Vec2(Math.cos(a)*def.width/SCALE/2,Math.sin(a)*def.height/SCALE/2);
      }));
    }
    function snapshot(body) {
      return {x:body.position.x,y:body.position.y,angle:body.angle,vx:body.position.x-body.positionPrev.x,
        vy:body.position.y-body.positionPrev.y,av:body.angle-body.anglePrev,sleeping:body.isSleeping};
    }
    function sync(delta) {
      const bodies=Matter.Composite.allBodies(engine.world),present=new Set(bodies);
      for(const [body,entry] of entries)if(!present.has(body)){world.destroyBody(entry.native);entries.delete(body);}
      for(const body of bodies) {
        let entry=entries.get(body);
        if(!entry) {
          const native=world.createBody({type:body.isStatic?'static':'dynamic',position:pl.Vec2(body.position.x/SCALE,body.position.y/SCALE),
            angle:body.angle,linearDamping:0.8,angularDamping:2,bullet:false,userData:body});
          native.createFixture(shape(body),{density:body.isStatic?0:CONFIG.PHYSICS.density*SCALE*SCALE,
            friction:body.friction,restitution:body.restitution});
          native.setLinearVelocity(pl.Vec2((body.position.x-body.positionPrev.x)/SCALE/delta,(body.position.y-body.positionPrev.y)/SCALE/delta));
          native.setAngularVelocity((body.angle-body.anglePrev)/delta);
          native.setAwake(!body.isSleeping);
          entry={native,last:snapshot(body)};entries.set(body,entry);
        }else {
          const current=snapshot(body),last=entry.last,native=entry.native;
          if(Math.abs(current.x-last.x)+Math.abs(current.y-last.y)+Math.abs(current.angle-last.angle)>1e-7) {
            native.setTransform(pl.Vec2(current.x/SCALE,current.y/SCALE),current.angle);
          }
          if(Math.abs(current.vx-last.vx)+Math.abs(current.vy-last.vy)>1e-7){native.setLinearVelocity(pl.Vec2(current.vx/SCALE/delta,current.vy/SCALE/delta));}
          if(Math.abs(current.av-last.av)>1e-7)native.setAngularVelocity(current.av/delta);
          if(current.sleeping!==last.sleeping){native.setAwake(!current.sleeping);}
        }
      }
    }
    function step(ms) {
      const delta=ms/1000;began=[];sync(delta);
      world.step(delta,16,16);
      for(const [body,entry] of entries) {
        if(body.isStatic)continue;
        const native=entry.native,pos=native.getPosition(),velocity=native.getLinearVelocity();
        Matter.Body.setPosition(body,{x:pos.x*SCALE,y:pos.y*SCALE});
        Matter.Body.setAngle(body,native.getAngle());
        body.positionPrev.x=body.position.x-velocity.x*SCALE*delta;
        body.positionPrev.y=body.position.y-velocity.y*SCALE*delta;
        body.anglePrev=body.angle-native.getAngularVelocity()*delta;
        body.velocity.x=velocity.x*SCALE*delta;body.velocity.y=velocity.y*SCALE*delta;
        body.angularVelocity=native.getAngularVelocity()*delta;
        body.speed=Math.hypot(velocity.x,velocity.y)*SCALE/60;
        body.angularSpeed=Math.abs(native.getAngularVelocity())/60;
        if(body.isSleeping===native.isAwake())Matter.Sleeping.set(body,!native.isAwake());
        entry.last=snapshot(body);
      }
      // Emit merge/landing events only after the world unlocks.
      const active=[];
      for(let contact=world.getContactList();contact;contact=contact.getNext())if(contact.isTouching())active.push(pair(contact));
      if(began.length)Matter.Events.trigger(engine,'collisionStart',{pairs:began});
      if(active.length)Matter.Events.trigger(engine,'collisionActive',{pairs:active});
      engine.timing.timestamp+=ms;
    }
    return {step,world};
  }
  return {create};
})();
