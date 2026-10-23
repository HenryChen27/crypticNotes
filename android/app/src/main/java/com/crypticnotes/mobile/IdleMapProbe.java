package com.crypticnotes.mobile;

import android.graphics.Bitmap;
import android.graphics.PixelFormat;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.os.Handler;

/** A short low-resolution capture pulse. Never observes or injects touch input. */
final class IdleMapProbe implements AutoCloseable {
    interface Result { void ready(Bitmap frame); }
    private final Handler handler;
    private ImageReader reader;
    private VirtualDisplay owner;
    private Runnable timeout;
    private boolean active;
    private int token;
    IdleMapProbe(Handler handler){this.handler=handler;}
    boolean active(){return active;}
    void start(VirtualDisplay display,int screenWidth,int screenHeight,int density,Result result){
        cancel();
        final int ticket=++token;
        int w=480,h=Math.max(1,Math.round(screenHeight*480f/screenWidth));
        if(reader==null || reader.getWidth()!=w || reader.getHeight()!=h){
            if(reader!=null)reader.close();
            reader=ImageReader.newInstance(w,h,PixelFormat.RGBA_8888,2);
        }
        try(Image stale=reader.acquireLatestImage()){}catch(Exception ignored){}
        owner=display;active=true;
        reader.setOnImageAvailableListener(source->{
            if(ticket!=token || !active)return;
            Bitmap frame=null;
            try(Image image=source.acquireLatestImage()){
                if(image==null)return;
                Image.Plane plane=image.getPlanes()[0];
                if(plane.getPixelStride()!=4)throw new IllegalStateException("Unexpected preview pixel stride");
                frame=Bitmap.createBitmap(image.getWidth(),image.getHeight(),Bitmap.Config.ARGB_8888);
                frame.copyPixelsFromBuffer(RgbaRows.packed(plane.getBuffer(),image.getWidth(),image.getHeight(),plane.getRowStride()));
            }catch(Exception error){if(frame!=null){frame.recycle();frame=null;}android.util.Log.w("CrypticNotes","Idle capture pulse failed",error);}
            finish(ticket,result,frame);
        },handler);
        timeout=()->finish(ticket,result,null);
        handler.postDelayed(timeout,350);
        try{
            display.setSurface(null);
            display.resize(w,h,density);
            display.setSurface(reader.getSurface());
        }catch(RuntimeException error){cancel();throw error;}
    }
    private void finish(int ticket,Result result,Bitmap frame){
        if(ticket!=token || !active){if(frame!=null)frame.recycle();return;}
        cancel();result.ready(frame);
    }
    void cancel(){
        token++;
        if(timeout!=null){handler.removeCallbacks(timeout);timeout=null;}
        if(reader!=null)reader.setOnImageAvailableListener(null,null);
        if(active && owner!=null)try{owner.setSurface(null);}catch(Exception ignored){}
        active=false;owner=null;
    }
    @Override public void close(){cancel();if(reader!=null){reader.close();reader=null;}}
}
