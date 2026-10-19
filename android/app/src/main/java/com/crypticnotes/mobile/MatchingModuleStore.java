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
    static final String MANIFEST="https://github.com/HenryChen27/crypticNotes/releases/latest/download/matching-module.json";
    final Context c;
    MatchingModuleStore(Context context){c=context.getApplicationContext();}
    boolean installed(){return c.getSharedPreferences("mobile",0).getBoolean("matchingEnabled",true)&&new File(c.getFilesDir(),"maps/floors.json").isFile();}
    JSONObject info()throws Exception{HttpURLConnection conn=MiniGameStore.connect(MANIFEST);try(InputStream in=conn.getInputStream()){JSONObject spec=new JSONObject(new String(MiniGameStore.bytes(in,32768),"UTF-8"));String url=spec.getString("url"),sha=spec.getString("sha256");long size=spec.getLong("size");if(!url.startsWith("https://github.com/HenryChen27/crypticNotes/releases/download/")||!sha.matches("[0-9a-f]{64}")||size<=0||size>600L*1024*1024)throw new IOException("无效地图模块");return spec;}finally{conn.disconnect();}}
    boolean updateAvailable()throws Exception{return !info().getString("sha256").equals(c.getSharedPreferences("mobile",0).getString("matchingHash",""));}
    static synchronized void python(Context c){if(!Python.isStarted())Python.start(new AndroidPlatform(c));}
    void download(MiniGameStore.Progress progress)throws Exception{
        JSONObject spec=info();String sha=spec.getString("sha256");long expected=spec.getLong("size");
        if(installed()&&sha.equals(c.getSharedPreferences("mobile",0).getString("matchingHash","")))return;
        File stage=new File(c.getCacheDir(),"matching-"+UUID.randomUUID());stage.mkdirs();File zip=new File(stage,"module.zip");
        try{
            progress.update("正在下载加页手记…");MessageDigest hash=MessageDigest.getInstance("SHA-256");long total=0;HttpURLConnection conn=MiniGameStore.connect(spec.getString("url"));
            try(InputStream in=conn.getInputStream();OutputStream out=new FileOutputStream(zip)){byte[] b=new byte[256*1024];int n;while((n=in.read(b))!=-1){total+=n;if(total>expected)throw new IOException("模块大小异常");hash.update(b,0,n);out.write(b,0,n);progress.update("下载地图模块 "+total*100/expected+"%");}}finally{conn.disconnect();}
            StringBuilder digest=new StringBuilder();for(byte b:hash.digest())digest.append(String.format(Locale.ROOT,"%02x",b&255));if(total!=expected||!sha.equals(digest.toString()))throw new IOException("模块校验失败");
            long unpacked=0;int count=0;Set<String> seen=new HashSet<>();String base=new File(stage,"maps").getCanonicalPath()+File.separator;
            try(ZipInputStream in=new ZipInputStream(new FileInputStream(zip))){ZipEntry e;byte[] b=new byte[65536];while((e=in.getNextEntry())!=null){String name=e.getName().replace('\\','/');File target=new File(stage,name);if(!name.startsWith("maps/")||name.contains("..")||name.contains(":")||!target.getCanonicalPath().startsWith(base)||!seen.add(name.toLowerCase(Locale.ROOT))||++count>20000)throw new IOException("无效地图文件路径");if(e.isDirectory()){target.mkdirs();continue;}target.getParentFile().mkdirs();try(OutputStream out=new FileOutputStream(target)){int n;while((n=in.read(b))!=-1){unpacked+=n;if(unpacked>1400L*1024*1024)throw new IOException("模块解压大小异常");out.write(b,0,n);}}}}
            progress.update("正在保留个人地图并安装…");python(c);Python.getInstance().getModule("mobile_modules").callAttr("install",c.getFilesDir().toString(),new File(stage,"maps").toString());
            c.getSharedPreferences("mobile",0).edit().putBoolean("matchingEnabled",true).putString("matchingHash",sha).apply();
        }finally{remove(stage);}
    }
    void delete()throws Exception{python(c);Python.getInstance().getModule("mobile_modules").callAttr("remove",c.getFilesDir().toString());c.getSharedPreferences("mobile",0).edit().putBoolean("matchingEnabled",false).remove("matchingHash").apply();}
    static void remove(File p){if(p.isDirectory()){File[] children=p.listFiles();if(children!=null)for(File x:children)remove(x);}p.delete();}
}
