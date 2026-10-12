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
    private int barHeight;
    private WindowManager windows;
    private WindowManager.LayoutParams params;
    private LinearLayout shell;
    private android.content.BroadcastReceiver screenReceiver;
    private TextView restoreButton;
    private boolean fullScreen;
    private final android.os.Handler handler=new android.os.Handler(android.os.Looper.getMainLooper());
    private final Runnable saveTimeout=()->{closing=false;showGame();Toast.makeText(this,"保存超时，请重试",Toast.LENGTH_LONG).show();};
    @Override public IBinder onBind(Intent intent){return null;}
    void runOnUiThread(Runnable action){new android.os.Handler(android.os.Looper.getMainLooper()).post(action);}
    @Override public int onStartCommand(Intent intent,int flags,int id){if(intent!=null&&"show".equals(intent.getAction()))showGame();return START_NOT_STICKY;}
    @Override public void onCreate(){
        super.onCreate();
        running=true;barHeight=Theme.px(this,30);
        NotificationManager manager=getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel("mini-game","小游戏",NotificationManager.IMPORTANCE_LOW));
        startForeground(1907,new Notification.Builder(this,"mini-game").setSmallIcon(android.R.drawable.ic_media_play).setContentTitle("合成大水母正在运行").setContentText("可在悬浮窗口中暂停、保存并退出").setOngoing(true).build());
        MiniGameStore store=new MiniGameStore(this);if(!store.installed()||!Settings.canDrawOverlays(this)){stopSelf();return;}
        root=new File(store.game,"game");File folder=new File(getFilesDir(),"minigame-saves/jellyfish");folder.mkdirs();save=new AtomicFile(new File(folder,"local-storage.json"));
        shell=new LinearLayout(this);shell.setOrientation(1);shell.setBackgroundColor(0xff182430);
        LinearLayout bar=new LinearLayout(this);bar.setGravity(Gravity.CENTER_VERTICAL);
        TextView title=new TextView(this);title.setText("合成大水母");title.setTextColor(Theme.TITLE);title.setPadding(12,0,0,0);bar.addView(title,new LinearLayout.LayoutParams(0,barHeight,1));
        TextView full=new TextView(this);full.setText("全屏");full.setTextColor(Theme.TITLE);full.setGravity(Gravity.CENTER);bar.addView(full,new LinearLayout.LayoutParams(Theme.px(this,62),barHeight));
        full.setOnClickListener(v->{fullScreen=!fullScreen;full.setText(fullScreen?"半屏":"全屏");resize();windows.updateViewLayout(shell,params);});
        TextView hide=new TextView(this);hide.setText("隐藏");hide.setTextColor(Theme.TITLE);hide.setGravity(Gravity.CENTER);bar.addView(hide,new LinearLayout.LayoutParams(Theme.px(this,48),barHeight));hide.setOnClickListener(v->hideGame());
        TextView close=new TextView(this);close.setText("×");close.setTextColor(Theme.TITLE);close.setTextSize(24);close.setGravity(Gravity.CENTER);bar.addView(close,new LinearLayout.LayoutParams(Theme.px(this,40),barHeight));close.setOnClickListener(v->saveAndClose());shell.addView(bar);
        web=new WebView(this);shell.addView(web,new LinearLayout.LayoutParams(-1,0,1));
        windows=(WindowManager)getSystemService(WINDOW_SERVICE);
        params=new WindowManager.LayoutParams(1,1,WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,android.graphics.PixelFormat.TRANSLUCENT);
        params.gravity=Gravity.TOP|Gravity.LEFT;resize();windows.addView(shell,params);
        title.setOnTouchListener(new View.OnTouchListener(){float x,y;int sx,sy;
            public boolean onTouch(View v,MotionEvent e){if(e.getActionMasked()==MotionEvent.ACTION_DOWN){x=e.getRawX();y=e.getRawY();sx=params.x;sy=params.y;}
                else if(e.getActionMasked()==MotionEvent.ACTION_MOVE){params.x=Math.max(0,sx+Math.round(e.getRawX()-x));params.y=Math.max(0,sy+Math.round(e.getRawY()-y));windows.updateViewLayout(shell,params);}return true;}
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
                        try(InputStream bridge=getAssets().open("safe-exit.js")){script+="<script>window.__jellyfishHostPost=m=>NativeGame.safeExit(JSON.stringify(m));"+new String(MiniGameStore.bytes(bridge,64*1024),StandardCharsets.UTF_8)+"</script>";}
                        page=page.replace("<head>","<head><meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'self' data: blob:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-src 'none'; object-src 'none'\">"+script);
                        return new WebResourceResponse("text/html","UTF-8",new ByteArrayInputStream(page.getBytes(StandardCharsets.UTF_8)));
                    }
                    String name=f.getName().toLowerCase(Locale.ROOT),mime=java.net.URLConnection.guessContentTypeFromName(name);
                    if(name.endsWith(".js"))mime="application/javascript";else if(name.endsWith(".css"))mime="text/css";else if(name.endsWith(".ttf"))mime="font/ttf";
                    return new WebResourceResponse(mime==null?"application/octet-stream":mime,null,new FileInputStream(f));
                }catch(Exception e){return blocked();}
            }
            @Override public void onReceivedError(WebView view,WebResourceRequest request,WebResourceError error){if(request.isForMainFrame())Toast.makeText(MiniGameOverlayService.this,"游戏加载失败："+error.getDescription(),Toast.LENGTH_LONG).show();}
        });web.loadUrl("https://minigame.local/index.html");
        screenReceiver=new android.content.BroadcastReceiver(){public void onReceive(android.content.Context c,Intent i){
            if(web!=null)saveAndClose();
        }};
        registerReceiver(screenReceiver,new android.content.IntentFilter(Intent.ACTION_SCREEN_OFF));
    }
    static boolean local(Uri uri){return "https".equals(uri.getScheme())&&"minigame.local".equals(uri.getHost());}
    static WebResourceResponse blocked(){return new WebResourceResponse("text/plain","UTF-8",403,"Blocked",Collections.emptyMap(),new ByteArrayInputStream(new byte[0]));}
    void resize(){android.util.DisplayMetrics m=getResources().getDisplayMetrics();int width=Math.min((int)(m.widthPixels*.90),(int)((m.heightPixels*.85-barHeight)*2559/1441));params.width=fullScreen?m.widthPixels:Math.max(240,width);params.height=fullScreen?m.heightPixels:(int)(params.width*1441.0/2559)+barHeight;params.x=(m.widthPixels-params.width)/2;params.y=(m.heightPixels-params.height)/2;}
    void hideGame(){shell.setVisibility(View.GONE);if(restoreButton==null){restoreButton=new TextView(this);restoreButton.setText("水母");restoreButton.setTextColor(Theme.TITLE);restoreButton.setBackgroundColor(0xdd182430);restoreButton.setGravity(Gravity.CENTER);WindowManager.LayoutParams p=new WindowManager.LayoutParams(Theme.px(this,52),Theme.px(this,40),WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,android.graphics.PixelFormat.TRANSLUCENT);p.gravity=Gravity.TOP|Gravity.RIGHT;p.y=Theme.px(this,60);windows.addView(restoreButton,p);restoreButton.setOnClickListener(v->showGame());}restoreButton.setVisibility(View.VISIBLE);}
    void showGame(){if(shell!=null)shell.setVisibility(View.VISIBLE);if(restoreButton!=null)restoreButton.setVisibility(View.GONE);}
    @Override public void onConfigurationChanged(Configuration c){super.onConfigurationChanged(c);if(params!=null){resize();windows.updateViewLayout(shell,params);}}
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
    @Override public void onDestroy(){running=false;handler.removeCallbacksAndMessages(null);if(screenReceiver!=null)unregisterReceiver(screenReceiver);if(restoreButton!=null&&restoreButton.isAttachedToWindow())windows.removeView(restoreButton);if(shell!=null&&shell.isAttachedToWindow())windows.removeView(shell);if(web!=null){web.removeJavascriptInterface("NativeGame");web.destroy();web=null;}super.onDestroy();}
}
