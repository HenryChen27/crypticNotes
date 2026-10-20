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
    private WindowManager windows;
    private WindowManager.LayoutParams params;
    private GameWindowChrome shell;
    // addView registers synchronously; isAttachedToWindow only becomes true
    // during the later traversal, so it cannot guard duplicate registration.
    private boolean windowRegistered;
    private android.content.BroadcastReceiver screenReceiver;
    private boolean fullScreen;
    private int customWidth;
    private android.graphics.Rect restoredBounds;
    private android.graphics.Rect swipeBounds;
    private int swipeCustomWidth;
    private float swipeDelta;
    private android.animation.ValueAnimator returnAnimator;
    private boolean layoutQueued;
    private long lastWindowMotionAt;
    private final Runnable applyLayout=()->{layoutQueued=false;if(shell!=null&&shell.isAttachedToWindow())windows.updateViewLayout(shell,params);};
    private final android.os.Handler handler=new android.os.Handler(android.os.Looper.getMainLooper());
    private final Runnable saveTimeout=()->closeFailed("保存超时");
    static String activeGameId="jellyfish";
    @Override public IBinder onBind(Intent intent){return null;}
    void applyHostSound(){if(web!=null)web.evaluateJavascript("window.__jellyfishSetMuted&&window.__jellyfishSetMuted("+(!getSharedPreferences("mobile",0).getBoolean("gameSound",true)||hidden)+")",null);}
    void runOnUiThread(Runnable action){new android.os.Handler(android.os.Looper.getMainLooper()).post(action);}
    @Override public int onStartCommand(Intent intent,int flags,int id){if(intent!=null){if("show".equals(intent.getAction()))showGame();else if("auto-hide".equals(intent.getAction())&&!hidden){hideGame();handler.postDelayed(autoClose,5000);}}return START_NOT_STICKY;}
    @Override public void onCreate(){
        super.onCreate();
        activeGameId=getSharedPreferences("mobile",0).getString("active_game","jellyfish");
        current=this;running=true;hidden=false;
        NotificationManager manager=getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel("mini-game","小游戏",NotificationManager.IMPORTANCE_LOW));
        startForeground(1907,new Notification.Builder(this,"mini-game").setSmallIcon(android.R.drawable.ic_media_play).setContentTitle("小游戏正在运行").setContentText("可在悬浮窗口中暂停、保存并退出").setContentIntent(PendingIntent.getForegroundService(this,0,new Intent(this,MiniGameOverlayService.class).setAction("show"),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE)).setOngoing(true).build());
        MiniGameStore store=new MiniGameStore(this,activeGameId);if(!store.installed()||!Settings.canDrawOverlays(this)){stopSelf();return;}
        root=new File(store.game,"game");File folder=new File(getFilesDir(),"minigame-saves/"+activeGameId);folder.mkdirs();save=new AtomicFile(new File(folder,"local-storage.json"));
        web=new WebView(this);
        web.setOverScrollMode(View.OVER_SCROLL_NEVER);
        shell=new GameWindowChrome(this,web,new GameWindowChrome.Host(){
            public boolean fullscreen(){return fullScreen;}
            public void move(int dx,int dy){if(fullScreen)return;params.x+=dx;params.y+=dy;clampPosition();queueLayout();}
            public void scale(int delta,boolean left){
                if(fullScreen)return;int right=params.x+params.width,x=params.x,y=params.y;
                shell.setPreviewing(true);customWidth=params.width+delta;resize();params.x=left?right-params.width:x;params.y=y;clampPosition();queueLayout();
            }
            public void finishResize(){shell.setPreviewing(false);}
            public void beginSwipe(){beginWindowSwipe();}
            public void previewSwipe(float delta){previewWindowSwipe(delta);}
            public void endSwipe(int action){endWindowSwipe(action);}
            public void minimize(){hideGame();}
            public void toggleFull(){toggleFullscreen();}
            public void close(){saveAndClose();}
        });
        windows=(WindowManager)getSystemService(WINDOW_SERVICE);
        params=new WindowManager.LayoutParams(1,1,WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS | WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED,android.graphics.PixelFormat.TRANSLUCENT);
        params.gravity=Gravity.TOP|Gravity.LEFT;if(android.os.Build.VERSION.SDK_INT>=28)params.layoutInDisplayCutoutMode=WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;resize();registerWindow();
        requestHighRefreshRate();
        WebSettings s=web.getSettings();s.setJavaScriptEnabled(true);s.setDomStorageEnabled(true);s.setAllowFileAccess(false);s.setAllowContentAccess(false);s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);s.setMediaPlaybackRequiresUserGesture(false);s.setSupportMultipleWindows(false);
        web.addJavascriptInterface(new Bridge(),"NativeGame");
        web.setOnKeyListener((v,key,event)->{if(key==KeyEvent.KEYCODE_BACK){if(event.getAction()==KeyEvent.ACTION_UP){if(fullScreen)toggleFullscreen();else hideGame();}return true;}return false;});
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
                        String script="<script>window.__crypticPowerSaving="+getSharedPreferences("mobile",0).getBoolean("power_saving",false)+";</script><style>*{-webkit-tap-highlight-color:transparent}html,body{overscroll-behavior:none}canvas{-webkit-user-select:none;user-select:none}</style><script>try{Object.entries(JSON.parse("+JSONObject.quote(saved)+")).forEach(([k,v])=>localStorage.setItem(k,v))}catch(e){}</script>";
                        try(InputStream audio=getAssets().open("host-audio.js")){script+="<script>"+new String(MiniGameStore.bytes(audio,64*1024),StandardCharsets.UTF_8)+"</script>";}
                        try(InputStream performance=getAssets().open("host-performance.js")){script+="<script>"+new String(MiniGameStore.bytes(performance,64*1024),StandardCharsets.UTF_8)+"</script>";}
                        try(InputStream animation=getAssets().open("host-animation-cache.js")){script+="<script>"+new String(MiniGameStore.bytes(animation,64*1024),StandardCharsets.UTF_8)+"</script>";}
                        try(InputStream bridge=getAssets().open("safe-exit.js")){script+="<script>window.__jellyfishHostPost=m=>NativeGame.safeExit(JSON.stringify(m));"+new String(MiniGameStore.bytes(bridge,64*1024),StandardCharsets.UTF_8)+"</script>";}
                        page=page.replace("<head>","<head><meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'self' data: blob:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-src 'none'; object-src 'none'\">"+script);
                        return new WebResourceResponse("text/html","UTF-8",new ByteArrayInputStream(page.getBytes(StandardCharsets.UTF_8)));
                    }
                    String name=f.getName().toLowerCase(Locale.ROOT),mime=java.net.URLConnection.guessContentTypeFromName(name);
                    if(name.endsWith(".js"))mime="application/javascript";else if(name.endsWith(".css"))mime="text/css";else if(name.endsWith(".ttf"))mime="font/ttf";
                    return new WebResourceResponse(mime==null?"application/octet-stream":mime,null,new FileInputStream(f));
                }catch(Exception e){return blocked();}
            }
            @Override public void onPageFinished(WebView view,String url){applyHostSound();setHostMuted(hidden);}
            @Override public void onReceivedError(WebView view,WebResourceRequest request,WebResourceError error){if(request.isForMainFrame())Toast.makeText(MiniGameOverlayService.this,"游戏加载失败："+error.getDescription(),Toast.LENGTH_LONG).show();}
        });web.loadUrl("https://minigame.local/index.html");
        screenReceiver=new android.content.BroadcastReceiver(){public void onReceive(android.content.Context c,Intent i){
            if(web!=null)saveAndClose();
        }};
        registerReceiver(screenReceiver,new android.content.IntentFilter(Intent.ACTION_SCREEN_OFF));
    }
    static boolean local(Uri uri){return "https".equals(uri.getScheme())&&"minigame.local".equals(uri.getHost());}
    static WebResourceResponse blocked(){return new WebResourceResponse("text/plain","UTF-8",403,"Blocked",Collections.emptyMap(),new ByteArrayInputStream(new byte[0]));}
    private void queueLayout(){
        lastWindowMotionAt=android.os.SystemClock.elapsedRealtime();
        if(!layoutQueued&&shell!=null&&shell.isAttachedToWindow()){layoutQueued=true;shell.postOnAnimation(applyLayout);}
    }
    boolean interacting(){return swipeBounds!=null||android.os.SystemClock.elapsedRealtime()-lastWindowMotionAt<750;}
    private void cancelReturn(){if(returnAnimator!=null){returnAnimator.removeAllListeners();returnAnimator.cancel();returnAnimator=null;}}
    private void restoreSwipe(){
        if(swipeBounds!=null){params.x=swipeBounds.left;params.y=swipeBounds.top;params.width=swipeBounds.width();params.height=swipeBounds.height();customWidth=swipeCustomWidth;swipeBounds=null;queueLayout();}
        shell.setPreviewing(false);
    }
    private void beginWindowSwipe(){cancelReturn();if(swipeBounds!=null)restoreSwipe();swipeBounds=new android.graphics.Rect(params.x,params.y,params.x+params.width,params.y+params.height);swipeCustomWidth=customWidth;swipeDelta=0;shell.setPreviewing(true);}
    private void previewWindowSwipe(float delta){
        if(swipeBounds==null||fullScreen)return;swipeDelta=delta;
        float progress=Math.max(-1,Math.min(1,delta/Theme.px(this,60)));
        int desired=Math.round(swipeBounds.width()*(1+.18f*progress));customWidth=desired;resize();
        params.x=swipeBounds.left+(swipeBounds.width()-params.width)/2;params.y=swipeBounds.top+Math.round(delta*.35f);clampPosition();queueLayout();
    }
    private void endWindowSwipe(int action){
        if(swipeBounds==null)return;
        if(action!=0){cancelReturn();restoreSwipe();if(action<0)saveAndClose();else if(!fullScreen)toggleFullscreen();return;}
        final float from=swipeDelta;returnAnimator=android.animation.ValueAnimator.ofFloat(1,0);returnAnimator.setDuration(160);
        returnAnimator.setInterpolator(new android.view.animation.DecelerateInterpolator());
        returnAnimator.addUpdateListener(v->previewWindowSwipe(from*(float)v.getAnimatedValue()));
        returnAnimator.addListener(new android.animation.AnimatorListenerAdapter(){@Override public void onAnimationEnd(android.animation.Animator animation){restoreSwipe();returnAnimator=null;}});returnAnimator.start();
    }
    void resize(){
        android.util.DisplayMetrics m=new android.util.DisplayMetrics();windows.getDefaultDisplay().getRealMetrics(m);
        int max=GameWindowGeometry.fitWidth(Integer.MAX_VALUE,m.widthPixels,m.heightPixels,1);
        int wanted=fullScreen?max:customWidth>0?customWidth:(int)(max*.85);
        params.width=GameWindowGeometry.fitWidth(wanted,m.widthPixels,m.heightPixels,Theme.px(this,200));
        params.height=GameWindowGeometry.height(params.width);
        params.x=(m.widthPixels-params.width)/2;params.y=(m.heightPixels-params.height)/2;
    }
    void toggleFullscreen(){
        if(!fullScreen){restoredBounds=new android.graphics.Rect(params.x,params.y,params.x+params.width,params.y+params.height);customWidth=params.width;}
        fullScreen=!fullScreen;
        if(fullScreen)params.flags|=WindowManager.LayoutParams.FLAG_FULLSCREEN;else params.flags&=~WindowManager.LayoutParams.FLAG_FULLSCREEN;
        if(android.os.Build.VERSION.SDK_INT>=30)params.setFitInsetsTypes(fullScreen?0:WindowInsets.Type.statusBars());
        params.screenOrientation=fullScreen
            ?android.content.pm.ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
            :android.content.pm.ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED;
        resize();
        if(!fullScreen&&restoredBounds!=null){params.x=restoredBounds.left;params.y=restoredBounds.top;clampPosition();}
        shell.updateMode();windows.updateViewLayout(shell,params);
    }
    void hideGame(){
        cancelReturn();if(swipeBounds!=null)restoreSwipe();
        shell.setPreviewing(false);shell.removeCallbacks(applyLayout);layoutQueued=false;
        if(shell!=null)shell.dismissMenu();
        setHostMuted(true);
        hidden=true;
        if(windowRegistered){windows.removeViewImmediate(shell);windowRegistered=false;}
    }
    void showGame(){
        handler.removeCallbacks(autoClose);
        setHostMuted(false);
        hidden=false;
        if(shell!=null){
            clampPosition();shell.setVisibility(View.VISIBLE);
            registerWindow();
        }
    }
    private void registerWindow(){
        if(windowRegistered||shell==null||windows==null)return;
        windows.addView(shell,params);windowRegistered=true;
        android.util.Log.i("CrypticNotes","Mini-game window registered");
    }
    void setHostMuted(boolean mute){mute=mute||!getSharedPreferences("mobile",0).getBoolean("gameSound",true);if(web!=null)web.evaluateJavascript("window.__jellyfishSetMuted&&window.__jellyfishSetMuted("+mute+")",null);}
    void clampPosition(){android.util.DisplayMetrics m=new android.util.DisplayMetrics();windows.getDefaultDisplay().getRealMetrics(m);params.x=Math.max(0,Math.min(m.widthPixels-params.width,params.x));params.y=Math.max(0,Math.min(m.heightPixels-params.height,params.y));}
    @Override public void onConfigurationChanged(Configuration c){
        super.onConfigurationChanged(c);
        if(params!=null){resize();if(shell.isAttachedToWindow())windows.updateViewLayout(shell,params);requestHighRefreshRate();}
    }
    private void requestHighRefreshRate(){
        Display display=windows.getDefaultDisplay();Display.Mode current=display.getMode();float rate=display.getRefreshRate();
        for(Display.Mode mode:display.getSupportedModes())if(mode.getPhysicalWidth()==current.getPhysicalWidth()&&mode.getPhysicalHeight()==current.getPhysicalHeight())rate=Math.max(rate,mode.getRefreshRate());
        if(getSharedPreferences("mobile",0).getBoolean("power_saving",false))rate=Math.min(rate,60f);
        params.preferredRefreshRate=rate;
        if(android.os.Build.VERSION.SDK_INT>=35)web.setRequestedFrameRate(rate);
        if(shell.isAttachedToWindow())windows.updateViewLayout(shell,params);
        android.util.Log.i("CrypticNotes","Mini-game refresh requested="+rate+", current="+display.getRefreshRate()+", WebView="+WebView.getCurrentWebViewPackage());
    }
    android.graphics.Rect visibleBounds(){
        if(hidden||shell==null||!shell.isAttachedToWindow())return new android.graphics.Rect();
        int[] location=new int[2];shell.getLocationOnScreen(location);
        return new android.graphics.Rect(location[0],location[1],location[0]+shell.getWidth(),location[1]+shell.getHeight());
    }
    int[] sceneOverlaySignature(int screenWidth,int screenHeight){
        if(shell==null||hidden||!shell.isAttachedToWindow())return null;
        android.graphics.Bitmap bitmap=null;
        try{
            bitmap=android.graphics.Bitmap.createBitmap(160,90,android.graphics.Bitmap.Config.ARGB_8888);
            android.graphics.Canvas canvas=new android.graphics.Canvas(bitmap);
            canvas.scale(160f/screenWidth,90f/screenHeight);
            int[] location=new int[2];shell.getLocationOnScreen(location);
            canvas.translate(location[0],location[1]);shell.draw(canvas);
            int[] result=new int[14400];bitmap.getPixels(result,0,160,0,0,160,90);return result;
        }catch(Exception e){return null;}finally{if(bitmap!=null)bitmap.recycle();}
    }
    private synchronized void write(String json)throws Exception{
        if(json==null||json.length()>1024*1024)throw new IOException("存档过大");JSONObject data=new JSONObject(json);Iterator<String> keys=data.keys();while(keys.hasNext()){String key=keys.next();if(!key.startsWith("jellyfish.")||!(data.get(key) instanceof String))throw new IOException("无效存档");}
        FileOutputStream out=null;try{out=save.startWrite();out.write(json.getBytes(StandardCharsets.UTF_8));save.finishWrite(out);}catch(Exception e){if(out!=null)save.failWrite(out);throw e;}
    }
    final class Bridge {
        @JavascriptInterface public void reportFrameStats(String json){
            if(json==null||json.length()>1024)return;
            try{JSONObject stats=new JSONObject(json);android.util.Log.i("CrypticNotes","Mini-game RAF fps="+stats.optDouble("rafFps")+", worst gap="+stats.optInt("worstGapMs")+"ms");}catch(Exception ignored){}
        }
        @JavascriptInterface public void safeExit(String message){
            try{JSONObject m=new JSONObject(message);if(!"safe-exit".equals(m.optString("type")))return;
                if(!m.optBoolean("saved"))throw new IOException(m.optString("reason","保存失败"));write(m.getString("json"));
                runOnUiThread(()->{handler.removeCallbacks(saveTimeout);stopSelf();});
            }catch(Exception e){runOnUiThread(()->closeFailed(e.getMessage()));}
        }
        @JavascriptInterface public String saveStorage(String json,boolean exit){
            try{write(json);if(exit)runOnUiThread(()->stopSelf());return "ok";}catch(Exception e){return "保存失败："+e.getMessage();}
        }
    }
    void saveAndClose(){
        if(closing||web==null)return;closing=true;
        cancelReturn();if(swipeBounds!=null)restoreSwipe();shell.setPreviewing(false);
        handler.postDelayed(saveTimeout,10000);
        web.evaluateJavascript("(()=>{if(typeof window.__jellyfishHostSave!=='function')return 'bridge_missing';window.__jellyfishHostSave(1);return 'started'})()",result->{if(closing&&"\"bridge_missing\"".equals(result))closeFailed("关闭接口未加载，请更新小游戏后重试");});
    }
    private void closeFailed(String reason){
        handler.removeCallbacks(saveTimeout);closing=false;
        if(web!=null)web.evaluateJavascript("window.__jellyfishHostFrozen=false",null);
        android.util.Log.e("CrypticNotes","Mini-game close failed: "+reason);
        // Never steal focus back from the main game after an automatic hide.
        Toast.makeText(this,(hidden?"小游戏保持后台，":"")+"保存未完成："+reason+"。请更新小游戏后重试",Toast.LENGTH_LONG).show();
    }
    @Override public void onDestroy(){current=null;running=false;hidden=false;cancelReturn();handler.removeCallbacksAndMessages(null);if(screenReceiver!=null)unregisterReceiver(screenReceiver);if(shell!=null){shell.removeCallbacks(applyLayout);if(windowRegistered){windows.removeViewImmediate(shell);windowRegistered=false;}}if(web!=null){web.removeJavascriptInterface("NativeGame");web.destroy();web=null;}super.onDestroy();}
}
