package com.crypticnotes.mobile;

/** No screen polling outside an explicit map-opening session. */
final class TouchCaptureSession {
    private boolean awake, seen;
    private long openingDeadline;
    void wake(long now) { awake=true; seen=false; openingDeadline=now+5000; }
    boolean awake() { return awake; }
    void sleep() { awake=false; seen=false; }
    boolean openingExpired(long now){return awake && !seen && now>=openingDeadline;}
    boolean closed(boolean visible,long now) {
        if(!awake)return true;
        if(visible){seen=true;return false;}
        return seen || now>=openingDeadline;
    }
}
