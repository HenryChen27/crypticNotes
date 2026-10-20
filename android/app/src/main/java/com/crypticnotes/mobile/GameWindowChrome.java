package com.crypticnotes.mobile;
import android.content.Context;
import android.graphics.*;
import android.graphics.drawable.GradientDrawable;
import android.view.*;
import android.widget.*;
/** Translucent gestures over the game itself; no title bar or extra frame. */
final class GameWindowChrome extends FrameLayout {
    interface Host {boolean fullscreen();void move(int dx,int dy);void scale(int delta,boolean left);void finishResize();void beginSwipe();void previewSwipe(float delta);void endSwipe(int action);void minimize();void toggleFull();void close();}
    private final Host host;
    private final View bottom,left,right,dots;
    private float edgeX,edgeY;
    private boolean edgeCandidate,edgeIntercepted;
    private android.window.OnBackInvokedCallback backCallback;
    private final LinearLayout menu;
    private final int slop;
    private final View game;
    private final ImageView snapshot;
    private Bitmap previewBitmap;
    private boolean previewing;
    GameWindowChrome(Context c,View game,Host host){
        super(c);this.host=host;this.game=game;slop=ViewConfiguration.get(c).getScaledTouchSlop();addView(game,new LayoutParams(-1,-1));
        snapshot=new ImageView(c);snapshot.setScaleType(ImageView.ScaleType.FIT_XY);addView(snapshot,new LayoutParams(-1,-1));snapshot.setVisibility(GONE);
        setClipToOutline(true);setOutlineProvider(new ViewOutlineProvider(){@Override public void getOutline(View v,Outline outline){outline.setRoundRect(0,0,getWidth(),getHeight(),host.fullscreen()?0:dp(12));}});
        dots=new Mark(c,0);dots.setContentDescription("点击窗口菜单，滑动移动");LayoutParams dotParams=new LayoutParams(dp(64),dp(34),Gravity.TOP|Gravity.CENTER_HORIZONTAL);dotParams.topMargin=dp(2);addView(dots,dotParams);
        dots.setOnTouchListener(new View.OnTouchListener(){float x,y,lastX,lastY;boolean dragging,moved;
            public boolean onTouch(View v,MotionEvent e){switch(e.getActionMasked()){
                case MotionEvent.ACTION_DOWN:x=lastX=e.getRawX();y=lastY=e.getRawY();dragging=moved=false;return true;
                case MotionEvent.ACTION_MOVE:if(Math.hypot(e.getRawX()-x,e.getRawY()-y)>Math.max(dp(2),slop/2)){moved=true;if(!dragging&&!host.fullscreen()){dragging=true;dismissMenu();TouchFeedback.click(v);}}if(dragging){host.move(Math.round(e.getRawX()-lastX),Math.round(e.getRawY()-lastY));lastX=e.getRawX();lastY=e.getRawY();}return true;
                case MotionEvent.ACTION_UP:if(!moved){TouchFeedback.click(v);toggleMenu();}dragging=false;return true;
                case MotionEvent.ACTION_CANCEL:dragging=false;return true;
            }return true;}
        });
        bottom=new Mark(c,1);bottom.setContentDescription("向上滑动保存并关闭，向下滑动全屏");addView(bottom,new LayoutParams(dp(120),dp(28),Gravity.BOTTOM|Gravity.CENTER_HORIZONTAL));
        bottom.setOnTouchListener(new View.OnTouchListener(){float y;int reached,screenHeight;boolean committed;public boolean onTouch(View v,MotionEvent e){
            if(e.getActionMasked()==MotionEvent.ACTION_DOWN){y=e.getRawY();reached=0;committed=false;android.util.DisplayMetrics metrics=new android.util.DisplayMetrics();((WindowManager)getContext().getSystemService(Context.WINDOW_SERVICE)).getDefaultDisplay().getRealMetrics(metrics);screenHeight=metrics.heightPixels;dismissMenu();host.beginSwipe();}
            if(committed)return true;
            float delta=e.getRawY()-y;int action=GameWindowGeometry.swipeAction(y,e.getRawY(),screenHeight,getResources().getDisplayMetrics().density);
            if(e.getActionMasked()==MotionEvent.ACTION_MOVE){host.previewSwipe(delta);if(action!=0&&action!=reached)TouchFeedback.click(v);reached=action;
                // Commit before the system navigation area can cancel the touch.
                if(action==1){committed=true;host.endSwipe(1);return true;}
            }
            if(e.getActionMasked()==MotionEvent.ACTION_UP)host.endSwipe(action);
            if(e.getActionMasked()==MotionEvent.ACTION_CANCEL)host.endSwipe(0);return true;}});
        left=new Mark(c,2);right=new Mark(c,3);addView(left,new LayoutParams(dp(36),dp(36),Gravity.BOTTOM|Gravity.LEFT));addView(right,new LayoutParams(dp(36),dp(36),Gravity.BOTTOM|Gravity.RIGHT));
        resizeTouch(left,true);resizeTouch(right,false);
        menu=new LinearLayout(c);menu.setGravity(Gravity.CENTER);GradientDrawable bg=new GradientDrawable();bg.setColor(0xd922303e);bg.setCornerRadius(dp(9));menu.setBackground(bg);menu.setElevation(dp(5));LayoutParams mp=new LayoutParams(-2,dp(42),Gravity.TOP|Gravity.CENTER_HORIZONTAL);mp.topMargin=dp(36);addView(menu,mp);menu.setVisibility(GONE);
        updateMode();
    }
    @Override public WindowInsets onApplyWindowInsets(WindowInsets insets){
        post(this::positionMenuSafely);return super.onApplyWindowInsets(insets);
    }
    @Override protected void onSizeChanged(int w,int h,int oldw,int oldh){super.onSizeChanged(w,h,oldw,oldh);post(this::positionMenuSafely);}
    private void positionMenuSafely(){
        if(dots==null||menu==null)return;
        int top=0;
        LayoutParams d=(LayoutParams)dots.getLayoutParams(),m=(LayoutParams)menu.getLayoutParams();
        int margin=top+dp(2);if(d.topMargin!=margin){d.topMargin=margin;dots.setLayoutParams(d);}
        if(m.topMargin!=top+dp(36)){m.topMargin=top+dp(36);menu.setLayoutParams(m);}
    }
    @Override protected void onAttachedToWindow(){super.onAttachedToWindow();requestApplyInsets();post(this::applyFullscreenBars);post(this::positionMenuSafely);
        if(android.os.Build.VERSION.SDK_INT>=33&&findOnBackInvokedDispatcher()!=null){backCallback=()->{if(host.fullscreen()){dismissMenu();host.toggleFull();}else host.minimize();};findOnBackInvokedDispatcher().registerOnBackInvokedCallback(android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT,backCallback);}
    }
    private void applyFullscreenBars(){
        boolean full=host.fullscreen();
        int flags=SYSTEM_UI_FLAG_LAYOUT_STABLE;
        if(full)flags|=SYSTEM_UI_FLAG_FULLSCREEN|SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN|SYSTEM_UI_FLAG_IMMERSIVE_STICKY;
        setSystemUiVisibility(flags);
        if(android.os.Build.VERSION.SDK_INT>=30&&getWindowInsetsController()!=null){
            android.view.WindowInsetsController controller=getWindowInsetsController();
            if(full){controller.setSystemBarsBehavior(android.view.WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);controller.hide(WindowInsets.Type.statusBars());}
            else controller.show(WindowInsets.Type.statusBars());
        }
    }
    @Override public void onWindowFocusChanged(boolean focused){super.onWindowFocusChanged(focused);if(focused)post(this::applyFullscreenBars);}
    @Override protected void onDetachedFromWindow(){
        if(android.os.Build.VERSION.SDK_INT>=33&&backCallback!=null&&findOnBackInvokedDispatcher()!=null)findOnBackInvokedDispatcher().unregisterOnBackInvokedCallback(backCallback);
        backCallback=null;super.onDetachedFromWindow();
    }
    @Override public boolean onInterceptTouchEvent(MotionEvent e){
        if(e.getActionMasked()==MotionEvent.ACTION_DOWN){edgeX=e.getX();edgeY=e.getY();edgeCandidate=host.fullscreen()&&(edgeX<=dp(24)||edgeX>=getWidth()-dp(24));edgeIntercepted=false;}
        if(edgeCandidate&&e.getActionMasked()==MotionEvent.ACTION_MOVE){float dx=e.getX()-edgeX,dy=e.getY()-edgeY;boolean inward=edgeX<getWidth()/2f?dx>0:dx<0;
            if(inward&&Math.abs(dx)>=dp(48)&&Math.abs(dx)>Math.abs(dy)*1.5f){edgeIntercepted=true;return true;}}
        return super.onInterceptTouchEvent(e);
    }
    @Override public boolean onTouchEvent(MotionEvent e){
        if(edgeIntercepted){if(e.getActionMasked()==MotionEvent.ACTION_UP){edgeIntercepted=edgeCandidate=false;TouchFeedback.click(this);dismissMenu();if(host.fullscreen())host.toggleFull();}else if(e.getActionMasked()==MotionEvent.ACTION_CANCEL)edgeIntercepted=edgeCandidate=false;return true;}
        return super.onTouchEvent(e);
    }
    private int dp(float n){return Theme.px(getContext(),n);}
    private void resizeTouch(View view,boolean left){view.setContentDescription("拖动等比例缩放");view.setOnTouchListener(new View.OnTouchListener(){float x,y;public boolean onTouch(View v,MotionEvent e){
        if(e.getActionMasked()==MotionEvent.ACTION_DOWN){x=e.getRawX();y=e.getRawY();TouchFeedback.click(v);}
        else if(e.getActionMasked()==MotionEvent.ACTION_MOVE){float dx=(e.getRawX()-x)*(left?-1:1),dy=(e.getRawY()-y)*(float)GameWindowGeometry.RATIO;host.scale(Math.round(Math.abs(dx)>Math.abs(dy)?dx:dy),left);x=e.getRawX();y=e.getRawY();}
        else if(e.getActionMasked()==MotionEvent.ACTION_UP||e.getActionMasked()==MotionEvent.ACTION_CANCEL)host.finishResize();return true;}});}
    void setPreviewing(boolean value){
        if(previewing==value)return;previewing=value;
        if(value){
            try{
                if(game.getWidth()==0||game.getHeight()==0){previewing=false;return;}
                int w=Math.min(192,game.getWidth()),h=Math.max(1,Math.round(w*game.getHeight()/(float)game.getWidth()));
                previewBitmap=Bitmap.createBitmap(w,h,Bitmap.Config.ARGB_8888);Canvas canvas=new Canvas(previewBitmap);canvas.scale(w/(float)game.getWidth(),h/(float)game.getHeight());game.draw(canvas);
                blurThumbnail(previewBitmap);
                snapshot.setImageBitmap(previewBitmap);snapshot.setVisibility(VISIBLE);game.setVisibility(INVISIBLE);
                if(game instanceof android.webkit.WebView)((android.webkit.WebView)game).evaluateJavascript("window.__jellyfishHostFrozen=true",null);
            }catch(Exception e){previewing=false;snapshot.setVisibility(GONE);game.setVisibility(VISIBLE);}
        }else{
            if(game instanceof android.webkit.WebView)((android.webkit.WebView)game).evaluateJavascript("window.__jellyfishHostFrozen=false",null);
            game.setVisibility(VISIBLE);snapshot.setVisibility(GONE);snapshot.setImageDrawable(null);previewBitmap=null;
        }
    }
    private static void blurThumbnail(Bitmap bitmap){
        int w=bitmap.getWidth(),h=bitmap.getHeight();int[] src=new int[w*h],tmp=new int[w*h],out=new int[w*h];bitmap.getPixels(src,0,w,0,0,w,h);
        for(int y=0;y<h;y++)for(int x=0;x<w;x++){int r=0,g=0,b=0;for(int k=-4;k<=4;k++){int v=src[y*w+Math.max(0,Math.min(w-1,x+k))];r+=(v>>16)&255;g+=(v>>8)&255;b+=v&255;}tmp[y*w+x]=0xff000000|((r/9)<<16)|((g/9)<<8)|(b/9);}
        for(int y=0;y<h;y++)for(int x=0;x<w;x++){int r=0,g=0,b=0;for(int k=-4;k<=4;k++){int v=tmp[Math.max(0,Math.min(h-1,y+k))*w+x];r+=(v>>16)&255;g+=(v>>8)&255;b+=v&255;}out[y*w+x]=0xff000000|((r/9)<<16)|((g/9)<<8)|(b/9);}
        bitmap.setPixels(out,0,w,0,0,w,h);
    }
    void updateMode(){boolean full=host.fullscreen();bottom.setVisibility(full?GONE:VISIBLE);left.setVisibility(full?GONE:VISIBLE);right.setVisibility(full?GONE:VISIBLE);menu.setVisibility(GONE);invalidateOutline();post(this::applyFullscreenBars);post(this::positionMenuSafely);}
    void dismissMenu(){menu.setVisibility(GONE);}
    private void toggleMenu(){if(menu.getVisibility()==VISIBLE){dismissMenu();return;}menu.removeAllViews();addOption(0,"最小化",host::minimize);addOption(1,host.fullscreen()?"恢复小窗":"全屏",host::toggleFull);addOption(2,"保存并关闭",host::close);menu.setVisibility(VISIBLE);}
    private void addOption(int kind,String description,Runnable action){View option=new Mark(getContext(),kind+4);option.setContentDescription(description);option.setOnClickListener(v->{TouchFeedback.click(v);dismissMenu();action.run();});menu.addView(option,new LinearLayout.LayoutParams(dp(44),-1));}
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
