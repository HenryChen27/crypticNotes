package com.crypticnotes.mobile;
import android.content.Context;
import android.view.*;
import android.widget.LinearLayout;
/** Intercept actual drags across tabs too; normal taps still reach children. */
final class DraggableHeader extends LinearLayout {
    interface Move {void move(int dx,int dy);}
    Move mover;private float x,y,lastX,lastY;private boolean dragging;
    DraggableHeader(Context c){super(c);}
    @Override public boolean onInterceptTouchEvent(MotionEvent e){
        if(e.getActionMasked()==MotionEvent.ACTION_DOWN){x=lastX=e.getRawX();y=lastY=e.getRawY();dragging=false;}
        if(e.getActionMasked()==MotionEvent.ACTION_MOVE&&Math.hypot(e.getRawX()-x,e.getRawY()-y)>ViewConfiguration.get(getContext()).getScaledTouchSlop())dragging=true;
        return dragging;
    }
    @Override public boolean onTouchEvent(MotionEvent e){
        if(e.getActionMasked()==MotionEvent.ACTION_MOVE&&dragging&&mover!=null){mover.move(Math.round(e.getRawX()-lastX),Math.round(e.getRawY()-lastY));lastX=e.getRawX();lastY=e.getRawY();}
        if(e.getActionMasked()==MotionEvent.ACTION_UP||e.getActionMasked()==MotionEvent.ACTION_CANCEL)dragging=false;
        return true;
    }
}
