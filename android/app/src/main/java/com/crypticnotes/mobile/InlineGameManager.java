package com.crypticnotes.mobile;
import android.app.AlertDialog;
import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.widget.*;
/** Only package management; starting remains in the floating panel. */
final class InlineGameManager extends LinearLayout {
    Runnable stateChanged;
    private final MiniGameStore store;
    private final Theme.ChalkButton download,delete;
    private final TextView status;
    private boolean busy;
    private final Handler main=new Handler(Looper.getMainLooper());
    InlineGameManager(Context c){
        super(c);store=new MiniGameStore(c);setOrientation(VERTICAL);
        LinearLayout row=new LinearLayout(c);row.setGravity(Gravity.CENTER_VERTICAL);
        TextView title=Theme.muted(c,"合成大水母：");Theme.text(title,15,Theme.TEXT);row.addView(title,new LinearLayout.LayoutParams(0,-2,1));
        download=new Theme.ChalkButton(c,"下载",true);delete=new Theme.ChalkButton(c,"删除");
        row.addView(download,new LinearLayout.LayoutParams(Theme.px(c,90),Theme.px(c,46)));
        LinearLayout.LayoutParams dp=new LinearLayout.LayoutParams(Theme.px(c,64),Theme.px(c,46));dp.leftMargin=Theme.px(c,8);row.addView(delete,dp);addView(row);
        status=Theme.muted(c,"");addView(status);status.setVisibility(GONE);
        download.setOnClickListener(v->{if(busy||MiniGameOverlayService.running)return;busy=true;refresh();status.setVisibility(VISIBLE);status.setText("正在下载…");
            new Thread(()->{String error=null;try{store.download(text->main.post(()->status.setText(text)));}catch(Exception e){error=e.getMessage();}
                final String result=error;main.post(()->{busy=false;if(result==null)c.getSharedPreferences("mobile",0).edit().putBoolean("gameUpdateAvailable",false).apply();refresh();status.setVisibility(result==null?GONE:VISIBLE);status.setText(result==null?"":result);});},"inline-game-download").start();
        });
        delete.setOnClickListener(v->{if(busy||MiniGameOverlayService.running)return;new AlertDialog.Builder(c).setMessage("删除游戏包？存档和成绩会保留。").setNegativeButton("取消",null).setPositiveButton("删除",(d,w)->{
            try{store.delete();c.getSharedPreferences("mobile",0).edit().putBoolean("gameUpdateAvailable",false).apply();refresh();}catch(Exception e){status.setVisibility(VISIBLE);status.setText(e.getMessage());}
        }).show();});refresh();
    }
    void refresh(){boolean installed=store.installed(),update=MiniGameUpdates.available(getContext());download.setText(busy?"下载中":installed?"更新":"下载");download.setEnabled(!busy&&!MiniGameOverlayService.running&&(!installed||update));delete.setEnabled(installed&&!busy&&!MiniGameOverlayService.running);ActionIcon.set(download,ActionIcon.GAME,installed&&update);if(stateChanged!=null)stateChanged.run();}
}
