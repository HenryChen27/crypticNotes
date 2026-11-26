package com.crypticnotes.mobile;

import android.content.Context;
import android.content.SharedPreferences;
import android.view.View;
import android.widget.LinearLayout;

/**
 * Which game map, which author, which route.
 *
 * For 磷光症 both authors offer 困难 and 噩梦 (凉哈皮: one set each, no
 * solo/duo; 展十: 困难 十六棺 and 噩梦 十四棺, route "full"), so the player
 * picks the difficulty and the route and party rows stay hidden.
 */
final class MapLibraryChoice extends LinearLayout {
    static final String[] PROVIDERS={"original","lianghapi","zhanshi"};
    static final String[] NAMES={"小布偶","凉哈皮","展十"};
    private final SharedPreferences prefs;
    private final Theme.ChalkChoice scene, provider, route;
    private final LinearLayout providerRow, routeRow;
    Runnable changed;
    private boolean syncing;
    MapLibraryChoice(Context context) {
        super(context);setOrientation(VERTICAL);
        prefs=context.getSharedPreferences("mobile",0);
        scene=new Theme.ChalkChoice(context,new String[]{"厄运之女","磷光症"});
        provider=new Theme.ChalkChoice(context,NAMES);
        route=new Theme.ChalkChoice(context,new String[]{"全棺","速刷"});
        addView(row(context,"地图",scene));
        providerRow=row(context,"地图版本",provider);addView(providerRow);
        routeRow=row(context,"参考路线",route);addView(routeRow);
        refresh();
        scene.setListener(i->{if(syncing)return;prefs.edit().putString("scene",i==1?"linguang":"curse").apply();updateVisibility();if(changed!=null)changed.run();});
        provider.setListener(i->{if(syncing)return;if(!new MatchingModuleStore(context,PROVIDERS[i]).installed()){refresh();android.widget.Toast.makeText(context,"请先到加页手记 → 版本下载"+NAMES[i]+"地图库",android.widget.Toast.LENGTH_SHORT).show();return;}prefs.edit().putString("map_provider",PROVIDERS[i]).apply();updateVisibility();if(changed!=null)changed.run();});
        route.setListener(i->{if(syncing)return;prefs.edit().putString("zhanshi_route",i==1?"speed":"full").apply();if(changed!=null)changed.run();});
    }
    private LinearLayout row(Context c,String text,View control) {
        LinearLayout row=new LinearLayout(c);row.setGravity(android.view.Gravity.CENTER_VERTICAL);
        row.addView(Theme.muted(c,text),new LinearLayout.LayoutParams(Theme.px(c,82),-2));
        row.addView(control,new LinearLayout.LayoutParams(Theme.px(c,170),Theme.px(c,42)));
        return row;
    }
    View detachRoute(){removeView(routeRow);return routeRow;}
    View detachProvider(){removeView(providerRow);return providerRow;}
    static String sceneOf(SharedPreferences prefs){return prefs.getString("scene","curse");}
    static String providerOf(SharedPreferences prefs){
        if(!prefs.getBoolean("little_doll_default_v1",false))prefs.edit().putString("map_provider","original").putBoolean("little_doll_default_v1",true).apply();
        return prefs.getString("map_provider","original");
    }
    static String title(String id){int index=java.util.Arrays.asList(PROVIDERS).indexOf(id);return NAMES[Math.max(0,index)];}
    static String[] levels(String scene,String author){
        if(!"original".equals(author))return new String[]{"hard","nightmare"};
        return "curse".equals(scene)?new String[]{"easy","normal","hard","nightmare"}:new String[]{"normal","hard","nightmare"};
    }
    static String levelName(String key){return "easy".equals(key)?"简单":"normal".equals(key)?"普通":"nightmare".equals(key)?"噩梦":"困难";}
    String selected(Theme.ChalkChoice control){return levels(scene(),provider())[control.getIndex()];}
    void refreshDifficulty(Theme.ChalkChoice control){
        String[] keys=levels(scene(),provider()),labels=new String[keys.length];
        for(int pos=0;pos<keys.length;pos++)labels[pos]=levelName(keys[pos]);
        int index=java.util.Arrays.asList(keys).indexOf(prefs.getString("difficulty","hard"));
        control.setOptions(labels,index<0?java.util.Arrays.asList(keys).indexOf("hard"):index);
    }
    /** The one difficulty an author offers for a map, or null when the player chooses.
     *  Every 磷光症 author now offers 困难 and 噩梦, so the player always chooses. */
    static String fixedDifficulty(String scene,String provider){
        return null;
    }
    boolean isLinguang(){return scene.getIndex()==1;}
    String scene(){return isLinguang()?"linguang":"curse";}
    String provider(){return PROVIDERS[provider.getIndex()];}
    boolean hasParty(){return "lianghapi".equals(provider())&&!isLinguang();}
    boolean isZhanshi(){return provider().equals("zhanshi");}
    /** Null while the player still picks the difficulty themselves. */
    String fixedDifficulty(){return fixedDifficulty(scene(),provider());}
    String difficulty(String legacy){String fixed=fixedDifficulty();return fixed!=null?fixed:legacy;}
    String mode(String legacy){
        if(provider().equals("original"))return null;
        if(isLinguang())return isZhanshi()?"full":null;
        return isZhanshi()?(route.getIndex()==1?"speed":"full"):legacy;
    }
    void refresh(){
        syncing=true;
        scene.setIndex(sceneOf(prefs).equals("linguang")?1:0);
        provider.setIndex(Math.max(0,java.util.Arrays.asList(PROVIDERS).indexOf(providerOf(prefs))));
        route.setIndex(prefs.getString("zhanshi_route","full").equals("speed")?1:0);
        updateVisibility();
        syncing=false;
    }
    private void updateVisibility(){
        providerRow.setVisibility(VISIBLE);
        routeRow.setVisibility(!isLinguang()&&isZhanshi()?VISIBLE:GONE);
    }
}
