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
    String id(){return provider==null||"original".equals(provider)?"notes":provider;}
    static String assetName(String id){
        switch(id){case "notes":return "IdentityVMapAssistant-Notes.zip";case "games":return "IdentityVMapAssistant-Games-Android.zip";case "pvp":return "IdentityVMapAssistant-PVP.zip";case "lianghapi":case "zhanshi":return "IdentityVMapAssistant-Maps-"+id+".zip";default:throw new IllegalArgumentException("未知模块");}
    }
    String hash(){return c.getSharedPreferences("mobile",0).getString("matchingHash_"+id(),id().equals("lianghapi")?c.getSharedPreferences("mobile",0).getString("matchingHash",""):"");}
    boolean installed(){
        if("pvp".equals(provider)){
            File folder=new File(c.getFilesDir(),"modules/pvp");
            for(String file:new String[]{"package.json","pvp-roster.json","pvp-pickrates.json","templates/index.json","templates/sheet.png"})if(!new File(folder,file).isFile())return false;
            return true;
        }
        if(id().equals("notes")||id().equals("games")){
            File live=new File(c.getFilesDir(),"modules/"+id());if(!new File(live,"package.json").isFile())return false;
            if(id().equals("games")){for(String name:new String[]{"host-audio.js","host-performance.js","host-animation-cache.js","safe-exit.js"})if(!new File(live,name).isFile())return false;}
            else for(String scene:new String[]{"curse","linguang"})for(String level:MapLibraryChoice.levels(scene,"original"))for(String name:new String[]{"art.npz","layouts.npz"})if(!new File(live,"maps/"+scene+"/original/"+level+"/"+name).isFile())return false;
            return true;
        }
        if(!new MatchingModuleStore(c,"notes").installed()||hash().isEmpty())return false;
        if(!c.getSharedPreferences("mobile",0).getBoolean("matchingEnabled",true))return false;
        if(!c.getSharedPreferences("mobile",0).getBoolean("matchingEnabled_"+provider,true))return false;
        return new File(c.getFilesDir(),"maps/packages/"+provider+".json").isFile();
    }
    JSONObject receipt(){
        String key=id();File file=new File(c.getFilesDir(),ModuleUpdates.core(key)?"modules/"+key+"/package.json":"maps/packages/"+key+".json");
        try{return new JSONObject(MiniGameStore.read(file));}catch(Exception ignored){return new JSONObject();}
    }
    static String version(JSONObject spec,String hash){
        return spec!=null&&!spec.optString("version").isEmpty()?spec.optString("version"):hash.substring(0,Math.min(12,hash.length()));
    }
    JSONObject info()throws Exception {
        String name=assetName(id());
        if(BuildConfig.LOCAL_REVIEW){
            try(InputStream input=c.getAssets().open("module-review.json")){
                JSONObject spec=new JSONObject(new String(MiniGameStore.bytes(input,16384),java.nio.charset.StandardCharsets.UTF_8)).getJSONObject(id());
                if(!name.equals(spec.getString("asset")))throw new IOException("审查包清单不一致");
                latest=spec.put("review",true);return latest;
            }catch(FileNotFoundException missing){
                throw new IOException("审查版缺少模块清单，请使用配套的审查 APK",missing);
            }
        }
        if("pvp".equals(provider)&&!BuildConfig.GRAY_PVP_URL.isEmpty()){
                latest=new JSONObject().put("sha256",BuildConfig.GRAY_PVP_SHA256).put("size",BuildConfig.GRAY_PVP_BYTES).put("url",BuildConfig.GRAY_PVP_URL);
                return latest;
        }
        JSONObject asset=Distribution.asset(Distribution.release(name),name);
        latest=new JSONObject().put("provider",id()).put("sha256",asset.getString("digest").substring(7).toLowerCase(Locale.ROOT)).put("size",asset.getLong("size")).put("url",asset.getString("browser_download_url"));return latest;
    }
    boolean updateAvailable()throws Exception{return !info().getString("sha256").equals(hash());}
    private InputStream openReviewArchive()throws IOException{
        String name=assetName(id());
        File storage=c.getExternalFilesDir(null);
        if(storage==null)throw new IOException("审查版的本地存储暂不可用，请稍后重试");
        try{return new FileInputStream(new File(storage,"review-packages/"+name));}
        catch(FileNotFoundException missing){throw new IOException("无法读取本地审查附件："+name+"。请从电脑同步本版附件后重试。",missing);}
    }
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
        boolean author=id().equals("lianghapi")||id().equals("zhanshi");
        if(author&&!new MatchingModuleStore(c).installed())throw new IOException("请先下载加页手记主程序");
        JSONObject spec=info();String sha=spec.getString("sha256");long expected=spec.getLong("size");
        if(!sha.matches("[0-9a-f]{64}")||expected<=0||expected>(id().equals("pvp")?32L:600L)*1024*1024)throw new IOException("模块校验信息无效");
        if(installed()&&sha.equals(hash()))return;
        JSONObject oldReceipt=receipt();
        String previous=oldReceipt.optString("sha256",installed()?hash():"");
        File stage=new File(c.getCacheDir(),"matching-"+UUID.randomUUID());stage.mkdirs();File zip=new File(stage,"module.zip");
        try{
            progress.update("正在下载…");MessageDigest hash=MessageDigest.getInstance("SHA-256");long total=0;
            boolean local=BuildConfig.LOCAL_REVIEW&&spec.optBoolean("review");String url=spec.optString("url");HttpURLConnection conn=local?null:MiniGameStore.connect(url,!("pvp".equals(provider)&&url.equals(BuildConfig.GRAY_PVP_URL)));
            try(InputStream in=local?openReviewArchive():conn.getInputStream();OutputStream out=new FileOutputStream(zip)){byte[] b=new byte[256*1024];int n,last=-1;while((n=in.read(b))!=-1){total+=n;if(total>expected)throw new IOException("模块大小异常");hash.update(b,0,n);out.write(b,0,n);int pct=(int)(total*100/expected);if(last!=pct){last=pct;progress.update("下载 "+pct+"%");}}}finally{if(conn!=null)conn.disconnect();}
            StringBuilder digest=new StringBuilder();for(byte b:hash.digest())digest.append(String.format(Locale.ROOT,"%02x",b&255));if(total!=expected||!sha.equals(digest.toString()))throw new IOException("模块校验失败");
            if(id().equals("notes")||id().equals("games")){
                boolean fresh=!installed();progress.update("正在安装主程序…");python(c);
                Python.getInstance().getModule("mapmatching.module_payload").callAttr("install",c.getFilesDir().toString(),id(),zip.toString(),expected,sha);
                android.content.SharedPreferences.Editor edit=c.getSharedPreferences("mobile",0).edit().putString("matchingHash_"+id(),sha);
                if(fresh&&id().equals("notes"))edit.putString("map_provider","original");edit.apply();
                PackageEvents.installed(c,id(),previous,sha,spec.optString("version"));return;
            }
            if("pvp".equals(provider)){
                progress.update("正在安装禁选辅助…");
                python(c);Python.getInstance().getModule("mapmatching.pvp_package").callAttr("install",c.getFilesDir().toString(),zip.toString(),expected,sha);
                PvpRoster.invalidate();c.getSharedPreferences("mobile",0).edit().putString("matchingHash_pvp",sha).apply();
                PackageEvents.installed(c,id(),previous,sha,spec.optString("version"));return;
            }
            long unpacked=0;int count=0;Set<String> seen=new HashSet<>();String base=new File(stage,"maps").getCanonicalPath()+File.separator;
            try(ZipInputStream in=new ZipInputStream(new FileInputStream(zip))){ZipEntry e;byte[] b=new byte[65536];while((e=in.getNextEntry())!=null){String name=e.getName().replace('\\','/');File target=new File(stage,name);if(!name.startsWith("maps/")||name.contains("..")||name.contains(":")||!target.getCanonicalPath().startsWith(base)||!seen.add(name.toLowerCase(Locale.ROOT))||++count>20000)throw new IOException("无效地图文件路径");if(e.isDirectory()){target.mkdirs();continue;}target.getParentFile().mkdirs();try(OutputStream out=new FileOutputStream(target)){int n;while((n=in.read(b))!=-1){unpacked+=n;if(unpacked>1400L*1024*1024)throw new IOException("模块解压大小异常");out.write(b,0,n);}}}}
            progress.update("正在保留个人地图并安装…");python(c);Python.getInstance().getModule("mobile_modules").callAttr("install_provider",c.getFilesDir().toString(),new File(stage,"maps").toString(),id(),spec.toString());
            c.getSharedPreferences("mobile",0).edit().putBoolean("matchingEnabled",true).putBoolean("matchingEnabled_"+id(),true).putString("matchingHash_"+id(),sha).apply();
            PackageEvents.installed(c,id(),previous,sha,spec.optString("version"));
        }finally{MapCatalog.invalidate();remove(stage);}
    }
    void delete()throws Exception{
        if(id().equals("notes")||id().equals("games")){
            if(id().equals("notes")){
                for(String child:new String[]{"lianghapi","zhanshi"})if(new File(c.getFilesDir(),"maps/packages/"+child+".json").isFile())new MatchingModuleStore(c,child).delete();
                c.getSharedPreferences("mobile",0).edit().putString("map_provider","original").apply();
            }else for(String game:GameCatalog.ids(c)){MiniGameStore store=new MiniGameStore(c,game);if(store.installed())store.delete();}
            python(c);Python.getInstance().getModule("mapmatching.module_payload").callAttr("remove",c.getFilesDir().toString(),id());
            c.getSharedPreferences("mobile",0).edit().remove("matchingHash_"+id()).apply();return;
        }
        if("pvp".equals(provider)){
            File folder=new File(c.getFilesDir(),"modules/pvp");remove(folder);if(folder.exists())throw new IOException("PVP 包未能完全删除");
            PvpRoster.invalidate();c.getSharedPreferences("mobile",0).edit().remove("matchingHash_pvp").apply();return;
        }
        python(c);
        try {
        Python.getInstance().getModule("mobile_modules").callAttr("remove_provider",c.getFilesDir().toString(),provider);
        android.content.SharedPreferences prefs=c.getSharedPreferences("mobile",0);android.content.SharedPreferences.Editor edit=prefs.edit().putBoolean("matchingEnabled_"+provider,false).remove("matchingHash_"+provider);
        if(provider.equals(MapLibraryChoice.providerOf(prefs)))edit.putString("map_provider","original");edit.apply();
        } finally { MapCatalog.invalidate(); }
    }
    static void remove(File p){if(p.isDirectory()){File[] children=p.listFiles();if(children!=null)for(File x:children)remove(x);}p.delete();}
}
