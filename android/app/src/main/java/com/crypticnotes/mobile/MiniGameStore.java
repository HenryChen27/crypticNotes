package com.crypticnotes.mobile;

import android.content.Context;
import org.json.JSONObject;
import java.io.*;
import java.net.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.zip.*;

/** Optional universal resource pack. Saves live outside the removable game. */
final class MiniGameStore {
    static final String CATALOG="https://github.com/HenryChen27/Jellyfish/releases/latest/download/native-desktop-games.json";
    final File root, game;
    interface Progress { void update(String text); }
    MiniGameStore(Context c){root=new File(c.getFilesDir(),"minigames");game=new File(root,"jellyfish");}
    boolean installed(){return new File(game,"game/index.html").isFile();}
    String version(){try{return new JSONObject(read(new File(game,"package.json"))).optString("version","");}catch(Exception e){return "";}}
    static byte[] bytes(InputStream in,int limit)throws IOException{ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] buf=new byte[8192];int n;while((n=in.read(buf))!=-1){if(out.size()+n>limit)throw new IOException("文件过大");out.write(buf,0,n);}return out.toByteArray();}
    static String read(File f)throws IOException{try(InputStream in=new FileInputStream(f)){return new String(bytes(in,1024*1024),java.nio.charset.StandardCharsets.UTF_8);}}
    static HttpURLConnection connect(String address)throws IOException{
        if(!address.startsWith("https://"))throw new IOException("下载地址不安全");
        HttpURLConnection c=(HttpURLConnection)new URL(address).openConnection();c.setConnectTimeout(20000);c.setReadTimeout(30000);c.setRequestProperty("User-Agent","CrypticNotes-mini-games");
        if(c.getResponseCode()!=200){c.disconnect();throw new IOException("下载失败，请稍后重试");}return c;
    }
    JSONObject catalogInfo()throws Exception{
        JSONObject catalog;
        HttpURLConnection c=connect(CATALOG);
        try(InputStream in=c.getInputStream()){byte[] raw=bytes(in,128*1024);catalog=new JSONObject(new String(raw,java.nio.charset.StandardCharsets.UTF_8));}finally{c.disconnect();}
        if(catalog.optInt("schema")!=2||!"jellyfish".equals(catalog.optString("id")))throw new IOException("无效游戏清单");
        JSONObject info=catalog.getJSONObject("game");String url=info.getString("url"),sha=info.getString("sha256");long size=info.getLong("size");
        if(!url.startsWith("https://github.com/HenryChen27/Jellyfish/releases/download/")||!sha.matches("[0-9a-f]{64}")||size<=0||size>600L*1024*1024)throw new IOException("无效游戏包");
        return info;
    }
    void download(Progress progress)throws Exception{
        root.mkdirs();progress.update("正在检查游戏更新…");
        JSONObject info=catalogInfo();String url=info.getString("url"),sha=info.getString("sha256"),version=info.getString("version");long size=info.getLong("size");
        HttpURLConnection c;
        if(installed()&&version.equals(version())){progress.update("游戏已是最新版");return;}
        File zip=new File(root,"download.zip"),stage=new File(root,".install-"+UUID.randomUUID()),backup=new File(root,".previous-jellyfish");
        try {
            MessageDigest digest=MessageDigest.getInstance("SHA-256");long count=0;c=connect(url);
            try(InputStream in=c.getInputStream();OutputStream out=new FileOutputStream(zip)){
                byte[] buf=new byte[256*1024];int n,last=-1;
                while((n=in.read(buf))!=-1){count+=n;if(count>size)throw new IOException("游戏包大小异常");out.write(buf,0,n);digest.update(buf,0,n);int pct=(int)(count*100/size);if(pct!=last){last=pct;progress.update("下载游戏 "+pct+"%");}}
            }finally{c.disconnect();}
            StringBuilder actual=new StringBuilder();for(byte b:digest.digest())actual.append(String.format(Locale.ROOT,"%02x",b&255));
            if(count!=size||!sha.equals(actual.toString()))throw new IOException("游戏包校验失败，请重试");
            progress.update("正在安装游戏…");stage.mkdirs();long extracted=0;int entries=0;Set<String> names=new HashSet<>();
            try(ZipInputStream in=new ZipInputStream(new FileInputStream(zip))){ZipEntry e;byte[] buf=new byte[65536];
                while((e=in.getNextEntry())!=null){String name=e.getName().replace('\\','/');
                    File target=new File(stage,name);String path=target.getCanonicalPath();
                    if(!path.startsWith(stage.getCanonicalPath()+File.separator)||name.contains(":")||!names.add(name.toLowerCase(Locale.ROOT))||++entries>20000)throw new IOException("无效游戏文件路径");
                    if(e.isDirectory()){target.mkdirs();continue;}target.getParentFile().mkdirs();
                    try(OutputStream out=new FileOutputStream(target)){int n;while((n=in.read(buf))!=-1){extracted+=n;if(extracted>1400L*1024*1024)throw new IOException("游戏包解压过大");out.write(buf,0,n);}}
                }
            }
            JSONObject meta=new JSONObject(read(new File(stage,"package.json")));
            if(!"jellyfish".equals(meta.optString("id"))||!"system-webview".equals(meta.optString("runtime"))||!new File(stage,"game/index.html").isFile())throw new IOException("游戏包结构不正确");
            remove(backup);if(game.exists()&&!game.renameTo(backup))throw new IOException("旧游戏无法替换");
            if(!stage.renameTo(game)){if(backup.exists())backup.renameTo(game);throw new IOException("游戏安装失败");}remove(backup);progress.update("游戏已安装");
        }finally{zip.delete();remove(stage);}
    }
    void delete()throws IOException{remove(game);}
    void remove(File file)throws IOException{
        if(!file.getCanonicalPath().startsWith(root.getCanonicalPath()+File.separator))throw new IOException("无效删除路径");
        if(!file.exists())return;if(file.isDirectory()){File[] children=file.listFiles();if(children==null)throw new IOException("目录无法读取");for(File f:children)remove(f);}
        if(!file.delete())throw new IOException("游戏文件无法删除");
    }
}
