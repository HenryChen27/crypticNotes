package com.crypticnotes.mobile;

import java.util.Arrays;

/** Small capture signature; masked pixels never contribute to scene changes. */
final class GameSceneDetector {
    private int[] reference;
    private boolean[] mask;
    private boolean armed;
    String status(){return reference==null?"waiting for usable frame":armed?"armed":"waiting for stable reference";}
    void reset(){reference=null;mask=null;armed=false;}
    boolean feed(int[] pixels, boolean[] excluded){
        if(pixels==null||excluded==null||pixels.length!=14400||excluded.length!=pixels.length)return false;
        if(mask!=null&&!Arrays.equals(mask,excluded))reset();
        int usable=0;long light=0;
        int[] sample=pixels.clone();
        for(int y=1;y<89;y++)for(int x=1;x<159;x++){
            int r=0,g=0,b=0;
            for(int dy=-1;dy<=1;dy++)for(int dx=-1;dx<=1;dx++){int c=pixels[(y+dy)*160+x+dx];r+=(c>>16)&255;g+=(c>>8)&255;b+=c&255;}
            sample[y*160+x]=((r/9)<<16)|((g/9)<<8)|(b/9);
        }
        for(int i=0;i<sample.length;i++)if(!excluded[i]){usable++;int c=sample[i];light+=((c>>16)&255)+((c>>8)&255)+(c&255);}
        if(usable<1000||light<usable*9L){reset();return false;}
        if(reference==null){reference=sample;mask=excluded.clone();return false;}
        int changed=0;long total=0;
        for(int i=0;i<sample.length;i++)if(!excluded[i]){
            int a=reference[i],b=sample[i];
            int delta=(Math.abs(((a>>16)&255)-((b>>16)&255))+Math.abs(((a>>8)&255)-((b>>8)&255))+Math.abs((a&255)-(b&255)))/3;
            total+=delta;if(delta>18)changed++;
        }
        boolean stable=changed<usable*.08 && total<usable*6L;
        if(!armed){reference=sample;armed=stable;return false;}
        if(changed>=usable*.25 && total>=usable*12L){reset();return true;}
        if(stable)reference=sample;
        return false;
    }
}
