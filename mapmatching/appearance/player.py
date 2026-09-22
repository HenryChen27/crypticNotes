import math
import numpy as np
from PySide6 import QtCore as C, QtGui as G
from .skins import doll

class PetAnimation:
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
        self.clock = C.QElapsedTimer()
        self.timer = C.QTimer(button)
        self.timer.setInterval(25)
        self.timer.timeout.connect(self.advance)

    def enable(self, enabled):
        self.enabled = bool(enabled and not self.pixmap.isNull())
        self.timer.stop()
        self.button.setFixedSize(112, 132) if self.enabled else self.button.setFixedSize(46, 46)
        self.button.update()

    def play(self, mood):
        if not self.enabled:
            return
        if self.timer.isActive() and self.mood == mood:
            return
        self.mood = mood
        self.clock.start()
        self.timer.start()
        self.button.update()

    def advance(self):
        if self.clock.elapsed() >= self.duration or not self.button.isVisible():
            self.timer.stop()
        self.button.update()

    @property
    def duration(self):
        return getattr(self.skin,'DURATIONS',{}).get(self.mood,2200)

    def paint(self, progress=None):
        p = G.QPainter(self.button)
        p.setRenderHints(G.QPainter.Antialiasing | G.QPainter.SmoothPixmapTransform)
        t = progress if progress is not None else (self.clock.elapsed()/self.duration if self.timer.isActive() else 1)
        angles, ease = self.skin.pose(self.mood, t)
        # Leave headroom inside the existing widget for the upward float.
        p.translate(7, 20)
        p.scale(.32, .32)
        motion = self.skin.body_motion(self.mood,t) if hasattr(self.skin,'body_motion') else dict(x=0,y=0,torso=0,squash=0)
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
            p.setOpacity(1-weight)
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
            self.skin.paint_effects(p,self.mood,t,self.duration)
        p.end()
