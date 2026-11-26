package com.crypticnotes.mobile;
import android.content.Context;
import android.graphics.*;
import android.view.View;

/** An icon button for the in-game PVP overlay: the picture says what it does, no caption. */
final class PvpGlyph extends View {
    /** CHECK and CROSS are bare brush marks; CLOSE is a small quiet cross; UP and DOWN are the fold triangle. */
    static final int CHECK=0,CROSS=1,CLOSE=2,UP=5,DOWN=6;
    private static final int GREEN=0xff6fd68f,RED=0xffe5645c,GOLD=0xffdcb96c,SHADE=0xaa05090d;
    private int kind;private final Paint paint=new Paint(3);
    PvpGlyph(Context c,int kind,String says){super(c);this.kind=kind;setContentDescription(says);setClickable(true);}
    void kind(int kind){this.kind=kind;invalidate();}
    private int tint=GOLD;
    /** Colour of the fold triangle. */
    void tint(int color){tint=color;invalidate();}
    @Override public boolean performClick(){TouchFeedback.click(this);return super.performClick();}

    /** One stroke of a loaded brush: a round head of width `from` thinning to a tip of width `to`. */
    private void brush(Canvas c,float x0,float y0,float x1,float y1,float from,float to){
        float dx=x1-x0,dy=y1-y0,length=(float)Math.hypot(dx,dy),nx=-dy/length,ny=dx/length;
        Path stroke=new Path();
        stroke.moveTo(x0+nx*from/2,y0+ny*from/2);stroke.lineTo(x1+nx*to/2,y1+ny*to/2);
        stroke.lineTo(x1-nx*to/2,y1-ny*to/2);stroke.lineTo(x0-nx*from/2,y0-ny*from/2);stroke.close();
        c.drawPath(stroke,paint);c.drawCircle(x0,y0,from/2,paint);c.drawCircle(x1,y1,to/2,paint);
    }
    private void mark(Canvas c){
        if(kind==CHECK){brush(c,5.2f,12.2f,10.4f,18.2f,2.4f,3.8f);brush(c,10.4f,18.2f,20.2f,4.8f,3.8f,1f);}
        else{brush(c,5.6f,5.4f,18.8f,18.8f,3.8f,1.2f);brush(c,18.6f,5.2f,5.4f,18.8f,3.8f,1.2f);}
    }
    @Override protected void onDraw(Canvas c){
        float w=getWidth(),h=getHeight(),r=Math.min(w,h)/2f;
        paint.setStyle(Paint.Style.FILL);
        if(kind==UP||kind==DOWN){
            // A bare triangle on the panel's own edge: which way the panel will go.
            float half=r*.85f,tall=r*.62f,tip=kind==UP?-tall:tall;
            Path t=new Path();t.moveTo(w/2-half,h/2-tip/2);t.lineTo(w/2+half,h/2-tip/2);t.lineTo(w/2,h/2+tip/2);t.close();
            paint.setColor(tint);c.drawPath(t,paint);
            return;
        }
        // The quiet cross stays small however large the area that takes the tap.
        if(kind==CLOSE)r=Math.min(r,Theme.px(getContext(),11));
        c.save();c.translate(w/2-r,h/2-r);c.scale(r/12f,r/12f);
        if(kind==CLOSE){
            paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(2.2f);paint.setStrokeCap(Paint.Cap.ROUND);paint.setColor(Theme.MUTED);
            c.drawLine(6.5f,6.5f,17.5f,17.5f,paint);c.drawLine(17.5f,6.5f,6.5f,17.5f,paint);
        }else{
            // No plate behind: the mark itself, with a soft dark edge so it holds on any picture.
            c.save();c.translate(.9f,1f);paint.setColor(SHADE);mark(c);c.restore();
            paint.setColor(kind==CHECK?GREEN:RED);mark(c);
        }
        c.restore();
    }
}

/** One horizontal meter: how much of the track is filled is the hunter's share. */
final class PvpBar extends View {
    private final float fill;private final Paint paint=new Paint(1);private final RectF box=new RectF();
    PvpBar(Context c,float fill){super(c);this.fill=Math.max(0,Math.min(1,fill));}
    @Override protected void onDraw(Canvas c){
        float h=getHeight(),r=h/2f;
        box.set(0,0,getWidth(),h);paint.setColor(0xb32a3f52);c.drawRoundRect(box,r,r,paint);
        // Never shorter than a dot, so a small share still reads as "some".
        box.set(0,0,Math.max(h,getWidth()*fill),h);paint.setColor(0xffdcb96c);c.drawRoundRect(box,r,r,paint);
    }
}
