package com.crypticnotes.mobile;
import android.content.Context;
import java.io.*;
import java.net.*;
import java.util.*;
import java.util.zip.*;
import java.security.MessageDigest;
import org.json.JSONObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

final class MatchingModuleStore {
    final Context c;final String provider;JSONObject latest;
    MatchingModuleStore(Context context){this(context,null);}
    MatchingModuleStore(Context context,String provider){c=context.getApplicationContext();this.provider=provider;}
    String id(){return provider==null?"lianghapi":provider;}
    String hash(){return c.getSharedPreferences("mobile",0).getString("matchingHash_"+id(),id().equals("lianghapi")?c.getSharedPreferences("mobile",0).getString("matchingHash",""):"");}
    boolean installed(){
        if(!c.getSharedPreferences("mobile",0).getBoolean("matchingEnabled",true))return false;
        if(provider==null)return new MatchingModuleStore(c,"lianghapi").installed()||new MatchingModuleStore(c,"zhanshi").installed();
        if(!c.getSharedPreferences("mobile",0).getBoolean("matchingEnabled_"+provider,true))return false;
        for(MapCatalog.Entry e:MapCatalog.load(c))if(e.provider.equals(provider)&&new File(c.getFilesDir(),e.source).isFile())return true;
        return false;
    }
    String version(){String value=hash();return !installed()?"未安装":value.isEmpty()?"旧版（未记录）":"库-"+value.substring(0,Math.min(12,value.length()));}
    JSONObject info()throws Exception {
        JSONObject spec=Distribution.mapCatalog();
        if(spec.has("providers")) {
            spec=spec.getJSONObject("providers").getJSONObject(id());
            if(!id().equals(spec.getString("provider")))throw new IOException("地图库作者清单不一致");
        }else if(id().equals("zhanshi"))throw new IOException("展十地图库尚未发布");
        String url=spec.getString("url"),sha=spec.getString("sha256");long size=spec.getLong("size");
        if(!Distribution.official(url)||!sha.matches("[0-9a-f]{64}")||size<=0||size>600L*1024*1024)throw new IOException("无效地图模块");
        latest=spec;return spec;
    }
    boolean updateAvailable()throws Exception{return !info().getString("sha256").equals(hash());}
    static synchronized void python(Context c){if(!Python.isStarted())Python.start(new AndroidPlatform(c));}

    /**
     * Merge a scene package shipped inside the APK (`assets/bundled/<scene>.zip`
     * + `.json`, see scripts/bundle_android_maps.py) into the installed library.
     *
     * Test builds only: release builds carry no such asset and this returns at
     * once. Runs once per package hash; author packages are not touched.
     * @return the status line to show, or null when nothing was installed
     */
    static synchronized String installBundled(Context context,MiniGameStore.Progress progress){
        Context c=context.getApplicationContext();String[] names;
        try{names=c.getAssets().list("bundled");}catch(IOException e){return null;}
        if(names==null)return null;
        String installed=null;
        for(String name:names){
            if(!name.endsWith(".json"))continue;
            try{
                JSONObject spec;
                try(InputStream in=c.getAssets().open("bundled/"+name)){spec=new JSONObject(new String(MiniGameStore.bytes(in,64*1024),java.nio.charset.StandardCharsets.UTF_8));}
                String scene=spec.getString("scene"),sha=spec.getString("sha256");
                if(!scene.matches("[a-z]+")||!sha.matches("[0-9a-f]{64}"))continue;
                if(sha.equals(c.getSharedPreferences("mobile",0).getString("bundledHash_"+scene,"")))continue;
                if(progress!=null)progress.update("正在安装内置地图：" +spec.optString("name",scene)+"…");
                File stage=new File(c.getCacheDir(),"bundled-"+UUID.randomUUID());stage.mkdirs();
                try{
                    MessageDigest hash=MessageDigest.getInstance("SHA-256");int count=0;long unpacked=0;
                    String base=new File(stage,"maps").getCanonicalPath()+File.separator;
                    byte[] raw;try(InputStream in=c.getAssets().open("bundled/"+spec.getString("asset"))){raw=MiniGameStore.bytes(in,300*1024*1024);}
                    hash.update(raw);StringBuilder digest=new StringBuilder();for(byte b:hash.digest())digest.append(String.format(Locale.ROOT,"%02x",b&255));
                    if(!sha.equals(digest.toString()))throw new IOException("内置地图包校验失败");
                    try(ZipInputStream in=new ZipInputStream(new ByteArrayInputStream(raw))){ZipEntry e;byte[] b=new byte[65536];while((e=in.getNextEntry())!=null){String entryName=e.getName().replace('\\','/');File target=new File(stage,entryName);if(!entryName.startsWith("maps/")||entryName.contains("..")||entryName.contains(":")||!target.getCanonicalPath().startsWith(base)||++count>5000)throw new IOException("无效地图文件路径");if(e.isDirectory()){target.mkdirs();continue;}target.getParentFile().mkdirs();try(OutputStream out=new FileOutputStream(target)){int n;while((n=in.read(b))!=-1){unpacked+=n;if(unpacked>600L*1024*1024)throw new IOException("内置地图包过大");out.write(b,0,n);}}}}
                    python(c);
                    int added=Python.getInstance().getModule("mobile_modules").callAttr("install_scene",c.getFilesDir().toString(),new File(stage,"maps").toString(),scene,spec.toString()).toInt();
                    for(String provider:new String[]{"lianghapi","zhanshi"})if(spec.optJSONArray("providers")!=null&&spec.optJSONArray("providers").toString().contains("\""+provider+"\""))
                        c.getSharedPreferences("mobile",0).edit().putBoolean("matchingEnabled",true).putBoolean("matchingEnabled_"+provider,true).apply();
                    c.getSharedPreferences("mobile",0).edit().putString("bundledHash_"+scene,sha).apply();
                    installed="已安装内置地图："+spec.optString("name",scene)+"（"+added+" 张）";
                    android.util.Log.i("CrypticNotes","Bundled scene installed: "+scene+", maps="+added);
                }finally{MapCatalog.invalidate();remove(stage);}
            }catch(Exception error){
                android.util.Log.e("CrypticNotes","Bundled scene install failed: "+name,error);
                installed="内置地图安装失败："+error.getMessage();
            }
        }
        return installed;
    }
    void download(MiniGameStore.Progress progress)throws Exception{
        JSONObject spec=info();String sha=spec.getString("sha256");long expected=spec.getLong("size");
        if(installed()&&sha.equals(hash()))return;
        File stage=new File(c.getCacheDir(),"matching-"+UUID.randomUUID());stage.mkdirs();File zip=new File(stage,"module.zip");
        try{
            progress.update("正在下载加页手记…");MessageDigest hash=MessageDigest.getInstance("SHA-256");long total=0;HttpURLConnection conn=MiniGameStore.connect(spec.getString("url"));
            try(InputStream in=conn.getInputStream();OutputStream out=new FileOutputStream(zip)){byte[] b=new byte[256*1024];int n;while((n=in.read(b))!=-1){total+=n;if(total>expected)throw new IOException("模块大小异常");hash.update(b,0,n);out.write(b,0,n);progress.update("下载地图模块 "+total*100/expected+"%");}}finally{conn.disconnect();}
            StringBuilder digest=new StringBuilder();for(byte b:hash.digest())digest.append(String.format(Locale.ROOT,"%02x",b&255));if(total!=expected||!sha.equals(digest.toString()))throw new IOException("模块校验失败");
            long unpacked=0;int count=0;Set<String> seen=new HashSet<>();String base=new File(stage,"maps").getCanonicalPath()+File.separator;
            try(ZipInputStream in=new ZipInputStream(new FileInputStream(zip))){ZipEntry e;byte[] b=new byte[65536];while((e=in.getNextEntry())!=null){String name=e.getName().replace('\\','/');File target=new File(stage,name);if(!name.startsWith("maps/")||name.contains("..")||name.contains(":")||!target.getCanonicalPath().startsWith(base)||!seen.add(name.toLowerCase(Locale.ROOT))||++count>20000)throw new IOException("无效地图文件路径");if(e.isDirectory()){target.mkdirs();continue;}target.getParentFile().mkdirs();try(OutputStream out=new FileOutputStream(target)){int n;while((n=in.read(b))!=-1){unpacked+=n;if(unpacked>1400L*1024*1024)throw new IOException("模块解压大小异常");out.write(b,0,n);}}}}
            progress.update("正在保留个人地图并安装…");python(c);Python.getInstance().getModule("mobile_modules").callAttr("install_provider",c.getFilesDir().toString(),new File(stage,"maps").toString(),id(),spec.toString());
            c.getSharedPreferences("mobile",0).edit().putBoolean("matchingEnabled",true).putBoolean("matchingEnabled_"+id(),true).putString("matchingHash_"+id(),sha).apply();
        }finally{MapCatalog.invalidate();remove(stage);}
    }
    void delete()throws Exception{
        python(c);
        try {
        if(provider==null){Python.getInstance().getModule("mobile_modules").callAttr("remove",c.getFilesDir().toString());c.getSharedPreferences("mobile",0).edit().putBoolean("matchingEnabled",false).apply();}
        else {Python.getInstance().getModule("mobile_modules").callAttr("remove_provider",c.getFilesDir().toString(),provider);c.getSharedPreferences("mobile",0).edit().putBoolean("matchingEnabled_"+provider,false).remove("matchingHash_"+provider).apply();}
        } finally { MapCatalog.invalidate(); }
    }
    static void remove(File p){if(p.isDirectory()){File[] children=p.listFiles();if(children!=null)for(File x:children)remove(x);}p.delete();}
}
