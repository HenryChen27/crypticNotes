package com.crypticnotes.mobile;
import android.content.Context;
import android.graphics.*;
import android.view.View;
final class HeaderClose extends View {
    private final Paint paint=new Paint(3);
    HeaderClose(Context c){super(c);setContentDescription("关闭设置");}
    @Override public boolean performClick(){TouchFeedback.click(this);return super.performClick();}
    @Override protected void onDraw(Canvas c){float x=getWidth()/2f,y=getHeight()/2f,d=Theme.px(getContext(),8);paint.setColor(0xff802020);paint.setStrokeWidth(Theme.px(getContext(),3));paint.setStrokeCap(Paint.Cap.SQUARE);c.drawLine(x-d,y-d,x+d,y+d,paint);c.drawLine(x-d,y+d,x+d,y-d,paint);}
}
