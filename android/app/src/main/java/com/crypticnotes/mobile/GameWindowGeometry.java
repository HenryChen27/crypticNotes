package com.crypticnotes.mobile;
/** Keep the game's native viewport ratio at every size, including fullscreen. */
final class GameWindowGeometry {
    static final double RATIO=2559.0/1441;
    static int fitWidth(int desired,int screenWidth,int screenHeight,int minimum){
        int maximum=Math.min(screenWidth,(int)Math.floor(screenHeight*RATIO));
        return Math.max(Math.min(minimum,maximum),Math.min(maximum,desired));
    }
    static int height(int width){return Math.max(1,(int)Math.round(width/RATIO));}
}
