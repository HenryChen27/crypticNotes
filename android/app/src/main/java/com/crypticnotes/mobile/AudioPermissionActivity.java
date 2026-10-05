package com.crypticnotes.mobile;

import android.app.*;
import android.os.Bundle;
import android.content.pm.PackageManager;
import android.Manifest;

/** Optional playback-capture permission, requested only from the audio switch. */
public class AudioPermissionActivity extends Activity {
    private boolean requested;
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        requested=state!=null && state.getBoolean("requested");
        if(requested) return;
        new AlertDialog.Builder(this).setTitle("录制内部声音")
                .setMessage("系统会请求录音权限，用于采集应用播放的声音，不启用麦克风。游戏禁止声音采集时，视频可能仍无声。")
                .setPositiveButton("继续",(dialog,which) -> { requested=true; requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO},7); })
                .setNegativeButton("取消",(dialog,which) -> finish())
                .setOnCancelListener(dialog -> finish()).show();
    }
    @Override protected void onSaveInstanceState(Bundle state) { state.putBoolean("requested",requested); super.onSaveInstanceState(state); }
    @Override public void onRequestPermissionsResult(int code,String[] permissions,int[] results) {
        super.onRequestPermissionsResult(code,permissions,results);
        if(code==7) {
            boolean granted=results.length>0 && results[0]==PackageManager.PERMISSION_GRANTED;
            getSharedPreferences("mobile",0).edit().putBoolean("record_internal_audio",granted).apply();
            android.widget.Toast.makeText(this,granted?"已开启内部声音，下次录制生效":"保留无声录制",android.widget.Toast.LENGTH_SHORT).show();
            finish();
        }
    }
}
