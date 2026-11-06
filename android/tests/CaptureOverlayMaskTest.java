package com.crypticnotes.mobile;
import java.util.Arrays;
public class CaptureOverlayMaskTest {
    static void check(boolean value){if(!value)throw new AssertionError();}
    public static void main(String[] args){
        CaptureOverlayMask mask=new CaptureOverlayMask();
        int[] game=new int[14400],overlay=new int[14400];
        Arrays.fill(game,0xff102030);Arrays.fill(overlay,0xffaaccee);
        check(mask.includesOverlay(game,overlay));
        check(!mask.includesOverlay(game,overlay)); // Single-app capture: do not mask the underlying game.
        check(mask.includesOverlay(overlay,overlay)); // Whole-screen capture: exclude the visible mini-game.
        mask.reset();check(mask.includesOverlay(null,overlay));
        Arrays.fill(overlay,0);check(mask.includesOverlay(game,overlay)); // Failed/transparent preview stays conservative.
        System.out.println("Single-app versus whole-screen overlay masks passed");
    }
}
