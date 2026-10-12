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
        current=this;running=true;hidden=false;
        NotificationManager manager=getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel("mini-game","小游戏",NotificationManager.IMPORTANCE_LOW));
        startForeground(1907,new Notification.Builder(this,"mini-game").setSmallIcon(android.R.drawable.ic_media_play).setContentTitle("合成大水母正在运行").setContentText("可在悬浮窗口中暂停、保存并退出").setContentIntent(PendingIntent.getForegroundService(this,0,new Intent(this,MiniGameOverlayService.class).setAction("show"),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE)).setOngoing(true).build());
        MiniGameStore store=new MiniGameStore(this);if(!store.installed()||!Settings.canDrawOverlays(this)){stopSelf();return;}
        root=new File(store.game,"game");File folder=new File(getFilesDir(),"minigame-saves/jellyfish");folder.mkdirs();save=new AtomicFile(new File(folder,"local-storage.json"));
        web=new WebView(this);
        shell=new GameWindowChrome(this,web,new GameWindowChrome.Host(){
            public boolean fullscreen(){return fullScreen;}
            public void move(int dx,int dy){if(fullScreen)return;params.x+=dx;params.y+=dy;clampPosition();windows.updateViewLayout(shell,params);}
            public void scale(int delta,boolean left){
                if(fullScreen)return;int right=params.x+params.width,x=params.x,y=params.y;
                customWidth=params.width+delta;resize();params.x=left?right-params.width:x;params.y=y;clampPosition();windows.updateViewLayout(shell,params);
            }
            public void minimize(){hideGame();}
            public void toggleFull(){toggleFullscreen();}
            public void close(){saveAndClose();}
        });
        windows=(WindowManager)getSystemService(WINDOW_SERVICE);
        params=new WindowManager.LayoutParams(1,1,WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS | WindowManager.LayoutParams.FLAG_FULLSCREEN,android.graphics.PixelFormat.TRANSLUCENT);
        params.gravity=Gravity.TOP|Gravity.LEFT;if(android.os.Build.VERSION.SDK_INT>=28)params.layoutInDisplayCutoutMode=WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;resize();windows.addView(shell,params);
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
    static WebResourceResponse blocked(){return new WebResourceResponse("text/plain","UTF-8",403,"Blocked",Collections.emptyMap(),new ByteArrayInputStream(new byte[0]));}
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
        fullScreen=!fullScreen;resize();
        if(!fullScreen&&restoredBounds!=null){params.x=restoredBounds.left;params.y=restoredBounds.top;clampPosition();}
        shell.updateMode();windows.updateViewLayout(shell,params);
    }
    void hideGame(){
        if(shell!=null)shell.dismissMenu();
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
