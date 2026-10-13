package com.crypticnotes.mobile;

/** Detect whether the actual captured pixels include our window, not its screen position. */
final class CaptureOverlayMask {
    private boolean included=true;
    private int different;
    void reset(){included=true;different=0;}
    boolean includesOverlay(int[] capture,int[] overlay){
        if(capture==null||overlay==null||capture.length!=overlay.length)return included;
        int usable=0,matching=0;
        for(int i=0;i<capture.length;i++){
            int expected=overlay[i];if((expected>>>24)<200)continue;
            usable++;
            int actual=capture[i];
            int delta=(Math.abs(((actual>>16)&255)-((expected>>16)&255))
                +Math.abs(((actual>>8)&255)-((expected>>8)&255))
                +Math.abs((actual&255)-(expected&255)))/3;
            if(delta<22)matching++;
        }
        if(usable<200)return included;
        if(matching>=usable*.75){included=true;different=0;}
        else if(matching<usable*.35&&++different>=2)included=false;
        return included;
    }
}
