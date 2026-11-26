package com.crypticnotes.mobile;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;

public class MiniGamesActivity extends Activity {
    @Override public void onCreate(Bundle state){
        super.onCreate(state);
        startActivity(new Intent(this,MainActivity.class).putExtra("open_module","games")
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP));
        finish();
    }
}
