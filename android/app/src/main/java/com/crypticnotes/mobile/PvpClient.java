package com.crypticnotes.mobile;

import android.content.Context;
import android.content.SharedPreferences;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * Talks to the hunter-prediction server. Worker threads only.
 *
 *   POST {server}/predict   {"version":1,"client":id,"rank":"六阶","map":"里奥的回忆","bans":["祭司","小说家","逃脱大师"],"recognized":0.75,"time":1763500000}
 *        -> {"id":"<match id>","hunters":[{"name":"红夫人","p":0.21}, ...]}
 *   POST {server}/report    the same fields plus "id" (echoed from /predict, may be null) and "hunter":"红夫人"
 *        -> any 2xx
 *
 * Names travel without the quotes some carry in the game. "client" is a random
 * id made on first use, so the server can cap one contributor's weight; it says
 * nothing else about the player. "map" is null when it was not read or left
 * blank, "rank" is null when not chosen, and "bans" holds only the slots the
 * hunter used (it may be empty). "recognized" is the share, 0..1 to two
 * places, of the ban slots and the map that are still as read off the screen
 * rather than set by the player's hand (PvpBanText.recognized); the hunter in
 * a report is always by hand and is not counted. "time" is when the body was
 * made, in seconds; a report kept for later keeps the time it was made.
 *
 * Every request is signed with this installation's own key (PvpSigner), in
 * the X-Pvp-Key and X-Pvp-Signature headers.
 *
 * The server address is fixed (SERVER). While the server cannot be reached,
 * or what it says holds no usable number, the list
 * still comes: the bundled pick rates of the player's rank (PvpRoster.pickRates),
 * most picked first. An answer given then is kept in files/pvp/reports.jsonl
 * and sent with the next report that gets through.
 */
final class PvpClient {
    static final class Prediction {
        String id;
        List<PvpRanking.Guess> hunters;
        /** Null when the server answered; otherwise why the order is only the default one. */
        String offline;
        /**
         * True when the numbers are the bundled pick rates at the player's rank rather than
         * the server's answer: no server, no reply, or a reply with no usable numbers in it.
         */
        boolean defaults;
    }
    private static final int VERSION=1,CONNECT_MS=5000,READ_MS=8000,QUEUE_LIMIT=500;

    /** The prediction server. Fixed: every installation talks to the same one, and there is nothing for a player to set. */
    static final String SERVER="https://pvp.smgfxyjq.cfd";
    static String server(Context context){return SERVER;}
    static String client(Context context){
        SharedPreferences prefs=context.getSharedPreferences("mobile",0);
        String id=prefs.getString("pvp_client",null);
        if(id==null){id=UUID.randomUUID().toString();prefs.edit().putString("pvp_client",id).apply();}
        return id;
    }
    private static JSONObject body(Context context,String rank,String map,List<String> bans,double recognized) throws Exception {
        JSONArray names=new JSONArray();
        for(String ban:bans)names.put(PvpBanText.plain(ban));
        return new JSONObject().put("version",VERSION).put("client",client(context)).put("rank",rank)
                .put("map",map==null?JSONObject.NULL:map).put("bans",names).put("recognized",Math.round(Math.max(0,Math.min(1,recognized))*100)/100.0).put("time",System.currentTimeMillis()/1000);
    }

    static Prediction predict(Context context,String rank,String map,List<String> bans,double recognized) throws Exception {
        PvpRoster roster=PvpRoster.get(context);
        Prediction prediction=new Prediction();
        List<String> names=new ArrayList<>();List<Double> probabilities=new ArrayList<>();
        String server=server(context);
        if(server.isEmpty())prediction.offline="未设置服务器，按默认顺序";
        else try{
            JSONObject answer=new JSONObject(post(server,"/predict",body(context,rank,map,bans,recognized)));
            prediction.id=answer.isNull("id")?null:answer.optString("id",null);
            JSONArray hunters=answer.getJSONArray("hunters");
            for(int i=0;i<hunters.length();i++){
                JSONObject hunter=hunters.getJSONObject(i);
                names.add(hunter.getString("name"));probabilities.add(hunter.optDouble("p",0));
            }
        }catch(Exception error){
            android.util.Log.w("CrypticNotes","PVP predict failed",error);
            names.clear();probabilities.clear();
            prediction.offline="服务器没有回应，按默认顺序";
        }
        prediction.hunters=PvpRanking.order(roster.hunters,names,probabilities);
        if(PvpRanking.leading(prediction.hunters,1).isEmpty()){
            // Nothing to go on from the server - no reply, or a reply without a single usable number:
            // show how often each hunter is picked at this rank, most picked first.
            names.clear();probabilities.clear();
            for(java.util.Map.Entry<String,Double> rate:roster.pickRates(rank).entrySet()){names.add(rate.getKey());probabilities.add(rate.getValue());}
            prediction.defaults=true;
            if(prediction.offline!=null)prediction.offline=prediction.offline.replace("按默认顺序","按本段位出场率排列");
            else prediction.offline="服务器的回应无效，按本段位出场率排列";
        }
        prediction.hunters=PvpRanking.order(roster.hunters,names,probabilities);
        return prediction;
    }

    /** True when the server took it now; false when it was put aside for later. */
    static boolean report(Context context,Prediction prediction,String rank,String map,List<String> bans,double recognized,String hunter) throws Exception {
        JSONObject report=body(context,rank,map,bans,recognized).put("id",prediction==null||prediction.id==null?JSONObject.NULL:prediction.id)
                .put("hunter",PvpBanText.plain(hunter));
        String server=server(context);
        File queue=new File(context.getFilesDir(),"pvp/reports.jsonl");
        synchronized(PvpClient.class){
            List<String> waiting=lines(queue);
            waiting.add(report.toString());
            int sent=0;
            if(!server.isEmpty())try{
                for(String line:waiting){post(server,"/report",new JSONObject(line));sent++;}
            }catch(Exception error){
                android.util.Log.w("CrypticNotes","PVP report failed after "+sent+" sent",error);
            }
            List<String> left=waiting.subList(sent,waiting.size());
            if(left.size()>QUEUE_LIMIT)left=left.subList(left.size()-QUEUE_LIMIT,left.size());
            if(left.isEmpty())queue.delete();
            else{
                queue.getParentFile().mkdirs();
                try(OutputStream out=new FileOutputStream(queue)){
                    for(String line:left)out.write((line+"\n").getBytes(StandardCharsets.UTF_8));
                }
            }
            return left.isEmpty();
        }
    }
    static int waiting(Context context){
        synchronized(PvpClient.class){return lines(new File(context.getFilesDir(),"pvp/reports.jsonl")).size();}
    }
    private static List<String> lines(File file){
        List<String> out=new ArrayList<>();
        if(!file.isFile())return out;
        try(InputStream in=new java.io.FileInputStream(file)){
            for(String line:new String(read(in),StandardCharsets.UTF_8).split("\n"))if(!line.trim().isEmpty())out.add(line.trim());
        }catch(Exception error){android.util.Log.w("CrypticNotes","PVP report queue unreadable",error);}
        return out;
    }

    private static String post(String server,String path,JSONObject body) throws Exception {
        String url=server+path;
        byte[] bytes=body.toString().getBytes(StandardCharsets.UTF_8);
        String[] signed=PvpSigner.sign(path,bytes);
        HttpURLConnection connection=(HttpURLConnection)new URL(url).openConnection();
        try{
            connection.setConnectTimeout(CONNECT_MS);connection.setReadTimeout(READ_MS);
            connection.setRequestMethod("POST");connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type","application/json; charset=utf-8");
            if(signed!=null){connection.setRequestProperty("X-Pvp-Key",signed[0]);connection.setRequestProperty("X-Pvp-Signature",signed[1]);}
            try(OutputStream out=connection.getOutputStream()){out.write(bytes);}
            int status=connection.getResponseCode();
            if(status/100!=2)throw new java.io.IOException("HTTP "+status+" from "+url);
            try(InputStream in=connection.getInputStream()){return new String(read(in),StandardCharsets.UTF_8);}
        }finally{connection.disconnect();}
    }
    private static byte[] read(InputStream in) throws Exception {
        ByteArrayOutputStream bytes=new ByteArrayOutputStream();byte[] chunk=new byte[4096];
        for(int n;(n=in.read(chunk))>0;){bytes.write(chunk,0,n);if(bytes.size()>1<<20)throw new java.io.IOException("response too large");}
        return bytes.toByteArray();
    }
}
