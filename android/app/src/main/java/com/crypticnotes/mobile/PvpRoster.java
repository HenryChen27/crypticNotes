package com.crypticnotes.mobile;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

/**
 * The bundled PVP roster (assets/pvp-roster.json): survivors, hunters, maps,
 * ranks, and each character's small portrait (assets/pvp/avatars, fetched by
 * scripts/fetch_pvp_avatars.py). Loaded once per process.
 */
final class PvpRoster {
    final String[] survivors,hunters,maps,ranks;
    private final Map<String,String> portraitFiles=new HashMap<>();
    private final Map<String,Bitmap> portraits=new HashMap<>();
    private final Context context;
    private static PvpRoster loaded;
    static synchronized void invalidate(){loaded=null;}
    private InputStream open(String name)throws java.io.IOException{return new java.io.FileInputStream(new java.io.File(context.getFilesDir(),"modules/pvp/"+name));}

    static synchronized PvpRoster get(Context context) throws Exception {
        if(loaded==null)loaded=new PvpRoster(context.getApplicationContext());
        return loaded;
    }

    private PvpRoster(Context context) throws Exception {
        this.context=context;
        JSONObject roster;
        try(InputStream in=open("pvp-roster.json")){
            ByteArrayOutputStream text=new ByteArrayOutputStream();byte[] chunk=new byte[4096];
            for(int n;(n=in.read(chunk))>0;)text.write(chunk,0,n);
            roster=new JSONObject(new String(text.toByteArray(),StandardCharsets.UTF_8));
        }
        survivors=strings(roster.getJSONArray("求生者"));hunters=strings(roster.getJSONArray("监管者"));
        maps=strings(roster.getJSONArray("地图"));ranks=strings(roster.getJSONArray("段位"));
        JSONObject files=roster.optJSONObject("头像");
        if(files!=null)for(java.util.Iterator<String> names=files.keys();names.hasNext();){String name=names.next();portraitFiles.put(name,files.getString(name));}
        JSONObject limits=roster.optJSONObject("禁用上限");
        if(limits!=null)for(java.util.Iterator<String> names=limits.keys();names.hasNext();){
            String rank=names.next();int limit=Math.max(0,limits.optInt(rank,3));
            banLimits.put(rank,limit);mostBans=Math.max(mostBans,limit);
        }
        if(banLimits.isEmpty())mostBans=3;
        // The default list: how often each hunter is picked at each rank (scripts/fetch_pvp_pickrates.py).
        try(InputStream in=open("pvp-pickrates.json")){
            ByteArrayOutputStream text=new ByteArrayOutputStream();byte[] chunk=new byte[4096];
            for(int n;(n=in.read(chunk))>0;)text.write(chunk,0,n);
            JSONObject bundled=new JSONObject(new String(text.toByteArray(),StandardCharsets.UTF_8));
            JSONObject byRank=bundled.optJSONObject("出场率");
            if(byRank!=null)for(java.util.Iterator<String> names=byRank.keys();names.hasNext();){
                String rank=names.next();JSONObject table=byRank.optJSONObject(rank);
                if(table!=null)pickRates.put(rank,rates(table));
            }
            JSONObject every=bundled.optJSONObject("全段");
            if(every!=null)pickRates.put("",rates(every));
        }catch(Exception error){android.util.Log.w("CrypticNotes","PVP pick rates not bundled: "+error);}
    }
    private static Map<String,Double> rates(JSONObject table){
        Map<String,Double> rates=new java.util.LinkedHashMap<>();
        for(java.util.Iterator<String> hunters=table.keys();hunters.hasNext();){String hunter=hunters.next();rates.put(hunter,table.optDouble(hunter,0));}
        return rates;
    }
    /**
     * Hunter name -> share of ranked matches it is picked in (0..1) at this
     * rank; with no rank chosen, or one the table lacks, over every rank.
     * Empty only when no table was bundled at all.
     */
    Map<String,Double> pickRates(String rank){
        Map<String,Double> rates=rank==null?null:pickRates.get(rank);
        if(rates==null)rates=pickRates.get("");
        return rates==null?java.util.Collections.<String,Double>emptyMap():rates;
    }
    private final Map<String,Map<String,Double>> pickRates=new HashMap<>();
    private final Map<String,Integer> banLimits=new HashMap<>();
    /** The most survivors a hunter may ban at any rank. */
    int mostBans;
    /**
     * How many survivors the hunter may ban in a lobby of this rank; the most
     * of any rank when the rank is not chosen. The lobby goes by the highest
     * survivor in it, which may be above the player's own rank, so this sizes
     * the empty slots shown and never drops a name that was actually read.
     */
    int banLimit(String rank){
        Integer limit=rank==null?null:banLimits.get(rank);
        return limit==null?mostBans:limit;
    }
    private static String[] strings(JSONArray array) throws Exception {
        String[] out=new String[array.length()];
        for(int i=0;i<out.length;i++)out[i]=array.getString(i);
        return out;
    }

    /** The character's portrait, or null when none was bundled (the name is then shown alone). */
    synchronized Bitmap portrait(String name){
        if(portraits.containsKey(name))return portraits.get(name);
        Bitmap bitmap=null;
        String file=portraitFiles.get(name);
        if(file!=null)try(InputStream in=open("avatars/"+file)){bitmap=BitmapFactory.decodeStream(in);}catch(Exception ignored){}
        portraits.put(name,bitmap);
        return bitmap;
    }
}
