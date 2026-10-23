package com.crypticnotes.mobile;
import android.accessibilityservice.AccessibilityService;
import android.view.accessibility.AccessibilityEvent;

/** Legacy component retained for installed users. Never intercepts or injects touch. */
public class TapRelayService extends AccessibilityService {
    public static volatile TapRelayService current;
    @Override public void onServiceConnected(){current=this;}
    @Override public void onAccessibilityEvent(AccessibilityEvent event){}
    @Override public void onInterrupt(){}
    @Override public void onDestroy(){current=null;super.onDestroy();}
}
