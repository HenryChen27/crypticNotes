package com.crypticnotes.mobile;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.util.LruCache;
import android.widget.ImageView;
import android.widget.LinearLayout;
import java.io.*;

/** assets/icon.png is relative to a game's index.html, never to the host APK. */
final class GameIcons {
    private static final LruCache<String,Bitmap> cache=new LruCache<>(16);
    static Bitmap bitmap(Context context,String id){
        File root=new File(context.getFilesDir(),"minigames/"+id+"/game");
        File icon=new File(root,"assets/icon.png");
        if(!icon.isFile())icon=new File(context.getFilesDir(),"game-icons/"+id+".png");
        String key=id+":"+icon.lastModified()+":"+icon.length();
        Bitmap saved=cache.get(key);if(saved!=null)return saved;
        Bitmap result=null;
        try{
            if(icon.isFile()&&icon.length()<=4*1024*1024&&icon.getCanonicalPath().startsWith(context.getFilesDir().getCanonicalPath()+File.separator))
                result=decode(icon);
        }catch(IOException|RuntimeException ignored){}
        if(result==null)result=asset(context,"minigames/icons/"+id+".png");
        if(result==null)result=asset(context,"minigames/fish5.png");
        if(result!=null)cache.put(key,result);return result;
    }
    static void prefetch(Context context,org.json.JSONObject games){
        java.util.Iterator<String> ids=games.keys();
        while(ids.hasNext()){
            String id=ids.next();if(!id.matches("[a-z0-9][a-z0-9-]*"))continue;
            org.json.JSONObject spec=games.optJSONObject(id),info=spec==null?null:spec.optJSONObject("icon");if(info==null)continue;
            String url=info.optString("url"),sha=info.optString("sha256");
            if(!url.startsWith("https://github.com/HenryChen27/mini_games/releases/download/")||!sha.matches("[0-9a-f]{64}"))continue;
            try{
                File target=new File(context.getFilesDir(),"game-icons/"+id+".png");
                if(target.isFile()&&target.length()<=4*1024*1024&&hash(java.nio.file.Files.readAllBytes(target.toPath())).equals(sha))continue;
                java.net.HttpURLConnection connection=MiniGameStore.connect(url);byte[] data;
                try(InputStream in=connection.getInputStream()){data=MiniGameStore.bytes(in,4*1024*1024);}finally{connection.disconnect();}
                if(!hash(data).equals(sha))continue;
                target.getParentFile().mkdirs();android.util.AtomicFile file=new android.util.AtomicFile(target);FileOutputStream out=null;
                try{out=file.startWrite();out.write(data);file.finishWrite(out);}catch(IOException e){if(out!=null)file.failWrite(out);}
            }catch(Exception ignored){}
        }
    }
    private static String hash(byte[] data)throws Exception{
        StringBuilder text=new StringBuilder();for(byte b:java.security.MessageDigest.getInstance("SHA-256").digest(data))text.append(String.format(java.util.Locale.ROOT,"%02x",b&255));return text.toString();
    }
    private static Bitmap decode(File icon){
        BitmapFactory.Options options=new BitmapFactory.Options();options.inJustDecodeBounds=true;BitmapFactory.decodeFile(icon.getPath(),options);
        if(options.outWidth<=0||options.outHeight<=0||Math.max(options.outWidth,options.outHeight)>8192)return null;
        options.inJustDecodeBounds=false;options.inSampleSize=1;
        while(Math.max(options.outWidth,options.outHeight)/options.inSampleSize>192)options.inSampleSize*=2;
        return BitmapFactory.decodeFile(icon.getPath(),options);
    }
    private static Bitmap asset(Context context,String name){
        try{
            BitmapFactory.Options options=new BitmapFactory.Options();options.inJustDecodeBounds=true;
            try(InputStream in=context.getAssets().open(name)){BitmapFactory.decodeStream(in,null,options);}
            if(options.outWidth<=0||options.outHeight<=0||Math.max(options.outWidth,options.outHeight)>8192)return null;
            options.inJustDecodeBounds=false;options.inSampleSize=1;
            while(Math.max(options.outWidth,options.outHeight)/options.inSampleSize>192)options.inSampleSize*=2;
            try(InputStream in=context.getAssets().open(name)){return BitmapFactory.decodeStream(in,null,options);}
        }catch(IOException|RuntimeException ignored){return null;}
    }
    static void addTo(LinearLayout row,String id){
        Context c=row.getContext();ImageView view=new ImageView(c);view.setImageBitmap(bitmap(c,id));view.setScaleType(ImageView.ScaleType.FIT_CENTER);view.setContentDescription(new MiniGameStore(c,id).title());
        LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(Theme.px(c,32),Theme.px(c,32));params.rightMargin=Theme.px(c,10);row.addView(view,params);
    }
}
