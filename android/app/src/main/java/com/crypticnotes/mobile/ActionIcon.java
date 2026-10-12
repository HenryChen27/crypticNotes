package com.crypticnotes.mobile;
import android.graphics.*;
import android.graphics.drawable.Drawable;
/** Vector controls, independent of font glyph coverage. */
final class ActionIcon extends Drawable {
    static final int GEAR=0,GAME=1,RECORD=2,STOP=3;
    private final int kind;private final Paint paint=new Paint(3);private final int color;boolean dot;
    ActionIcon(int kind,int color){this.kind=kind;this.color=color;}
    @Override public void draw(Canvas c){
        c.save();c.translate(getBounds().left,getBounds().top);c.scale(getBounds().width()/24f,getBounds().height()/24f);
        paint.setColor(color);paint.setStrokeWidth(1.6f);paint.setStyle(Paint.Style.STROKE);paint.setStrokeCap(Paint.Cap.ROUND);
        if(kind==GEAR){c.drawCircle(12,12,7,paint);c.drawCircle(12,12,2.5f,paint);for(int i=0;i<8;i++){c.save();c.rotate(i*45,12,12);c.drawLine(12,2,12,5,paint);c.restore();}}
        else if(kind==GAME){c.drawRoundRect(2,6,22,19,4,4,paint);c.drawLine(5,12,11,12,paint);c.drawLine(8,9,8,15,paint);paint.setStyle(Paint.Style.FILL);c.drawCircle(16,10,1.1f,paint);c.drawCircle(19,14,1.1f,paint);}
        else {c.drawCircle(12,12,9,paint);paint.setStyle(Paint.Style.FILL);if(kind==RECORD)c.drawCircle(12,12,4.5f,paint);else c.drawRect(7.5f,7.5f,16.5f,16.5f,paint);}
        if(dot){paint.setStyle(Paint.Style.FILL);paint.setColor(0xffd97977);c.drawCircle(21,3,3,paint);}c.restore();
    }
    @Override public void setAlpha(int a){paint.setAlpha(a);}
    @Override public void setColorFilter(ColorFilter f){paint.setColorFilter(f);}
    @Override public int getOpacity(){return PixelFormat.TRANSLUCENT;}
    static void set(android.widget.TextView view,int kind,boolean dot){ActionIcon icon=new ActionIcon(kind,view.getCurrentTextColor());icon.dot=dot;int size=Theme.px(view.getContext(),20);icon.setBounds(0,0,size,size);view.setCompoundDrawables(icon,null,null,null);view.setCompoundDrawablePadding(Theme.px(view.getContext(),6));}
}
