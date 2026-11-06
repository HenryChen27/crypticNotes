import math
import random
import numpy as np
from PySide6 import QtCore as C, QtGui as G
from .skins import doll

class PetAnimation:
    """Layered rig player for the companion mascot.

    Besides the skin's own moods, three runtime modifiers are blended on top of
    whatever pose is playing, so they need no new animation data:

    - ``look``: a head turn in degrees (towards the speech bubble, the cursor).
    - ``drag``: limb swing and torso lean driven by the drag velocity while the
      player carries the doll, with a spring so limbs trail the hand.
    - ``opacity``: the idle fade.

    The idle breath is cached as frames; any active modifier switches that
    frame back to a live render, so the cache never shows a stale head.
    """
    IDLE_FRAMES = 30
    BASE_SIZE = (112, 132)
    GAME_SIZE = (146, 176)
    BASE_ORIGIN = (7, 20)

    def __init__(self, button, skin=doll):
        self.skin = skin
        self.button = button
        self.pixmap = G.QPixmap(str(skin.IMAGE))
        self.layers = {}
        if not self.pixmap.isNull():
            for name, vertices in skin.PARTS.items():
                layer = G.QPixmap(306, 332)
                layer.fill(C.Qt.transparent)
                painter = G.QPainter(layer)
                painter.setRenderHint(G.QPainter.Antialiasing)
                path = G.QPainterPath()
                path.addPolygon(G.QPolygonF([C.QPointF(*v) for v in vertices]))
                painter.setClipPath(path)
                painter.drawPixmap(C.QRect(0,0,306,332), self.pixmap)
                painter.end()
                self.layers[name] = layer
            # One continuous source mask per arm, with no overlaid elbow seam.
            for side in ('left','right'):
                layer=G.QPixmap(306,332);layer.fill(C.Qt.transparent)
                painter=G.QPainter(layer)
                path=G.QPainterPath()
                for section in ('upper','lower'):
                    section_path=G.QPainterPath()
                    section_path.addPolygon(G.QPolygonF([C.QPointF(*v) for v in skin.PARTS[side+'_'+section]]))
                    path=path.united(section_path)
                painter.setRenderHint(G.QPainter.Antialiasing)
                painter.setClipPath(path)
                painter.drawPixmap(C.QRect(0,0,306,332),self.pixmap)
                painter.end();self.layers[side+'_arm']=layer
        self.enabled = False
        self.mood = 'curious'
        self.wave_right = False
        self.clock = C.QElapsedTimer()
        self.since_play = C.QElapsedTimer()
        self.timer = C.QTimer(button)
        self.timer.setInterval(25)
        self.timer.timeout.connect(self.advance)
        # The idle breath is a fixed 3 s loop with no randomness, so its frames
        # are rendered once and blitted; the full limb warp ran 20 times a
        # second for as long as the companion was on screen.
        self._idle_cache = {}
        self._idle_index = None
        # Runtime modifiers (see class docstring).
        self.scale = 1.
        self.look = 0.
        self.look_current = 0.
        self.opacity = 1.
        self.opacity_target = 1.
        self.shadow = True
        self.dragging = False
        self.drag_velocity = 0.
        self.drag_swing = 0.
        self.drag_lean = 0.
        self.drag_lift = 0.

    # ── sizing ─────────────────────────────────────────────────
    def widget_size(self, game_background=False):
        w, h = self.GAME_SIZE if game_background else self.BASE_SIZE
        return int(round(w*self.scale)), int(round(h*self.scale))

    def origin_for(self, width, height, game_background=False):
        """Where the 306×332 canvas lands inside a widget of this size."""
        base_w, base_h = self.widget_size(False)
        return (self.BASE_ORIGIN[0]*self.scale + (width-base_w)/2,
                self.BASE_ORIGIN[1]*self.scale + (height-base_h)/2)

    @property
    def render_scale(self):
        return .32*self.scale

    def set_scale(self, factor):
        self.scale = max(.5, min(2., float(factor)))
        self._idle_cache.clear()
        self.apply_size()

    def apply_size(self):
        game = getattr(self.button, 'game_background', False)
        if self.enabled:
            self.button.setFixedSize(*self.widget_size(game))
        else:
            self.button.setFixedSize(46, 46)

    # ── lifecycle ──────────────────────────────────────────────
    def enable(self, enabled):
        self.enabled = bool(enabled and not self.pixmap.isNull())
        extra=getattr(self.button,'match_timer',None)
        if extra is not None:
            if self.enabled:extra.stop()
            elif getattr(self.button,'matching',False) or getattr(self.button,'game_background',False):extra.start()
        self.timer.stop()
        if self.enabled:
            self.mood = 'matching' if getattr(self.button,'matching',False) or getattr(self.button,'game_background',False) else 'idle'
            self.clock.start()
            self.since_play.start()
            self.timer.start(50)
        self.apply_size()
        self.button.update()

    def play(self, mood):
        if not self.enabled:
            return
        if (getattr(self.button, 'matching', False) or getattr(self.button,'game_background',False)) and mood != 'matching':
            return
        if self.timer.isActive() and self.mood == mood:
            return
        self.mood = mood
        if mood == 'curious':
            self.wave_right = random.choice((False, True))
        self.clock.start()
        self.since_play.start()
        self.timer.start(25)
        self.button.update()

    @property
    def looping(self):
        return self.mood in getattr(self.skin, 'LOOPING', ('matching',))

    def advance(self):
        if self.clock.elapsed() >= self.duration:
            if not self.looping:
                self.mood = 'idle'
            self.clock.restart()
            self.timer.setInterval(33 if self.mood == 'matching' else 50)
        window=getattr(self.button,'window',None)
        choice=getattr(window,'power_saving',None)
        saving=choice is not None and choice.isChecked()
        self.timer.setInterval((66 if self.mood=='matching' else 100) if saving else (33 if self.mood=='matching' else 50))
        if self.mood == 'doze':
            self.timer.setInterval(100)   # a slow breath needs no more than 10 fps
        changed = self._advance_modifiers()
        if self.dragging:
            self.timer.setInterval(33)
        if not self.button.isVisible():
            return
        if self.cacheable and not changed:
            # Only repaint when the cached frame changes (100 ms steps).
            index = self.idle_frame_index()
            if index == self._idle_index:
                return
            self._idle_index = index
        else:
            self._idle_index = None
        self.button.update()

    def _advance_modifiers(self):
        """Ease the runtime modifiers one step; True when something moved."""
        before = (round(self.look_current,2), round(self.opacity,3),
                  round(self.drag_swing,1), round(self.drag_lean,1), round(self.drag_lift,2))
        self.look_current += (self.look-self.look_current)*.22
        if abs(self.look_current-self.look) < .05:
            self.look_current = self.look
        self.opacity += (self.opacity_target-self.opacity)*.12
        if abs(self.opacity-self.opacity_target) < .005:
            self.opacity = self.opacity_target
        # Limbs trail the hand: a spring towards the velocity-driven target,
        # which relaxes to zero once the doll is set down.
        target = max(-26., min(26., -self.drag_velocity*1.6)) if self.dragging else 0.
        self.drag_swing += (target-self.drag_swing)*.28
        self.drag_lean += (target*.45-self.drag_lean)*.22
        self.drag_lift += ((1. if self.dragging else 0.)-self.drag_lift)*.2
        if not self.dragging:
            self.drag_velocity *= .6
            if abs(self.drag_swing) < .3 and abs(self.drag_lean) < .3 and self.drag_lift < .01:
                self.drag_swing = self.drag_lean = self.drag_lift = 0.
        after = (round(self.look_current,2), round(self.opacity,3),
                 round(self.drag_swing,1), round(self.drag_lean,1), round(self.drag_lift,2))
        return before != after

    @property
    def modified(self):
        """A pose modifier is active: a cached frame would be wrong.

        Opacity is not one: a steady fade is baked into the cache key instead,
        so a faded idle doll still blits frames rather than re-rendering.
        """
        return (self.look_current != 0. or self.dragging
                or self.drag_swing != 0. or self.drag_lean != 0. or self.drag_lift != 0.
                or self.blending)

    @property
    def blending(self):
        """First 400 ms of a looping pose that does not start at rest."""
        return (self.looping and self.mood != 'matching' and self.since_play.isValid()
                and self.since_play.elapsed() < 400)

    # Deterministic loops whose frames can be rendered once and reused.
    CACHED_MOODS = ('idle', 'doze')

    @property
    def cacheable(self):
        return self.mood in self.CACHED_MOODS and not self.modified and self.timer.isActive()

    def idle_frame_index(self):
        return int(self.clock.elapsed()/self.duration*self.IDLE_FRAMES) % self.IDLE_FRAMES

    @property
    def duration(self):
        return 3000 if self.mood == 'idle' else getattr(self.skin,'DURATIONS',{}).get(self.mood,2200)

    # ── drag hooks (called by the button) ──────────────────────
    def begin_drag(self):
        self.dragging = True
        self.drag_velocity = 0.
        if self.enabled and self.timer.isActive():
            self.timer.setInterval(33)

    def drag_moved(self, dx_per_ms):
        # Smoothed horizontal speed in px/ms; a flick reads as a swing.
        self.drag_velocity = self.drag_velocity*.5 + dx_per_ms*.5

    def end_drag(self):
        if not self.dragging:
            return
        self.dragging = False
        if self.enabled and self.mood == 'idle':
            self.play('land')

    # ── painting ───────────────────────────────────────────────
    def paint(self, progress=None, render_scale=None, origin=None):
        render_scale = self.render_scale if render_scale is None else render_scale
        if origin is None:
            origin = self.origin_for(self.button.width(), self.button.height())
        if progress is None and self.cacheable:
            index = self.idle_frame_index()
            dpr = self.button.devicePixelRatioF()
            key = (self.mood, index, round(self.opacity, 2), render_scale, tuple(origin),
                   self.button.width(), self.button.height(), dpr)
            frame = self._idle_cache.get(key)
            if frame is None:
                frame = G.QPixmap(int(self.button.width()*dpr), int(self.button.height()*dpr))
                frame.setDevicePixelRatio(dpr)
                frame.fill(C.Qt.transparent)
                self._paint_on(frame, (index+.5)/self.IDLE_FRAMES, render_scale, origin)
                if len(self._idle_cache) >= 4*self.IDLE_FRAMES:
                    self._idle_cache.clear()   # size, DPI or fade changed a lot; start over
                self._idle_cache[key] = frame
            p = G.QPainter(self.button)
            p.drawPixmap(0, 0, frame)
            p.end()
            return
        t = progress if progress is not None else (self.clock.elapsed()/self.duration if self.timer.isActive() else 1)
        self._paint_on(self.button, t, render_scale, origin)

    def _paint_on(self, device, t, render_scale=.32, origin=(7,20)):
        p = G.QPainter(device)
        p.setRenderHints(G.QPainter.Antialiasing | G.QPainter.SmoothPixmapTransform)
        if self.opacity < 1.:
            p.setOpacity(self.opacity)
        angles, ease = self.skin.pose(self.mood, t)
        if self.mood == 'curious' and self.wave_right:
            for part_name in ('upper', 'lower', 'leg'):
                left, right = 'left_'+part_name, 'right_'+part_name
                angles[left], angles[right] = -angles[right], -angles[left]
            angles['head'] *= -1
        motion = self.skin.body_motion(self.mood,t) if hasattr(self.skin,'body_motion') else dict(x=0,y=0,torso=0,squash=0)
        # A looping pose (doze) does not start at rest: blend it in over 400 ms.
        if self.blending:
            blend = min(1., self.since_play.elapsed()/400)
            angles = {k: v*blend for k, v in angles.items()}
            motion = {k: v*blend for k, v in motion.items()}
        # Runtime modifiers on top of the skin's pose.
        angles['head'] += self.look_current + self.drag_lean*.6
        motion = dict(motion)
        motion['torso'] += self.drag_lean
        for limb, sign in (('left_upper', 1), ('right_upper', 1), ('left_leg', 1), ('right_leg', 1)):
            angles[limb] += self.drag_swing*sign
        for limb in ('left_lower', 'right_lower'):
            angles[limb] += self.drag_swing*.5
        # Carried by the head: arms rise a little, legs hang straighter.
        angles['left_upper'] += 18*self.drag_lift
        angles['right_upper'] -= 18*self.drag_lift
        motion['y'] -= 6*self.drag_lift
        # Leave headroom inside the existing widget for the upward float.
        p.translate(*origin)
        p.scale(render_scale, render_scale)
        if self.shadow:
            # Contact shadow under the feet: shrinks and fades as the doll
            # lifts, which is what makes the jumps read as jumps.
            lift = min(1., max(0., -motion['y']/90)) if motion['y'] < 0 else 0.
            lift = max(lift, self.drag_lift)
            p.save()
            p.setPen(C.Qt.NoPen)
            p.setBrush(G.QColor(0, 0, 0, int(58*(1-lift*.85))))
            p.drawEllipse(C.QPointF(153+motion['x']*.4, 325), 48*(1-lift*.4), 9*(1-lift*.4))
            p.restore()
        p.translate(motion['x'],motion['y'])
        p.translate(153,228)
        p.scale(1+motion['squash'],1-motion['squash'])
        p.translate(-153,-228)

        def part(name, pivot, angle):
            p.save()
            p.translate(*pivot)
            p.rotate(angle)
            p.translate(-pivot[0], -pivot[1])
            p.drawPixmap(0, 0, self.layers[name])
            p.restore()

        def arm(side, shoulder, elbow):
            # Integrate a distributed bend along the whole fabric arm.
            # Small overlapping texture strips follow its smooth tangent.
            start=135.;end=242.;step=2.
            slope=(elbow[0]-shoulder[0])/(elbow[1]-shoulder[1])
            x=shoulder[0]+(start-shoulder[1])*slope;y=start
            base=math.radians(angles[side+'_upper'])
            dx=shoulder[0]+(x-shoulder[0])*math.cos(base)-(y-shoulder[1])*math.sin(base)
            dy=shoulder[1]+(x-shoulder[0])*math.sin(base)+(y-shoulder[1])*math.cos(base)
            while y<end:
                length=min(step,end-y)
                u=max(0.,min(1.,(y+length/2-shoulder[1])/(end-shoulder[1])))
                angle=base+math.radians(angles[side+'_lower'])*u*u*(3-2*u)
                co,si=math.cos(angle),math.sin(angle)
                p.save()
                p.setTransform(G.QTransform(co,si,-si,co,dx-co*x+si*y,dy-si*x-co*y),True)
                rect=C.QRectF(0,y,306,length+.35)
                p.drawPixmap(rect,self.layers[side+'_arm'],rect)
                p.restore()
                dx+=length*(slope*co-si);dy+=length*(slope*si+co)
                x+=length*slope;y+=length

        def curved_limb(name, start, end, controls, weight, foreshorten=1.):
            # Warp the entire texture along a smooth curve, including legs.
            sx,sy=start;ex,ey=end
            slope=(ex-sx)/(ey-sy)
            def raw_point(u):
                v=1-u
                qx=v**3*sx+3*v*v*u*controls[0][0]+3*v*u*u*controls[1][0]+u**3*controls[2][0]
                qy=v**3*sy+3*v*v*u*controls[0][1]+3*v*u*u*controls[1][1]+u**3*controls[2][1]
                return ((1-weight)*(sx+(ex-sx)*u)+weight*qx,
                        (1-weight)*(sy+(ey-sy)*u)+weight*qy)
            # Equal arc-length sampling: bending must not stretch the cloth.
            samples=np.array([raw_point(u) for u in np.linspace(0,1,161)])
            distances=np.r_[0,np.cumsum(np.linalg.norm(np.diff(samples,axis=0),axis=1))]
            total=max(float(distances[-1]),1e-6)
            visible_length=math.hypot(ex-sx,ey-sy)*(1-weight*(1-foreshorten))
            samples=np.array(start)+(samples-np.array(start))*visible_length/total
            fractions=distances/total
            def point(u):
                if u<0:
                    return samples[0]+(samples[1]-samples[0])*u/fractions[1]
                if u>1:
                    return samples[-1]+(samples[-1]-samples[-2])*(u-1)/(1-fractions[-2])
                return np.array([np.interp(u,fractions,samples[:,k]) for k in (0,1)])
            for row in range(int(sy)-12,int(ey)+3,2):
                u=(row-sy)/(ey-sy)
                x=sx+slope*(row-sy)
                qx,qy=point(u);nx,ny=point(u+.001)
                vx=(nx-qx)/(.001*(ey-sy));vy=(ny-qy)/(.001*(ey-sy))
                angle=math.atan2(vy,vx)-math.atan2(1,slope)
                co,si=math.cos(angle),math.sin(angle)
                b=vx-slope*co;d=vy-slope*si
                p.save()
                p.setTransform(G.QTransform(co,si,b,d,qx-co*x-b*row,qy-si*x-d*row),True)
                rect=C.QRectF(0,row,306,2.25)
                p.drawPixmap(rect,self.layers[name],rect);p.restore()

        def folded_arm(side, weight):
            shoulder=self.skin.PIVOTS[side+'_shoulder']
            elbow=self.skin.PIVOTS[side+'_elbow']
            # Fold back over the upper arm, rather than drawing a U silhouette.
            upper=(22 if side=='left' else -22)*weight
            radians=math.radians(upper)
            vx,vy=elbow[0]-shoulder[0],elbow[1]-shoulder[1]
            ex=shoulder[0]+vx*math.cos(radians)-vy*math.sin(radians)
            ey=shoulder[1]+vx*math.sin(radians)+vy*math.cos(radians)
            p.save()
            # The tucked upper arm is behind the forearm in this frontal view.
            p.setOpacity(p.opacity()*(1-weight))
            part(side+'_upper',shoulder,upper)
            p.restore()
            p.save();p.translate(ex-elbow[0],ey-elbow[1])
            part(side+'_lower',elbow,(-170 if side=='left' else 170)*weight)
            p.restore()

        cuddling=self.mood in ('heart','happy')
        if cuddling:
            left_weight,right_weight=self.skin.leg_weights(t) if hasattr(self.skin,'leg_weights') else (ease,ease)
            curved_limb('left_leg',(119,228),(128,317),((136,253),(153,278),(170,303)),left_weight)
            curved_limb('right_leg',(182,228),(162,317),((225,250),(202,269),(173,262)),right_weight,foreshorten=.70)
        else:
            part('left_leg', self.skin.PIVOTS["left_leg"], angles['left_leg'])
            part('right_leg', self.skin.PIVOTS["right_leg"], angles['right_leg'])
        p.save()
        p.translate(153,228)
        p.rotate(motion['torso'])
        p.translate(-153,-228)
        p.drawPixmap(0, 0, self.layers['body'])
        part('head', self.skin.PIVOTS["head"], angles['head'])
        if cuddling:
            folded_arm('left',ease)
            folded_arm('right',ease)
        else:
            arm('left', self.skin.PIVOTS["left_shoulder"], self.skin.PIVOTS["left_elbow"])
            arm('right', self.skin.PIVOTS["right_shoulder"], self.skin.PIVOTS["right_elbow"])
        p.restore()
        if hasattr(self.skin,'paint_effects'):
            avoid = 'right' if self.look > 0 else 'left' if self.look < 0 else None
            self.skin.paint_effects(p,self.mood,t,self.duration,
                                    effect_scale=render_scale/.32, avoid=avoid)
        p.end()
