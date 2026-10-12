package com.crypticnotes.mobile;

import android.app.Activity;
import android.content.*;
import android.util.AtomicFile;
import android.widget.Toast;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** User-selected settings and mini-game backup, without APKs or screen captures. */
final class DataBackup {
    static final int EXPORT=71,IMPORT=72;
    static void choose(Activity a,boolean export){
        Intent i=new Intent(export?Intent.ACTION_CREATE_DOCUMENT:Intent.ACTION_OPEN_DOCUMENT)
            .addCategory(Intent.CATEGORY_OPENABLE).setType("application/json");
        if(export)i.putExtra(Intent.EXTRA_TITLE,"加页手记备份.json");
        a.startActivityForResult(i,export?EXPORT:IMPORT);
    }
    static byte[] read(InputStream in)throws IOException{
        try(InputStream stream=in;ByteArrayOutputStream out=new ByteArrayOutputStream()){
            byte[] block=new byte[8192];int n;
            while((n=stream.read(block))!=-1){if(out.size()+n>4*1024*1024)throw new IOException("备份文件过大");out.write(block,0,n);}
            return out.toByteArray();
        }
    }
    static boolean handle(Activity a,int request,int result,Intent data){
        if(request!=EXPORT&&request!=IMPORT)return false;
        if(result!=Activity.RESULT_OK||data==null||data.getData()==null)return true;
        try{
            if(CaptureService.current!=null||MiniGameOverlayService.running)throw new IOException("请先停止识图并退出小游戏");
            SharedPreferences prefs=a.getSharedPreferences("mobile",0);
            File game=new File(a.getFilesDir(),"minigame-saves/jellyfish/local-storage.json");
            if(request==EXPORT){
                JSONObject values=new JSONObject();
                for(Map.Entry<String,?> entry:prefs.getAll().entrySet()){
                    Object v=entry.getValue();String type=v instanceof Set?"set":v.getClass().getSimpleName();
                    values.put(entry.getKey(),new JSONObject().put("type",type).put("value",v instanceof Set?new JSONArray((Set<?>)v):v));
                }
                JSONObject backup=new JSONObject().put("format","crypticnotes-backup").put("version",1).put("preferences",values);
                if(game.isFile())backup.put("game",new JSONObject(new String(read(new FileInputStream(game)),StandardCharsets.UTF_8)));
                try(OutputStream out=a.getContentResolver().openOutputStream(data.getData())){out.write(backup.toString(2).getBytes(StandardCharsets.UTF_8));}
                Toast.makeText(a,"备份已保存",Toast.LENGTH_LONG).show();
            }else{
                JSONObject backup=new JSONObject(new String(read(a.getContentResolver().openInputStream(data.getData())),StandardCharsets.UTF_8));
                if(!"crypticnotes-backup".equals(backup.optString("format"))||backup.optInt("version")!=1)throw new IOException("不支持的备份格式");
                JSONObject values=backup.getJSONObject("preferences");SharedPreferences.Editor edit=prefs.edit();
                for(Iterator<String> keys=values.keys();keys.hasNext();){
                    String key=keys.next();JSONObject item=values.getJSONObject(key);String type=item.getString("type");
                    switch(type){
                        case "String":edit.putString(key,item.getString("value"));break;
                        case "Boolean":edit.putBoolean(key,item.getBoolean("value"));break;
                        case "Integer":edit.putInt(key,item.getInt("value"));break;
                        case "Long":edit.putLong(key,item.getLong("value"));break;
                        case "Float":edit.putFloat(key,(float)item.getDouble("value"));break;
                        case "set":JSONArray arr=item.getJSONArray("value");Set<String> set=new HashSet<>();for(int n=0;n<arr.length();n++)set.add(arr.getString(n));edit.putStringSet(key,set);break;
                        default:throw new IOException("无效的设置类型");
                    }
                }
                JSONObject saved=backup.optJSONObject("game");
                if(saved!=null){
                    for(Iterator<String> keys=saved.keys();keys.hasNext();){String key=keys.next();if(!key.startsWith("jellyfish.")||!(saved.get(key) instanceof String))throw new IOException("无效的小游戏存档");}
                    game.getParentFile().mkdirs();AtomicFile file=new AtomicFile(game);FileOutputStream out=null;
                    try{out=file.startWrite();out.write(saved.toString().getBytes(StandardCharsets.UTF_8));file.finishWrite(out);}catch(Exception e){if(out!=null)file.failWrite(out);throw e;}
                }
                if(!edit.commit())throw new IOException("设置保存失败");
                Toast.makeText(a,"备份已导入",Toast.LENGTH_LONG).show();a.recreate();
            }
        }catch(Exception e){Toast.makeText(a,"备份未完成："+e.getMessage(),Toast.LENGTH_LONG).show();}
        return true;
    }
}
