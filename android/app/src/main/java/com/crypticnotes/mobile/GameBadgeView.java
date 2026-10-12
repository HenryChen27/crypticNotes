package com.crypticnotes.mobile;

import android.content.Context;
import android.graphics.*;
import android.os.SystemClock;
import android.widget.ImageView;

/** Orbit indicator for the mobile emblem; stays inside its touch bounds. */
final class GameBadgeView extends ImageView {
    final Paint ink=new Paint(Paint.ANTI_ALIAS_FLAG);
    GameBadgeView(Context context){super(context);}
    PointF orbit(){double angle=SystemClock.elapsedRealtime()/3200.0*Math.PI*2;float r=Math.min(getWidth(),getHeight())*.34f;return new PointF(getWidth()/2f+(float)Math.cos(angle)*r,getHeight()/2f+(float)Math.sin(angle)*r);}
    boolean hit(float x,float y){PointF p=orbit();return MiniGameOverlayService.hidden&&Math.hypot(x-p.x,y-p.y)<getWidth()*.28f;}
    @Override protected void onDraw(Canvas canvas){
        if(MiniGameOverlayService.hidden){canvas.save();canvas.scale(.7f,.7f,getWidth()/2f,getHeight()/2f);canvas.rotate((SystemClock.elapsedRealtime()%1800)/5f,getWidth()/2f,getHeight()/2f);super.onDraw(canvas);canvas.restore();
            PointF p=orbit();float unit=getWidth()/44f;canvas.save();canvas.translate(p.x,p.y);canvas.scale(unit,unit);
            ink.setColor(0xff77caff);ink.setStrokeWidth(1.8f);ink.setStyle(Paint.Style.FILL);canvas.drawArc(new RectF(-7,-7,7,7),180,180,true,ink);ink.setStyle(Paint.Style.STROKE);
            for(int x:new int[]{-4,0,4}){Path path=new Path();path.moveTo(x,0);path.cubicTo(x-3,3,x+3,5,x,8);canvas.drawPath(path,ink);}canvas.restore();
        }else super.onDraw(canvas);
        postInvalidateDelayed(MiniGameOverlayService.hidden?33:300);
    }
}
