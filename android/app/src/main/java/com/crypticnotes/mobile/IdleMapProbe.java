package com.crypticnotes.mobile;

import android.graphics.Bitmap;
import android.graphics.PixelFormat;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.os.Handler;

/**
 * A low-resolution mirror that stays attached while recognition is idle.
 * Never observes or injects touch input.
 *
 * It used to be a pulse: attach the surface, take one frame, detach, once a
 * second. Every attach and every detach makes SurfaceFlinger tear the virtual
 * display down and build it again, and each of those cost the game one frame --
 * measured on a Xiaomi 15 Pro at 60 fps as a pair of 33 ms frames 80 ms apart,
 * every second, for as long as the floating button was up. So the surface is
 * now attached once and each check only reads the newest frame; nothing is
 * reconfigured until recognition wakes ({@link #cancel()}).
 */
final class IdleMapProbe implements AutoCloseable {
    interface Result { void ready(Bitmap frame); }
    private final Handler handler;
    private ImageReader reader;
    private VirtualDisplay owner;
    private Runnable timeout;
    private boolean active,attached;
    private int token;
    IdleMapProbe(Handler handler){this.handler=handler;}
    /** A first frame is still awaited after attaching. */
    boolean active(){return active;}
    /** The low-resolution surface is the display's current output. */
    boolean attached(){return attached;}
    /**
     * Delivers the newest low-resolution frame, or null when nothing has been
     * drawn since the last check (an unchanged screen cannot have opened the map).
     */
    void start(VirtualDisplay display,int screenWidth,int screenHeight,int density,Result result){
        int w=480,h=Math.max(1,Math.round(screenHeight*480f/screenWidth));
        if(attached && !active && owner==display && reader!=null && reader.getWidth()==w && reader.getHeight()==h){
            result.ready(latest(reader));
            return;
        }
        cancel();
        final int ticket=++token;
        if(reader==null || reader.getWidth()!=w || reader.getHeight()!=h){
            if(reader!=null)reader.close();
            reader=ImageReader.newInstance(w,h,PixelFormat.RGBA_8888,2);
        }
        try(Image stale=reader.acquireLatestImage()){}catch(Exception ignored){}
        owner=display;active=true;
        reader.setOnImageAvailableListener(source->{
            if(ticket!=token || !active)return;
            Bitmap frame=latest(source);
            if(frame!=null)finish(ticket,result,frame);
        },handler);
        timeout=()->finish(ticket,result,null);
        handler.postDelayed(timeout,350);
        try{
            display.setSurface(null);
            display.resize(w,h,density);
            display.setSurface(reader.getSurface());
            attached=true;
        }catch(RuntimeException error){cancel();throw error;}
    }
    private static Bitmap latest(ImageReader source){
        Bitmap frame=null;
        try(Image image=source.acquireLatestImage()){
            if(image==null)return null;
            Image.Plane plane=image.getPlanes()[0];
            if(plane.getPixelStride()!=4)throw new IllegalStateException("Unexpected preview pixel stride");
            frame=Bitmap.createBitmap(image.getWidth(),image.getHeight(),Bitmap.Config.ARGB_8888);
            frame.copyPixelsFromBuffer(RgbaRows.packed(plane.getBuffer(),image.getWidth(),image.getHeight(),plane.getRowStride()));
            return frame;
        }catch(Exception error){
            if(frame!=null)frame.recycle();
            android.util.Log.w("CrypticNotes","Idle capture read failed",error);
            return null;
        }
    }
    /** Ends the wait for the first frame; the surface stays attached. */
    private void finish(int ticket,Result result,Bitmap frame){
        if(ticket!=token || !active){if(frame!=null)frame.recycle();return;}
        active=false;
        if(timeout!=null){handler.removeCallbacks(timeout);timeout=null;}
        if(reader!=null)reader.setOnImageAvailableListener(null,null);
        result.ready(frame);
    }
    /** Detaches the mirror. The caller owns the display's size and surface afterwards. */
    void cancel(){
        token++;
        if(timeout!=null){handler.removeCallbacks(timeout);timeout=null;}
        if(reader!=null)reader.setOnImageAvailableListener(null,null);
        if((active || attached) && owner!=null)try{owner.setSurface(null);}catch(Exception ignored){}
        active=false;attached=false;owner=null;
    }
    @Override public void close(){cancel();if(reader!=null){reader.close();reader=null;}}
}
