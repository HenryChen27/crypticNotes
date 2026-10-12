package com.crypticnotes.mobile;

import android.app.*;
import android.os.Bundle;
import android.content.Intent;
import android.view.View;
import android.widget.*;

/** Download/delete resources separately from the APK. */
public class MiniGamesActivity extends Activity {
    private MiniGameStore store;
    private TextView status;
    private Theme.ChalkButton download, delete;
    private volatile boolean busy;
    @Override public void onCreate(Bundle state){
        super.onCreate(state);store=new MiniGameStore(this);
        LinearLayout body=new LinearLayout(this);body.setOrientation(1);body.setPadding(24,24,24,24);body.setBackgroundColor(0xff182430);
        body.addView(Theme.text(new TextView(this),23,Theme.TITLE));((TextView)body.getChildAt(0)).setText("合成大水母");
        body.addView(Theme.muted(this,"按需下载 · 暂停与存档 · 仅自己可见的排行榜\n删除包体会保留本机存档和成绩。"));
        status=Theme.muted(this,"");body.addView(status);
        download=new Theme.ChalkButton(this,"下载游戏",true);body.addView(download);
        delete=new Theme.ChalkButton(this,"删除游戏包");body.addView(delete);
        Theme.ChalkButton back=new Theme.ChalkButton(this,"返回");body.addView(back);back.setOnClickListener(v->finish());ScrollView scroll=new ScrollView(this);scroll.addView(body);setContentView(scroll);
        download.setOnClickListener(v->{if(busy||MiniGameOverlayService.running)return;busy=true;refresh();new Thread(()->{
            String error=null;try{store.download(text->runOnUiThread(()->status.setText(text)));}catch(Exception e){error=e.getMessage();}
            final String result=error;runOnUiThread(()->{busy=false;if(isFinishing()||isDestroyed())return;refresh();if(result==null)getSharedPreferences("mobile",0).edit().putBoolean("gameUpdateAvailable",false).apply();status.setText(result==null?"游戏已是最新版，请从悬浮球启动":result);});
        },"minigame-download").start();});
        delete.setOnClickListener(v->{if(MiniGameOverlayService.running)return;new AlertDialog.Builder(this).setMessage("删除游戏包？本机存档和排行榜会保留。").setNegativeButton("取消",null).setPositiveButton("删除",(d,w)->{
            try{store.delete();refresh();}catch(Exception e){status.setText(e.getMessage());}
        }).show();});refresh();
    }
    @Override protected void onResume(){super.onResume();if(store!=null){refresh();MiniGameUpdates.check(this,()->{if(!isDestroyed()&&!isFinishing())refresh();});}}
    void refresh(){
        boolean installed=store.installed(),running=MiniGameOverlayService.running;
        download.setEnabled(!busy&&!running);delete.setEnabled(installed&&!busy&&!running);
        ActionIcon.set(download,ActionIcon.GAME,MiniGameUpdates.available(this));
        download.setText(busy?"正在下载…":installed?"检查游戏更新":"下载游戏");
        status.setText(running?"游戏正在悬浮窗口运行，请先保存退出再更新或删除":installed?"已安装 "+store.version():"按需下载，使用手机系统网页引擎");
    }
}
