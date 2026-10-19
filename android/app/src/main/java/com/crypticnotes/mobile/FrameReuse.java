package com.crypticnotes.mobile;
final class FrameReuse {
    static boolean same(int[] a,int[] b,boolean controlsOnly){
        if(a==null||b==null||a.length!=14400||b.length!=14400)return false;
        for(int y=0;y<90;y++)for(int x=0;x<160;x++){
            boolean controls=(x>=88&&y<23)||(x>=137&&y>=18&&y<50)||(x>=104&&y>=65);
            boolean map=x>=65&&x<138&&y>=10&&y<79;
            if((controls||(!controlsOnly&&map))&&a[y*160+x]!=b[y*160+x])return false;
        }
        return true;
    }
}
