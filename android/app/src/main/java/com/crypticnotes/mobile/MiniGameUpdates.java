package com.crypticnotes.mobile;
import android.content.Context;
import android.os.Handler;
import android.os.Looper;
/** Metadata-only check, throttled across app and floating panel. */
final class MiniGameUpdates {
    private static volatile long checkedAt;private static volatile boolean checking,confirmed,failed;
    private static final java.util.ArrayList<Runnable> listeners=new java.util.ArrayList<>();
    static PackageState state(MiniGameStore store,boolean installed,org.json.JSONObject spec){
        if(installed&&confirmed&&!checking&&!failed&&spec==null)return PackageState.WITHDRAWN;
        return PackageState.resolve(installed,checking,failed,confirmed&&spec!=null?spec.optString("sha256"):null,installed?store.hash():"");
    }
    static boolean available(Context c){org.json.JSONObject catalog=GameCatalog.cached(c);for(String id:GameCatalog.ids(c)){MiniGameStore store=new MiniGameStore(c,id);if(state(store,store.installed(),catalog.optJSONObject(id))==PackageState.UPDATE)return true;}return false;}
    private static final Object fetchLock=new Object();
    static org.json.JSONObject fetch(Context c)throws Exception{synchronized(fetchLock){
        try{org.json.JSONObject catalog=MiniGameStore.collection();c.getSharedPreferences("mobile",0).edit().putString("gameCatalog",catalog.toString()).apply();
            confirmed=true;failed=false;return catalog;}
        catch(Exception error){confirmed=false;failed=true;throw error;}
        finally{checkedAt=android.os.SystemClock.elapsedRealtime();}
    }}
    static void check(Context context,Runnable callback){
        check(context,false,callback);
    }
    static void check(Context context,boolean force,Runnable callback){
        Context c=context.getApplicationContext();
        synchronized(MiniGameUpdates.class){
            if(!checking&&!force&&checkedAt!=0&&android.os.SystemClock.elapsedRealtime()-checkedAt<60000){new Handler(Looper.getMainLooper()).post(callback);return;}
            listeners.add(callback);if(checking)return;checking=true;
        }
        new Thread(()->{try{
            org.json.JSONObject catalog=fetch(c);GameIcons.prefetch(c,catalog);
        }catch(Exception ignored){}finally{
            java.util.ArrayList<Runnable> ready;
            synchronized(MiniGameUpdates.class){checking=false;ready=new java.util.ArrayList<>(listeners);listeners.clear();}
            Handler main=new Handler(Looper.getMainLooper());for(Runnable listener:ready)main.post(listener);
        }},"game-update-check").start();
    }
}
