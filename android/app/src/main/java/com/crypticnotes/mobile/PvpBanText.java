package com.crypticnotes.mobile;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * The parts of PVP ban reading that need no Android and no Python, so they run
 * on a desktop JVM (android/tests/PvpBanTextTest.java): where on the screen to
 * look, whether a frame is worth reading at all, and the frame-to-frame vote.
 * The names themselves are matched by mobile_pvp.py.
 */
final class PvpBanText {
    /**
     * Fractions of the screen HEIGHT: the lobby UI scales with height and hugs
     * the corners. The same numbers as BAN_ROI / MAP_ROI in mobile_pvp.py
     * (android/tests/pvp_contract.py checks that they agree).
     */
    static final float BAN_LEFT=0.20f,BAN_TOP=0.155f,BAN_RIGHT=1.20f,BAN_BOTTOM=0.245f;
    /** The "排位模式 - 里奥的回忆" line, measured from the RIGHT edge. */
    static final float MAP_FROM_RIGHT=1.25f,MAP_TOP=0.795f,MAP_TO_RIGHT=0.10f,MAP_BOTTOM=0.87f;

    static int[] banRegion(int width,int height){
        return new int[]{clamp((int)(BAN_LEFT*height),width),(int)(BAN_TOP*height),clamp((int)(BAN_RIGHT*height),width),(int)(BAN_BOTTOM*height)};
    }
    /**
     * The "前往【红教堂】" line at the top left: there while the survivors ban the hunter's
     * traits, before the lobby, and again while the match loads. GOTO_ROI in mobile_pvp.py.
     */
    static final float GOTO_LEFT=0.0f,GOTO_TOP=0.04f,GOTO_RIGHT=0.80f,GOTO_BOTTOM=0.17f;
    static int[] gotoRegion(int width,int height){
        return new int[]{clamp((int)(GOTO_LEFT*height),width),(int)(GOTO_TOP*height),clamp((int)(GOTO_RIGHT*height),width),(int)(GOTO_BOTTOM*height)};
    }
    /** Pale writing on a dark corner: some bright pixels, far from most. Anything else is not worth matching. */
    static boolean hasWriting(byte[] rgba){
        int bright=0,seen=0;
        for(int i=0;i+2<rgba.length;i+=12,seen++)
            if(((rgba[i]&255)*77+(rgba[i+1]&255)*150+(rgba[i+2]&255)*29>>8)>120)bright++;
        return seen>0 && bright*250>=seen && bright*5<=seen*2;
    }
    static int[] mapRegion(int width,int height){
        return new int[]{clamp(width-(int)(MAP_FROM_RIGHT*height),width),(int)(MAP_TOP*height),clamp(width-(int)(MAP_TO_RIGHT*height),width),(int)(MAP_BOTTOM*height)};
    }
    private static int clamp(int x,int width){return Math.max(0,Math.min(width,x));}

    /** Name labels are pale paper: a ban region with almost no bright pixels is not worth reading. */
    static boolean hasPaleLabel(byte[] rgba){
        int bright=0,seen=0;
        for(int i=0;i+2<rgba.length;i+=12,seen++)
            if(((rgba[i]&255)*77+(rgba[i+1]&255)*150+(rgba[i+2]&255)*29>>8)>150)bright++;
        return seen>0 && bright*50>=seen;
    }

    /**
     * How much of what is sent came off the screen rather than from the
     * player's hand, 0..1. The items are the ban slots of the lobby plus the
     * map; an item counts when it is still what was read - a banned survivor
     * that was read, a slot read as unused and left unused, a map (or no map)
     * as read. `readBans` null means nothing was read at all: 0. The hunter is
     * not an item; that one is always picked by hand.
     */
    static double recognized(List<String> readBans,String readMap,List<String> bans,String map,int slots){
        if(readBans==null)return 0;
        slots=Math.max(slots,Math.max(bans.size(),readBans.size()));
        int kept=slots-Math.max(bans.size(),readBans.size());
        for(String ban:bans)if(readBans.contains(ban))kept++;
        if(map==null?readMap==null:map.equals(readMap))kept++;
        return kept/(double)(slots+1);
    }

    /** A roster name as shown to the player: without the quotes some names carry. */
    static String plain(String name){return name==null?"":name.replaceAll("[“”\"]","");}

    /**
     * The cards slide in and out and a label can be missed in one frame, so the
     * vote is per name: a survivor counts once two frames have shown them. The
     * list is reported when it first exists and again each time it grows; names
     * keep the left-to-right order they were seen in. A quiet spell ends the lobby.
     */
    static final class Vote {
        static final long LOBBY_GAP_MS=60_000;
        private final Map<String,Integer> counts=new LinkedHashMap<>();
        private final List<String> order=new ArrayList<>();
        private int reported;
        private long lastSeen;
        private String map;
        /** Returns the list to announce now, or null. */
        List<String> feed(List<String> bans,String frameMap,long nowMs){
            if(lastSeen!=0 && nowMs-lastSeen>LOBBY_GAP_MS)reset();
            if(frameMap!=null)map=frameMap;
            if(bans.isEmpty())return null;
            lastSeen=nowMs;
            for(int i=0;i<bans.size();i++){
                String name=bans.get(i);
                counts.merge(name,1,Integer::sum);
                if(order.contains(name))continue;
                // Slot a new name in next to its neighbour in this frame.
                int slot=order.size();
                for(int j=i-1;j>=0;j--){int at=order.indexOf(bans.get(j));if(at>=0){slot=at+1;break;}}
                if(slot==order.size())for(int j=i+1;j<bans.size();j++){int at=order.indexOf(bans.get(j));if(at>=0){slot=at;break;}}
                order.add(slot,name);
            }
            List<String> confirmed=new ArrayList<>();
            for(String name:order)if(counts.get(name)>=2)confirmed.add(name);
            if(confirmed.size()<=reported)return null;
            reported=confirmed.size();
            return confirmed;
        }
        String map(){return map;}
        void reset(){counts.clear();order.clear();reported=0;lastSeen=0;map=null;}
    }
}
