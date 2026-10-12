package com.crypticnotes.mobile;
import android.content.Context;
import android.graphics.*;
import android.graphics.drawable.GradientDrawable;
import android.view.*;
import android.widget.*;
/** Translucent gestures over the game itself; no title bar or extra frame. */
final class GameWindowChrome extends FrameLayout {
    interface Host {boolean fullscreen();void move(int dx,int dy);void scale(int delta,boolean left);void minimize();void toggleFull();void close();}
    private final Host host;
    private final View bottom,left,right;
    private final LinearLayout menu;
    private final int slop;
    GameWindowChrome(Context c,View game,Host host){
        super(c);this.host=host;slop=ViewConfiguration.get(c).getScaledTouchSlop();addView(game,new LayoutParams(-1,-1));
        setClipToOutline(true);setOutlineProvider(new ViewOutlineProvider(){@Override public void getOutline(View v,Outline outline){outline.setRoundRect(0,0,getWidth(),getHeight(),host.fullscreen()?0:dp(12));}});
        View dots=new Mark(c,0);dots.setContentDescription("游戏窗口操作，长按拖动");LayoutParams dotParams=new LayoutParams(dp(56),dp(30),Gravity.TOP|Gravity.CENTER_HORIZONTAL);dotParams.topMargin=dp(3);addView(dots,dotParams);
        dots.setOnTouchListener(new View.OnTouchListener(){float x,y,lastX,lastY;boolean dragging,held,moved;
            final Runnable hold=()->{held=true;dragging=!host.fullscreen();};
            public boolean onTouch(View v,MotionEvent e){switch(e.getActionMasked()){
                case MotionEvent.ACTION_DOWN:x=lastX=e.getRawX();y=lastY=e.getRawY();dragging=held=moved=false;postDelayed(hold,ViewConfiguration.getLongPressTimeout());return true;
                case MotionEvent.ACTION_MOVE:if(Math.hypot(e.getRawX()-x,e.getRawY()-y)>slop){moved=true;if(!held)removeCallbacks(hold);}if(dragging){host.move(Math.round(e.getRawX()-lastX),Math.round(e.getRawY()-lastY));lastX=e.getRawX();lastY=e.getRawY();}return true;
                case MotionEvent.ACTION_UP:removeCallbacks(hold);if(!held&&!moved)toggleMenu();dragging=false;return true;
                case MotionEvent.ACTION_CANCEL:removeCallbacks(hold);dragging=false;return true;
            }return true;}
        });
        bottom=new Mark(c,1);bottom.setContentDescription("向上滑动最小化，向下滑动全屏");addView(bottom,new LayoutParams(dp(120),dp(28),Gravity.BOTTOM|Gravity.CENTER_HORIZONTAL));
        bottom.setOnTouchListener(new View.OnTouchListener(){float y;public boolean onTouch(View v,MotionEvent e){if(e.getActionMasked()==MotionEvent.ACTION_DOWN)y=e.getRawY();if(e.getActionMasked()==MotionEvent.ACTION_UP){float delta=e.getRawY()-y;if(delta<-dp(20))host.minimize();else if(delta>dp(20)&&!host.fullscreen())host.toggleFull();}return true;}});
        left=new Mark(c,2);right=new Mark(c,3);addView(left,new LayoutParams(dp(36),dp(36),Gravity.BOTTOM|Gravity.LEFT));addView(right,new LayoutParams(dp(36),dp(36),Gravity.BOTTOM|Gravity.RIGHT));
        resizeTouch(left,true);resizeTouch(right,false);
        menu=new LinearLayout(c);menu.setGravity(Gravity.CENTER);GradientDrawable bg=new GradientDrawable();bg.setColor(0xd922303e);bg.setCornerRadius(dp(9));menu.setBackground(bg);menu.setElevation(dp(5));LayoutParams mp=new LayoutParams(-2,dp(42),Gravity.TOP|Gravity.CENTER_HORIZONTAL);mp.topMargin=dp(36);addView(menu,mp);menu.setVisibility(GONE);
        updateMode();
    }
    private int dp(float n){return Theme.px(getContext(),n);}
    private void resizeTouch(View view,boolean left){view.setContentDescription("拖动等比例缩放");view.setOnTouchListener(new View.OnTouchListener(){float x,y;public boolean onTouch(View v,MotionEvent e){
        if(e.getActionMasked()==MotionEvent.ACTION_DOWN){x=e.getRawX();y=e.getRawY();}
        else if(e.getActionMasked()==MotionEvent.ACTION_MOVE){float dx=(e.getRawX()-x)*(left?-1:1),dy=(e.getRawY()-y)*(float)GameWindowGeometry.RATIO;host.scale(Math.round(Math.abs(dx)>Math.abs(dy)?dx:dy),left);x=e.getRawX();y=e.getRawY();}return true;}});}
    void updateMode(){boolean full=host.fullscreen();bottom.setVisibility(full?GONE:VISIBLE);left.setVisibility(full?GONE:VISIBLE);right.setVisibility(full?GONE:VISIBLE);menu.setVisibility(GONE);invalidateOutline();}
    void dismissMenu(){menu.setVisibility(GONE);}
    private void toggleMenu(){if(menu.getVisibility()==VISIBLE){dismissMenu();return;}menu.removeAllViews();addOption(0,"最小化",host::minimize);addOption(1,host.fullscreen()?"恢复小窗":"全屏",host::toggleFull);if(host.fullscreen())addOption(2,"保存并关闭",host::close);menu.setVisibility(VISIBLE);}
    private void addOption(int kind,String description,Runnable action){View option=new Mark(getContext(),kind+4);option.setContentDescription(description);option.setOnClickListener(v->{dismissMenu();action.run();});menu.addView(option,new LinearLayout.LayoutParams(dp(44),-1));}
    final class Mark extends View {
        final int kind;final Paint p=new Paint(3);Mark(Context c,int kind){super(c);this.kind=kind;}
        @Override protected void onDraw(Canvas c){float x=getWidth()/2f,y=getHeight()/2f,u=getResources().getDisplayMetrics().density;p.setColor(0x95d1dce3);p.setStrokeWidth(1.7f*u);p.setStrokeCap(Paint.Cap.ROUND);p.setStyle(Paint.Style.STROKE);
            if(kind==0){p.setStyle(Paint.Style.FILL);for(int i=-1;i<=1;i++)c.drawCircle(x+i*8*u,y,2.2f*u,p);}
            else if(kind==1){p.setColor(0x70d1dce3);p.setStyle(Paint.Style.FILL);c.drawRoundRect(x-30*u,y+4*u,x+30*u,y+7*u,2*u,2*u,p);}
            else if(kind==2||kind==3){float side=kind==2?1:-1,edge=kind==2?8*u:getWidth()-8*u,b=getHeight()-8*u;Path path=new Path();path.moveTo(edge,b-13*u);path.lineTo(edge,b-5*u);path.quadTo(edge,b,edge+side*5*u,b);path.lineTo(edge+side*13*u,b);c.drawPath(path,p);}
            else if(kind==4)c.drawLine(x-6*u,y,x+6*u,y,p);
            else if(kind==6){c.drawLine(x-5*u,y-5*u,x+5*u,y+5*u,p);c.drawLine(x-5*u,y+5*u,x+5*u,y-5*u,p);}
            else for(int sx:new int[]{-1,1})for(int sy:new int[]{-1,1}){float a=(host.fullscreen()?7:2)*u,b=(host.fullscreen()?2:7)*u,d=(host.fullscreen()?1:-1)*u,tx=x+sx*b,ty=y+sy*b;c.drawLine(x+sx*a,y+sy*a,tx,ty,p);c.drawLine(tx,ty,tx+sx*d*4,ty,p);c.drawLine(tx,ty,tx,ty+sy*d*4,p);}
        }
    }
}
