package com.crypticnotes.mobile;

import android.content.Context;
import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.List;

/**
 * Hands the two lobby regions to mobile_pvp.py, which compares the name labels
 * and the map line with the roster rendered in the lobby's own typeface. Runs
 * on the device, nothing is uploaded. Call {@link #read} from a worker thread.
 */
final class PvpBanReader {
    static final class Reading {
        final List<String> bans;final String map;
        /** Match scores, for the log: a miss cannot be diagnosed from the result alone. */
        final String raw;
        Reading(List<String> bans,String map,String raw){this.bans=bans;this.map=map;this.raw=raw;}
    }
    private final PyObject module;

    PvpBanReader(Context context){
        MatchingModuleStore.python(context);
        module=Python.getInstance().getModule("mobile_pvp");
        module.callAttr("configure",new java.io.File(context.getFilesDir(),"modules/pvp/templates").toString());
    }

    /**
     * The regions are tight RGBA rows (width*4 bytes per row). `ban` and `map` are null while no
     * ban card is up, `line` (the "前往【地图】" corner) is null when nothing is written there.
     */
    Reading read(byte[] ban,int banWidth,int banHeight,byte[] map,int mapWidth,int mapHeight,byte[] line,int lineWidth,int lineHeight) throws Exception {
        JSONObject result=new JSONObject(module.callAttr("read_strips",ban,banWidth,banHeight,map,mapWidth,mapHeight,line,lineWidth,lineHeight).toString());
        JSONArray names=result.getJSONArray("bans");
        List<String> bans=new ArrayList<>();
        for(int i=0;i<names.length();i++)bans.add(names.getString(i));
        return new Reading(bans,result.isNull("map")?null:result.getString("map"),result.optString("scores"));
    }
}
