package com.crypticnotes.mobile;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArraySet;

/**
 * The Android half of the mailbox (the rules are in Mailbox): keeps the last
 * good list and the read state in files/mail/mailbox.json, and talks to the
 * PVP server on worker threads.
 *
 * Signed like /predict when this installation already has its PVP key, and
 * unsigned when it does not - mail is no reason to make one. Every failure is
 * silent: the list on screen stays the last one, with one quiet line saying
 * so. Nothing here shows a dialog, a toast or a notification.
 */
final class MailboxSync {
    private static final int CONNECT_MS=5000,READ_MS=8000;
    private static final Object WORK=new Object();
    private static final Set<Runnable> listeners=new CopyOnWriteArraySet<>();
    private static final Handler main=new Handler(Looper.getMainLooper());
    private static Mailbox box;
    private static long attempted;
    private static boolean running;

    /** The mailbox, read from its file the first time. Cheap after that; the startup thread makes the first call. */
    static synchronized Mailbox box(Context context){
        if(box==null){
            String saved=null;
            File file=file(context);
            if(file.isFile())try(InputStream in=new FileInputStream(file)){saved=new String(read(in),StandardCharsets.UTF_8);}
            catch(Exception error){android.util.Log.w("CrypticNotes","Mailbox cache unreadable",error);}
            box=Mailbox.restore(saved);
            org.json.JSONObject delivery=ReviewDelivery.read(context);
            if(delivery!=null)box.applyReview(delivery.toString());
            if(box.hasEvictions()){
                String retained=box.save();
                if(!retained.equals(saved))try{save(context,retained);}
                catch(Exception error){android.util.Log.w("CrypticNotes","Mailbox cache not trimmed",error);}
            }
        }
        return box;
    }
    private static File file(Context context){return new File(context.getFilesDir(),"mail/mailbox.json");}

    /** Called on the main thread after anything in the mailbox changed. */
    static void observe(Runnable listener){listeners.add(listener);}
    static void unobserve(Runnable listener){listeners.remove(listener);}
    private static void changed(){main.post(()->{for(Runnable listener:listeners)listener.run();});}

    /** Milliseconds since the last refresh was started; huge when there has been none in this process. */
    static synchronized long age(){return attempted==0?Long.MAX_VALUE:SystemClock.elapsedRealtime()-attempted;}

    /** Asks the server, unless one is already asking or the last time was less than minAgeMs ago. Any thread. */
    static void refresh(Context context,long minAgeMs){
        final Context app=context.getApplicationContext();
        synchronized(MailboxSync.class){
            if(running||age()<minAgeMs)return;
            running=true;attempted=SystemClock.elapsedRealtime();
        }
        new Thread(()->{
            try{
                synchronized(WORK){
                    Mailbox mailbox=box(app);
                    mailbox.refresh(transport(),PvpClient.client(app),System.currentTimeMillis()/1000);
                    save(app,mailbox.save());
                }
            }catch(Throwable error){android.util.Log.w("CrypticNotes","Mailbox refresh failed",error);}
            finally{synchronized(MailboxSync.class){running=false;}changed();}
        },"mailbox-refresh").start();
    }

    /** The player opened a mail: read here at once, the server told in the background. Main thread. */
    static void open(Context context,long id){
        if(box(context).open(id)){changed();deliver(context);}
    }
    /** 一键已读. Returns how many must-open mails are still unread. Main thread. */
    static int markAll(Context context){
        Mailbox mailbox=box(context);
        int before=mailbox.unread(),left=mailbox.markAll();
        if(mailbox.unread()!=before){changed();deliver(context);}
        return left;
    }
    private static void deliver(Context context){
        final Context app=context.getApplicationContext();
        new Thread(()->{
            try{
                synchronized(WORK){
                    Mailbox mailbox=box(app);
                    // First to disk, so what was read stays read whatever the network does.
                    save(app,mailbox.save());
                    mailbox.deliver(transport(),PvpClient.client(app),System.currentTimeMillis()/1000);
                    save(app,mailbox.save());
                }
            }catch(Throwable error){android.util.Log.w("CrypticNotes","Mailbox receipt not sent",error);}
        },"mailbox-receipt").start();
    }

    private static void save(Context context,String contents) throws Exception {
        File file=file(context),fresh=new File(file.getPath()+".new");
        file.getParentFile().mkdirs();
        try(OutputStream out=new FileOutputStream(fresh)){out.write(contents.getBytes(StandardCharsets.UTF_8));}
        if(!fresh.renameTo(file)){file.delete();if(!fresh.renameTo(file))throw new java.io.IOException("mailbox cache not replaced");}
    }

    private static Mailbox.Transport transport(){
        final boolean keyed=PvpSigner.hasKey();
        return new Mailbox.Transport(){
            public boolean signed(){return keyed;}
            public String post(String path,String body) throws Exception {
                byte[] bytes=body.getBytes(StandardCharsets.UTF_8);
                String[] signed=keyed?PvpSigner.signExisting(path,bytes):null;
                // A receipt without a signature does nothing on the server; failing here keeps it for later.
                if(signed==null&&!path.equals("/mail"))throw new java.io.IOException("receipt not signed");
                String url=PvpClient.SERVER+path;
                HttpURLConnection connection=(HttpURLConnection)new URL(url).openConnection();
                try{
                    connection.setConnectTimeout(CONNECT_MS);connection.setReadTimeout(READ_MS);
                    connection.setRequestMethod("POST");connection.setDoOutput(true);
                    connection.setRequestProperty("Content-Type","application/json; charset=utf-8");
                    if(signed!=null){connection.setRequestProperty("X-Pvp-Key",signed[0]);connection.setRequestProperty("X-Pvp-Signature",signed[1]);}
                    try(OutputStream out=connection.getOutputStream()){out.write(bytes);}
                    int status=connection.getResponseCode();
                    if(status==400)throw new Mailbox.Rejected("HTTP 400 from "+url);
                    if(status/100!=2)throw new java.io.IOException("HTTP "+status+" from "+url);
                    try(InputStream in=connection.getInputStream()){return new String(read(in),StandardCharsets.UTF_8);}
                }finally{connection.disconnect();}
            }
        };
    }
    private static byte[] read(InputStream in) throws Exception {
        ByteArrayOutputStream bytes=new ByteArrayOutputStream();byte[] chunk=new byte[4096];
        for(int n;(n=in.read(chunk))>0;){bytes.write(chunk,0,n);if(bytes.size()>1<<20)throw new java.io.IOException("mailbox answer too large");}
        return bytes.toByteArray();
    }
}
