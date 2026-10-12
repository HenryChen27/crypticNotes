package com.crypticnotes.mobile;

import android.app.*;
import android.os.IBinder;
import android.content.Intent;
import android.provider.Settings;
import android.content.res.Configuration;
import android.net.Uri;
import android.util.AtomicFile;
import android.view.*;
import android.webkit.*;
import android.widget.*;
import org.json.JSONObject;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Local-only WebView host, with atomic saves outside the game package. */
public class MiniGameOverlayService extends Service {
    private WebView web;
    private File root;
    private AtomicFile save;
    private boolean closing;
    static volatile boolean running;
    static volatile boolean hidden;
    static MiniGameOverlayService current;
    private final Runnable autoClose=()->{if(hidden)saveAndClose();};
    private int barHeight;
    private WindowManager windows;
    private WindowManager.LayoutParams params;
    private LinearLayout shell;
    private android.content.BroadcastReceiver screenReceiver;
    private boolean fullScreen;
    private int customWidth;
    private android.graphics.Rect restoredBounds;
    private final android.os.Handler handler=new android.os.Handler(android.os.Looper.getMainLooper());
    private final Runnable saveTimeout=()->{closing=false;showGame();Toast.makeText(this,"保存超时，请重试",Toast.LENGTH_LONG).show();};
    @Override public IBinder onBind(Intent intent){return null;}
    void runOnUiThread(Runnable action){new android.os.Handler(android.os.Looper.getMainLooper()).post(action);}
    @Override public int onStartCommand(Intent intent,int flags,int id){if(intent!=null){if("show".equals(intent.getAction()))showGame();else if("auto-hide".equals(intent.getAction())&&!hidden){hideGame();handler.postDelayed(autoClose,5000);}}return START_NOT_STICKY;}
    @Override public void onCreate(){
        super.onCreate();
        current=this;running=true;hidden=false;barHeight=Theme.px(this,30);
        NotificationManager manager=getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel("mini-game","小游戏",NotificationManager.IMPORTANCE_LOW));
        startForeground(1907,new Notification.Builder(this,"mini-game").setSmallIcon(android.R.drawable.ic_media_play).setContentTitle("合成大水母正在运行").setContentText("可在悬浮窗口中暂停、保存并退出").setContentIntent(PendingIntent.getForegroundService(this,0,new Intent(this,MiniGameOverlayService.class).setAction("show"),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE)).setOngoing(true).build());
        MiniGameStore store=new MiniGameStore(this);if(!store.installed()||!Settings.canDrawOverlays(this)){stopSelf();return;}
        root=new File(store.game,"game");File folder=new File(getFilesDir(),"minigame-saves/jellyfish");folder.mkdirs();save=new AtomicFile(new File(folder,"local-storage.json"));
        shell=new LinearLayout(this);shell.setOrientation(1);shell.setBackgroundColor(0xff182430);
        LinearLayout bar=new LinearLayout(this);bar.setGravity(Gravity.CENTER_VERTICAL);
        TextView title=new TextView(this);title.setText("合成大水母");title.setTextColor(Theme.TITLE);title.setPadding(12,0,0,0);bar.addView(title,new LinearLayout.LayoutParams(0,barHeight,1));
        ControlIcon full=new ControlIcon(1);bar.addView(full,new LinearLayout.LayoutParams(Theme.px(this,34),barHeight));
        full.setOnClickListener(v->{
            if(!fullScreen)restoredBounds=new android.graphics.Rect(params.x,params.y,params.x+params.width,params.y+params.height);
            fullScreen=!fullScreen;full.invalidate();resize();
            if(!fullScreen&&restoredBounds!=null){params.x=restoredBounds.left;params.y=restoredBounds.top;clampPosition();}
            windows.updateViewLayout(shell,params);
        });
        ControlIcon hide=new ControlIcon(0);bar.addView(hide,new LinearLayout.LayoutParams(Theme.px(this,34),barHeight));hide.setOnClickListener(v->hideGame());
        ControlIcon close=new ControlIcon(2);bar.addView(close,new LinearLayout.LayoutParams(Theme.px(this,34),barHeight));close.setOnClickListener(v->saveAndClose());shell.addView(bar);
        web=new WebView(this);
        FrameLayout viewport=new FrameLayout(this);viewport.addView(web,new FrameLayout.LayoutParams(-1,-1));
        View grip=new View(this){private final android.graphics.Paint paint=new android.graphics.Paint(3);
            @Override protected void onDraw(android.graphics.Canvas c){paint.setColor(0xffa8bfce);paint.setStrokeWidth(Theme.px(getContext(),1.5f));float d=Theme.px(getContext(),6);c.drawLine(getWidth()-3*d,getHeight()-d,getWidth()-d,getHeight()-3*d,paint);c.drawLine(getWidth()-2*d,getHeight()-d,getWidth()-d,getHeight()-2*d,paint);}};
        FrameLayout.LayoutParams gripParams=new FrameLayout.LayoutParams(Theme.px(this,28),Theme.px(this,28),Gravity.BOTTOM|Gravity.RIGHT);viewport.addView(grip,gripParams);
        grip.setContentDescription("拖动缩放游戏窗口");
        grip.setOnTouchListener(new View.OnTouchListener(){float x;int initial;
            public boolean onTouch(View v,MotionEvent e){if(fullScreen)return false;
                if(e.getActionMasked()==MotionEvent.ACTION_DOWN){x=e.getRawX();initial=params.width;}
                else if(e.getActionMasked()==MotionEvent.ACTION_MOVE){customWidth=initial+Math.round(e.getRawX()-x);int px=params.x,py=params.y;resize();params.x=px;params.y=py;clampPosition();windows.updateViewLayout(shell,params);}return true;}});
        shell.addView(viewport,new LinearLayout.LayoutParams(-1,0,1));
        windows=(WindowManager)getSystemService(WINDOW_SERVICE);
        params=new WindowManager.LayoutParams(1,1,WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS | WindowManager.LayoutParams.FLAG_FULLSCREEN,android.graphics.PixelFormat.TRANSLUCENT);
        params.gravity=Gravity.TOP|Gravity.LEFT;if(android.os.Build.VERSION.SDK_INT>=28)params.layoutInDisplayCutoutMode=WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;resize();windows.addView(shell,params);
        title.setOnTouchListener(new View.OnTouchListener(){float x,y;int sx,sy;
            public boolean onTouch(View v,MotionEvent e){if(e.getActionMasked()==MotionEvent.ACTION_DOWN){x=e.getRawX();y=e.getRawY();sx=params.x;sy=params.y;}
                else if(e.getActionMasked()==MotionEvent.ACTION_MOVE && !fullScreen){params.x=sx+Math.round(e.getRawX()-x);params.y=sy+Math.round(e.getRawY()-y);clampPosition();windows.updateViewLayout(shell,params);}return true;}
        });
        WebSettings s=web.getSettings();s.setJavaScriptEnabled(true);s.setDomStorageEnabled(true);s.setAllowFileAccess(false);s.setAllowContentAccess(false);s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);s.setMediaPlaybackRequiresUserGesture(false);s.setSupportMultipleWindows(false);
        web.addJavascriptInterface(new Bridge(),"NativeGame");
        web.setOnKeyListener((v,key,event)->{if(key==KeyEvent.KEYCODE_BACK){if(event.getAction()==KeyEvent.ACTION_UP)hideGame();return true;}return false;});
        web.setWebChromeClient(new WebChromeClient(){
            @Override public boolean onJsConfirm(WebView view,String url,String message,JsResult result){
                AlertDialog dialog=new AlertDialog.Builder(MiniGameOverlayService.this).setMessage(message).setPositiveButton("确定",(d,w)->result.confirm()).setNegativeButton("取消",(d,w)->result.cancel()).setOnCancelListener(d->result.cancel()).create();
                dialog.getWindow().setType(WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY);dialog.show();return true;
            }
        });
        web.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest req){return !local(req.getUrl());}
            @Override public WebResourceResponse shouldInterceptRequest(WebView view,WebResourceRequest req){
                try{
                    Uri uri=req.getUrl();if(!local(uri))return blocked();
                    File f=new File(root,uri.getPath().substring(1));if(!f.getCanonicalPath().startsWith(root.getCanonicalPath()+File.separator)||!f.isFile())return blocked();
                    if(f.getName().equals("index.html")){
                        String page=MiniGameStore.read(f),saved="{}";
                        try(InputStream in=save.openRead()){saved=new String(MiniGameStore.bytes(in,1024*1024),StandardCharsets.UTF_8);}catch(IOException ignored){}
                        String script="<script>try{Object.entries(JSON.parse("+JSONObject.quote(saved)+")).forEach(([k,v])=>localStorage.setItem(k,v))}catch(e){}</script>";
                        try(InputStream audio=getAssets().open("host-audio.js")){script+="<script>"+new String(MiniGameStore.bytes(audio,64*1024),StandardCharsets.UTF_8)+"</script>";}
                        try(InputStream bridge=getAssets().open("safe-exit.js")){script+="<script>window.__jellyfishHostPost=m=>NativeGame.safeExit(JSON.stringify(m));"+new String(MiniGameStore.bytes(bridge,64*1024),StandardCharsets.UTF_8)+"</script>";}
                        page=page.replace("<head>","<head><meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'self' data: blob:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-src 'none'; object-src 'none'\">"+script);
                        return new WebResourceResponse("text/html","UTF-8",new ByteArrayInputStream(page.getBytes(StandardCharsets.UTF_8)));
                    }
                    String name=f.getName().toLowerCase(Locale.ROOT),mime=java.net.URLConnection.guessContentTypeFromName(name);
                    if(name.endsWith(".js"))mime="application/javascript";else if(name.endsWith(".css"))mime="text/css";else if(name.endsWith(".ttf"))mime="font/ttf";
                    return new WebResourceResponse(mime==null?"application/octet-stream":mime,null,new FileInputStream(f));
                }catch(Exception e){return blocked();}
            }
            @Override public void onPageFinished(WebView view,String url){setHostMuted(hidden);}
            @Override public void onReceivedError(WebView view,WebResourceRequest request,WebResourceError error){if(request.isForMainFrame())Toast.makeText(MiniGameOverlayService.this,"游戏加载失败："+error.getDescription(),Toast.LENGTH_LONG).show();}
        });web.loadUrl("https://minigame.local/index.html");
        screenReceiver=new android.content.BroadcastReceiver(){public void onReceive(android.content.Context c,Intent i){
            if(web!=null)saveAndClose();
        }};
        registerReceiver(screenReceiver,new android.content.IntentFilter(Intent.ACTION_SCREEN_OFF));
    }
    static boolean local(Uri uri){return "https".equals(uri.getScheme())&&"minigame.local".equals(uri.getHost());}
    final class ControlIcon extends View {
        final int kind;final android.graphics.Paint paint=new android.graphics.Paint(3);
        ControlIcon(int kind){super(MiniGameOverlayService.this);this.kind=kind;setContentDescription(kind==0?"隐藏":kind==1?"全屏或恢复窗口":"保存并关闭");}
        @Override protected void onDraw(android.graphics.Canvas c){super.onDraw(c);float unit=getResources().getDisplayMetrics().density,x=getWidth()/2f,y=getHeight()/2f;paint.setColor(Theme.TITLE);paint.setStrokeWidth(1.5f*unit);
            if(kind==0)c.drawLine(x-6*unit,y,x+6*unit,y,paint);
            else if(kind==2){c.drawLine(x-5*unit,y-5*unit,x+5*unit,y+5*unit,paint);c.drawLine(x-5*unit,y+5*unit,x+5*unit,y-5*unit,paint);}
            else for(int sx:new int[]{-1,1})for(int sy:new int[]{-1,1}){float a=(fullScreen?7:2)*unit,b=(fullScreen?2:7)*unit,d=(fullScreen?1:-1)*unit,tx=x+sx*b,ty=y+sy*b;c.drawLine(x+sx*a,y+sy*a,tx,ty,paint);c.drawLine(tx,ty,tx+sx*d*4,ty,paint);c.drawLine(tx,ty,tx,ty+sy*d*4,paint);}
        }
    }
    static WebResourceResponse blocked(){return new WebResourceResponse("text/plain","UTF-8",403,"Blocked",Collections.emptyMap(),new ByteArrayInputStream(new byte[0]));}
    void resize(){
        android.util.DisplayMetrics m=new android.util.DisplayMetrics();
        windows.getDefaultDisplay().getRealMetrics(m);
        int width=Math.min((int)(m.widthPixels*.90),(int)((m.heightPixels*.85-barHeight)*2559/1441));
        int maxWidth=Math.min(m.widthPixels,(int)((m.heightPixels-barHeight)*2559.0/1441));
        params.width=fullScreen?m.widthPixels:Math.max(Math.min(Theme.px(this,200),maxWidth),Math.min(maxWidth,customWidth>0?customWidth:width));
        params.height=fullScreen?m.heightPixels:(int)(params.width*1441.0/2559)+barHeight;
        params.x=fullScreen?0:(m.widthPixels-params.width)/2;
        params.y=fullScreen?0:(m.heightPixels-params.height)/2;
    }
    void hideGame(){
        setHostMuted(true);
        hidden=true;
        if(shell!=null && shell.isAttachedToWindow())windows.removeViewImmediate(shell);
    }
    void showGame(){
        handler.removeCallbacks(autoClose);
        setHostMuted(false);
        hidden=false;
        if(shell!=null){
            clampPosition();shell.setVisibility(View.VISIBLE);
            if(!shell.isAttachedToWindow())windows.addView(shell,params);
        }
    }
    void setHostMuted(boolean mute){if(web!=null)web.evaluateJavascript("window.__jellyfishSetMuted&&window.__jellyfishSetMuted("+mute+")",null);}
    void clampPosition(){android.util.DisplayMetrics m=new android.util.DisplayMetrics();windows.getDefaultDisplay().getRealMetrics(m);params.x=Math.max(0,Math.min(m.widthPixels-params.width,params.x));params.y=Math.max(0,Math.min(m.heightPixels-params.height,params.y));}
    @Override public void onConfigurationChanged(Configuration c){
        super.onConfigurationChanged(c);
        if(params!=null){resize();if(shell.isAttachedToWindow())windows.updateViewLayout(shell,params);}
    }
    android.graphics.Rect visibleBounds(){
        if(hidden||shell==null||!shell.isAttachedToWindow())return new android.graphics.Rect();
        int[] location=new int[2];shell.getLocationOnScreen(location);
        return new android.graphics.Rect(location[0],location[1],location[0]+shell.getWidth(),location[1]+shell.getHeight());
    }
    private synchronized void write(String json)throws Exception{
        if(json==null||json.length()>1024*1024)throw new IOException("存档过大");JSONObject data=new JSONObject(json);Iterator<String> keys=data.keys();while(keys.hasNext()){String key=keys.next();if(!key.startsWith("jellyfish.")||!(data.get(key) instanceof String))throw new IOException("无效存档");}
        FileOutputStream out=null;try{out=save.startWrite();out.write(json.getBytes(StandardCharsets.UTF_8));save.finishWrite(out);}catch(Exception e){if(out!=null)save.failWrite(out);throw e;}
    }
    final class Bridge {
        @JavascriptInterface public void safeExit(String message){
            try{JSONObject m=new JSONObject(message);if(!"safe-exit".equals(m.optString("type")))return;
                if(!m.optBoolean("saved"))throw new IOException(m.optString("reason","保存失败"));write(m.getString("json"));
                runOnUiThread(()->{handler.removeCallbacks(saveTimeout);stopSelf();});
            }catch(Exception e){runOnUiThread(()->{handler.removeCallbacks(saveTimeout);closing=false;showGame();Toast.makeText(MiniGameOverlayService.this,"存档未完成，请重试",Toast.LENGTH_LONG).show();});}
        }
        @JavascriptInterface public String saveStorage(String json,boolean exit){
            try{write(json);if(exit)runOnUiThread(()->stopSelf());return "ok";}catch(Exception e){return "保存失败："+e.getMessage();}
        }
    }
    void saveAndClose(){
        if(closing||web==null)return;closing=true;
        handler.postDelayed(saveTimeout,10000);
        web.evaluateJavascript("window.__jellyfishHostSave(1)",null);
    }
    @Override public void onDestroy(){current=null;running=false;hidden=false;handler.removeCallbacksAndMessages(null);if(screenReceiver!=null)unregisterReceiver(screenReceiver);if(shell!=null&&shell.isAttachedToWindow())windows.removeView(shell);if(web!=null){web.removeJavascriptInterface("NativeGame");web.destroy();web=null;}super.onDestroy();}
}
