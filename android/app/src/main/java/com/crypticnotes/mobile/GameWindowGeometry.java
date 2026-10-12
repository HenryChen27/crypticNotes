package com.crypticnotes.mobile;
/** Keep the game's native viewport ratio at every size, including fullscreen. */
final class GameWindowGeometry {
    static final double RATIO=2559.0/1441;
    static int fitWidth(int desired,int screenWidth,int screenHeight,int minimum){
        int maximum=Math.min(screenWidth,(int)Math.floor(screenHeight*RATIO));
        return Math.max(Math.min(minimum,maximum),Math.min(maximum,desired));
    }
    static int height(int width){return Math.max(1,(int)Math.round(width/RATIO));}
    static int swipeAction(float startY,float currentY,int screenHeight,float density){
        float delta=currentY-startY;
        if(delta<=-60*density)return -1;
        float remaining=Math.max(0,screenHeight-startY);
        float threshold=Math.min(60*density,Math.max(6*density,remaining*.4f));
        float edgeMovement=Math.min(12*density,Math.max(4*density,remaining*.15f));
        boolean atBottom=currentY>=screenHeight-24*density && delta>=edgeMovement;
        return delta>0&&(delta>=threshold||atBottom)?1:0;
    }
}
