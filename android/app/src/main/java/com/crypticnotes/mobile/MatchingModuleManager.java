package com.crypticnotes.mobile;
import android.app.AlertDialog;
import android.content.*;
import android.os.*;
import android.view.View;
import android.widget.*;
/** Download-only state, or a compact final version fold. */
final class MatchingModuleManager extends LinearLayout {
    final MatchingModuleStore store;final Theme.ChalkButton action,delete;final TextView status,versionLabel;boolean busy;static volatile boolean operationRunning;Boolean available;Runnable changed;
    final Handler main=new Handler(Looper.getMainLooper());
    MatchingModuleManager(Context c){this(c,null);}
    MatchingModuleManager(Context c,String provider){super(c);setOrientation(VERTICAL);
        if(provider==null){store=null;action=null;delete=null;status=null;versionLabel=null;
            for(String id:new String[]{"lianghapi","zhanshi"}){MatchingModuleManager row=new MatchingModuleManager(c,id);row.changed=()->{if(changed!=null)changed.run();};addView(row);}return;}
        addView(Theme.muted(c,provider.equals("lianghapi")?"凉哈皮地图库":"展十地图库"));store=new MatchingModuleStore(c,provider);LinearLayout row=new LinearLayout(c);action=new Theme.ChalkButton(c,"下载",true);delete=new Theme.ChalkButton(c,"删除");row.addView(action,new LayoutParams(0,-2,1));row.addView(delete);addView(row);versionLabel=Theme.muted(c,"");addView(versionLabel);status=Theme.muted(c,"");status.setVisibility(GONE);addView(status);action.setOnClickListener(v->run(false));delete.setOnClickListener(v->new AlertDialog.Builder(c).setMessage("删除这个作者的地图库？其他作者与个人地图会保留。").setNegativeButton("取消",null).setPositiveButton("删除",(d,w)->run(true)).show());refresh();}
    void refresh(){if(store==null){for(int i=0;i<getChildCount();i++)if(getChildAt(i) instanceof MatchingModuleManager)((MatchingModuleManager)getChildAt(i)).refresh();return;}boolean installed=store.installed();versionLabel.setText("版本 "+store.version()+(store.latest==null?"":String.format(java.util.Locale.ROOT," · 下载 %.1f MB",store.latest.optLong("size")/1048576.0)));action.setText(busy?"处理中…":!installed?"下载":available==null?"检查更新":available?"更新":"已是最新版");action.setEnabled(!busy&&(!installed||available==null||available));delete.setVisibility(installed?VISIBLE:GONE);delete.setEnabled(!busy);}
    void run(boolean removing){if(busy||operationRunning)return;operationRunning=true;boolean check=!removing&&store.installed()&&available==null;busy=true;refresh();status.setVisibility(VISIBLE);status.setText(check?"正在检查…":"正在准备…");if(!check)getContext().stopService(new Intent(getContext(),CaptureService.class));new Thread(()->{String error=null;try{if(check)available=store.updateAvailable();else if(removing){store.delete();available=null;}else{store.download(text->main.post(()->status.setText(text)));available=false;}}catch(Exception e){error=e.getMessage();}String result=error;main.post(()->{busy=false;operationRunning=false;status.setVisibility(result==null?GONE:VISIBLE);status.setText(result==null?"":result);refresh();if(changed!=null)changed.run();});},"matching-module").start();}
}
