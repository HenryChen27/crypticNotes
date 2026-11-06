package com.crypticnotes.mobile;
public class GameWindowGeometryTest {
    public static void main(String[] args){
        if(GameWindowGeometry.swipeAction(500,540,1000,1)!=0
            ||GameWindowGeometry.swipeAction(500,560,1000,1)!=1
            ||GameWindowGeometry.swipeAction(980,980,1000,1)!=0
            ||GameWindowGeometry.swipeAction(980,990,1000,1)!=1
            ||GameWindowGeometry.swipeAction(990,995,1000,1)!=1
            ||GameWindowGeometry.swipeAction(500,440,1000,1)!=-1
            ||GameWindowGeometry.swipeAction(2970,2985,3000,3)!=1)throw new AssertionError("Swipe edge/threshold regression");
        for(int[] screen:new int[][]{{2400,1080},{1080,2400},{800,360},{320,200}})
            for(int desired:new int[]{-100,1,200,600,2400,Integer.MAX_VALUE}){
                int width=GameWindowGeometry.fitWidth(desired,screen[0],screen[1],200),height=GameWindowGeometry.height(width);
                if(width<=0||height<=0||width>screen[0]||height>screen[1]||Math.abs(height-width/GameWindowGeometry.RATIO)>.51)throw new AssertionError();
            }
        System.out.println("Portrait, landscape, minimum and fullscreen preserve ratio and screen bounds");
    }
}
