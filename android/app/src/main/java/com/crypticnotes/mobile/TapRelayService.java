package com.crypticnotes.mobile;
import android.accessibilityservice.*;
import android.graphics.Path;
import android.view.accessibility.AccessibilityEvent;

public class TapRelayService extends AccessibilityService {
    public static volatile TapRelayService current;
    @Override public void onServiceConnected(){current=this;}
    @Override public void onAccessibilityEvent(AccessibilityEvent event){}
    @Override public void onInterrupt(){}
    @Override public void onDestroy(){current=null;super.onDestroy();}
    public void relay(Path path,long duration,Runnable done){
        GestureDescription gesture=new GestureDescription.Builder().addStroke(
            new GestureDescription.StrokeDescription(path,0,Math.min(1500,Math.max(45,duration)))).build();
        boolean accepted=dispatchGesture(gesture,new GestureResultCallback(){
            @Override public void onCompleted(GestureDescription g){done.run();}
            @Override public void onCancelled(GestureDescription g){done.run();}
        },null);
        if(!accepted)done.run();
    }
}
