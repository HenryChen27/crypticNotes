package com.crypticnotes.mobile;
import android.content.Context;
import android.os.Handler;
import android.os.Looper;
/** Metadata-only check, throttled across app and floating panel. */
final class MiniGameUpdates {
    private static volatile long checkedAt;private static volatile boolean checking;
    private static final java.util.ArrayList<Runnable> listeners=new java.util.ArrayList<>();
    static boolean available(Context c){return c.getSharedPreferences("mobile",0).getBoolean("gameUpdateAvailable",false);}
    static void check(Context context,Runnable callback){
        Context c=context.getApplicationContext();
        synchronized(MiniGameUpdates.class){
            if(checkedAt!=0&&android.os.SystemClock.elapsedRealtime()-checkedAt<60000){new Handler(Looper.getMainLooper()).post(callback);return;}
            listeners.add(callback);if(checking)return;checking=true;
        }
        new Thread(()->{try{
            org.json.JSONObject catalog=MiniGameStore.collection();boolean update=false;
            java.util.Iterator<String> ids=catalog.keys();while(ids.hasNext()){String id=ids.next();MiniGameStore store=new MiniGameStore(c,id);if(store.installed()&&!catalog.getJSONObject(id).optString("sha256").equals(store.hash()))update=true;}
            c.getSharedPreferences("mobile",0).edit().putString("gameCatalog",catalog.toString()).putBoolean("gameUpdateAvailable",update).apply();
            checkedAt=android.os.SystemClock.elapsedRealtime();
        }catch(Exception ignored){}finally{
            java.util.ArrayList<Runnable> ready;
            synchronized(MiniGameUpdates.class){checking=false;ready=new java.util.ArrayList<>(listeners);listeners.clear();}
            Handler main=new Handler(Looper.getMainLooper());for(Runnable listener:ready)main.post(listener);
        }},"game-update-check").start();
    }
}
