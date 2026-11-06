package com.crypticnotes.mobile;

import android.content.Context;
import android.content.SharedPreferences;
import android.view.View;
import android.widget.LinearLayout;

/**
 * Which game map, which author, which route.
 *
 * For 磷光症 each author has one difficulty so far (凉哈皮: 困难, 展十: 噩梦
 * 十四棺), so the difficulty follows the author and the route row is hidden;
 * the legacy party selector stays with the caller.
 */
final class MapLibraryChoice extends LinearLayout {
    private final SharedPreferences prefs;
    private final Theme.ChalkChoice scene, provider, route;
    private final LinearLayout providerRow, routeRow;
    Runnable changed;
    private boolean syncing;
    MapLibraryChoice(Context context) {
        super(context);setOrientation(VERTICAL);
        prefs=context.getSharedPreferences("mobile",0);
        scene=new Theme.ChalkChoice(context,new String[]{"厄运之女","磷光症"});
        provider=new Theme.ChalkChoice(context,new String[]{"凉哈皮","展十"});
        route=new Theme.ChalkChoice(context,new String[]{"全棺","速刷"});
        addView(row(context,"地图",scene));
        providerRow=row(context,"地图版本",provider);addView(providerRow);
        routeRow=row(context,"参考路线",route);addView(routeRow);
        refresh();
        scene.setListener(i->{if(syncing)return;prefs.edit().putString("scene",i==1?"linguang":"curse").apply();updateVisibility();if(changed!=null)changed.run();});
        provider.setListener(i->{if(syncing)return;prefs.edit().putString("map_provider",i==1?"zhanshi":"lianghapi").apply();updateVisibility();if(changed!=null)changed.run();});
        route.setListener(i->{if(syncing)return;prefs.edit().putString("zhanshi_route",i==1?"speed":"full").apply();if(changed!=null)changed.run();});
    }
    private LinearLayout row(Context c,String text,View control) {
        LinearLayout row=new LinearLayout(c);row.setGravity(android.view.Gravity.CENTER_VERTICAL);
        row.addView(Theme.muted(c,text),new LinearLayout.LayoutParams(Theme.px(c,82),-2));
        row.addView(control,new LinearLayout.LayoutParams(Theme.px(c,170),Theme.px(c,42)));
        return row;
    }
    View detachRoute(){removeView(routeRow);return routeRow;}
    static String sceneOf(SharedPreferences prefs){return prefs.getString("scene","curse");}
    static String providerOf(SharedPreferences prefs){return prefs.getString("map_provider","lianghapi");}
    /** The one difficulty an author offers for 磷光症 so far, or null when the player chooses. */
    static String fixedDifficulty(String scene,String provider){
        if(!scene.equals("linguang"))return null;
        return provider.equals("zhanshi")?"nightmare":"hard";
    }
    boolean isLinguang(){return scene.getIndex()==1;}
    String scene(){return isLinguang()?"linguang":"curse";}
    String provider(){return provider.getIndex()==1?"zhanshi":"lianghapi";}
    boolean isZhanshi(){return provider().equals("zhanshi");}
    /** Null while the player still picks the difficulty themselves. */
    String fixedDifficulty(){return fixedDifficulty(scene(),provider());}
    String difficulty(String legacy){String fixed=fixedDifficulty();return fixed!=null?fixed:legacy;}
    String mode(String legacy){
        if(isLinguang())return isZhanshi()?"full":null;
        return isZhanshi()?(route.getIndex()==1?"speed":"full"):legacy;
    }
    void refresh(){
        syncing=true;
        scene.setIndex(sceneOf(prefs).equals("linguang")?1:0);
        provider.setIndex(prefs.getString("map_provider","lianghapi").equals("zhanshi")?1:0);
        route.setIndex(prefs.getString("zhanshi_route","full").equals("speed")?1:0);
        updateVisibility();
        syncing=false;
    }
    private void updateVisibility(){
        providerRow.setVisibility(VISIBLE);
        routeRow.setVisibility(!isLinguang()&&isZhanshi()?VISIBLE:GONE);
    }
}
