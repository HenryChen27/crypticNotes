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
        if(kind==GEAR){Path path=new Path();path.setFillType(Path.FillType.EVEN_ODD);for(int i=0;i<32;i++){double a=i*Math.PI/16;float r=(i%4==0||i%4==1)?10:7.7f;float x=12+(float)Math.cos(a)*r,y=12+(float)Math.sin(a)*r;if(i==0)path.moveTo(x,y);else path.lineTo(x,y);}path.close();path.addCircle(12,12,4.2f,Path.Direction.CW);paint.setStyle(Paint.Style.FILL);c.drawPath(path,paint);}
        else if(kind==GAME){Path path=new Path();path.setFillType(Path.FillType.EVEN_ODD);path.moveTo(6,5);path.quadTo(2,5,1,17);path.quadTo(0,23,6,18);path.lineTo(18,18);path.quadTo(24,23,23,17);path.quadTo(22,5,18,5);path.close();path.moveTo(7,8);path.lineTo(9,8);path.lineTo(9,10);path.lineTo(11,10);path.lineTo(11,12);path.lineTo(9,12);path.lineTo(9,14);path.lineTo(7,14);path.lineTo(7,12);path.lineTo(5,12);path.lineTo(5,10);path.lineTo(7,10);path.close();path.addCircle(16,10,1.2f,Path.Direction.CW);path.addCircle(19,13,1.2f,Path.Direction.CW);paint.setStyle(Paint.Style.FILL);c.drawPath(path,paint);}
        else {c.drawCircle(12,12,9,paint);paint.setStyle(Paint.Style.FILL);if(kind==RECORD)c.drawCircle(12,12,4.5f,paint);else c.drawRect(7.5f,7.5f,16.5f,16.5f,paint);}
        if(dot){paint.setStyle(Paint.Style.FILL);paint.setColor(0xffd97977);c.drawCircle(21,3,3,paint);}c.restore();
    }
    @Override public void setAlpha(int a){paint.setAlpha(a);}
    @Override public void setColorFilter(ColorFilter f){paint.setColorFilter(f);}
    @Override public int getOpacity(){return PixelFormat.TRANSLUCENT;}
    static void set(android.widget.TextView view,int kind,boolean dot){ActionIcon icon=new ActionIcon(kind,view.getCurrentTextColor());icon.dot=dot;int size=Theme.px(view.getContext(),20);icon.setBounds(0,0,size,size);view.setCompoundDrawables(icon,null,null,null);view.setCompoundDrawablePadding(Theme.px(view.getContext(),6));}
}
