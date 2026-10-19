package com.crypticnotes.mobile;
import android.app.AlertDialog;
import android.content.*;
import android.os.*;
import android.view.View;
import android.widget.*;
/** Download-only state, or a compact final version fold. */
final class MatchingModuleManager extends LinearLayout {
    final MatchingModuleStore store;final Theme.ChalkButton action,delete;final TextView status;boolean busy;Boolean available;Runnable changed;
    final Handler main=new Handler(Looper.getMainLooper());
    MatchingModuleManager(Context c){super(c);setOrientation(VERTICAL);store=new MatchingModuleStore(c);LinearLayout row=new LinearLayout(c);action=new Theme.ChalkButton(c,"下载",true);delete=new Theme.ChalkButton(c,"删除");row.addView(action,new LayoutParams(0,-2,1));row.addView(delete);addView(row);status=Theme.muted(c,"");status.setVisibility(GONE);addView(status);action.setOnClickListener(v->run(false));delete.setOnClickListener(v->new AlertDialog.Builder(c).setMessage("删除识图模块？个人地图与设置会保留。").setNegativeButton("取消",null).setPositiveButton("删除",(d,w)->run(true)).show());refresh();}
    void refresh(){boolean installed=store.installed();action.setText(busy?"处理中…":!installed?"下载":available==null?"检查更新":available?"更新":"已是最新版");action.setEnabled(!busy&&(!installed||available==null||available));delete.setVisibility(installed?VISIBLE:GONE);delete.setEnabled(!busy);}
    void run(boolean removing){if(busy)return;boolean check=!removing&&store.installed()&&available==null;busy=true;refresh();status.setVisibility(VISIBLE);status.setText(check?"正在检查…":"正在准备…");if(!check)getContext().stopService(new Intent(getContext(),CaptureService.class));new Thread(()->{String error=null;try{if(check)available=store.updateAvailable();else if(removing){store.delete();available=null;}else{store.download(text->main.post(()->status.setText(text)));available=false;}}catch(Exception e){error=e.getMessage();}String result=error;main.post(()->{busy=false;status.setVisibility(result==null?GONE:VISIBLE);status.setText(result==null?"":result);refresh();if(changed!=null)changed.run();});},"matching-module").start();}
}
