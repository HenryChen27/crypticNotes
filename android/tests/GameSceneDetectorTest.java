package com.crypticnotes.mobile;
import java.util.Arrays;
public class GameSceneDetectorTest {
    static void check(boolean ok){if(!ok)throw new AssertionError();}
    public static void main(String[] args){
        GameSceneDetector d=new GameSceneDetector();
        int[] a=new int[14400],b=new int[14400];boolean[] mask=new boolean[14400];
        Arrays.fill(a,0xff203040);Arrays.fill(b,0xffa0b0c0);
        check(!d.feed(a,mask));check(!d.feed(a,mask));check(d.feed(b,mask));
        d.reset();for(int i=0;i<14400;i++)mask[i]=i%160<100;
        check(!d.feed(a,mask));check(!d.feed(a,mask));
        int[] game=a.clone();for(int i=0;i<game.length;i++)if(mask[i])game[i]=b[i];
        check(!d.feed(game,mask));check(d.feed(b,mask));
        Arrays.fill(mask,true);check(!d.feed(b,mask));
        Arrays.fill(mask,false);Arrays.fill(a,0);check(!d.feed(a,mask));
        Arrays.fill(a,0xff203040);check(!d.feed(a,mask));check(!d.feed(a,mask));
        int[] animated=a.clone();for(int i=0;i<animated.length;i+=10)animated[i]=0xff243444;
        check(!d.feed(animated,mask));
        mask[0]=true;check(!d.feed(b,mask));
        // A large change on the very first pair must not need a stable warmup.
        d.reset();Arrays.fill(mask,false);
        check(!d.feed(a,mask));check(d.feed(b,mask));
        // Moderate changes must advance the baseline rather than accumulate.
        d.reset();Arrays.fill(a,0xff303030);check(!d.feed(a,mask));
        for(int level=0x3a;level<0xa0;level+=10){
            Arrays.fill(a,0xff000000|(level<<16)|(level<<8)|level);
            check(!d.feed(a,mask));
        }
        System.out.println("Stable scene, major change, overlay exclusion, black/covered frames and mask changes passed");
    }
}
