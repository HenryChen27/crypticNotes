package com.crypticnotes.mobile;
import android.content.Context;
import java.io.File;
import java.util.*;
import org.json.JSONObject;
final class GameCatalog {
    static JSONObject cached(Context c){try{return new JSONObject(c.getSharedPreferences("mobile",0).getString("gameCatalog","{}"));}catch(Exception e){return new JSONObject();}}
    static java.util.List<String> ids(Context c){Set<String> ids=new LinkedHashSet<>();JSONObject catalog=cached(c);Iterator<String> it=catalog.keys();while(it.hasNext()){String id=it.next();if(id.matches("[a-z0-9][a-z0-9-]*")&&!id.equals("runtime"))ids.add(id);}File[] files=new File(c.getFilesDir(),"minigames").listFiles();if(files!=null)for(File f:files){String id=f.getName();if(!id.equals("runtime")&&id.matches("[a-z0-9][a-z0-9-]*")&&new File(f,"game/index.html").isFile())ids.add(id);}if(ids.isEmpty())ids.add("jellyfish");return new ArrayList<>(ids);}
}
