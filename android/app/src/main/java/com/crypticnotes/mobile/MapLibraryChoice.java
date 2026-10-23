package com.crypticnotes.mobile;

import android.content.Context;
import android.content.SharedPreferences;
import android.view.View;
import android.widget.LinearLayout;

/** Author and route are separate from the legacy party selector. */
final class MapLibraryChoice extends LinearLayout {
    private final SharedPreferences prefs;
    private final Theme.ChalkChoice provider, route;
    private final LinearLayout routeRow;
    Runnable changed;
    private boolean syncing;
    MapLibraryChoice(Context context) {
        super(context);setOrientation(VERTICAL);
        prefs=context.getSharedPreferences("mobile",0);
        provider=new Theme.ChalkChoice(context,new String[]{"凉哈皮","展十"});
        route=new Theme.ChalkChoice(context,new String[]{"全棺","速刷"});
        addView(row(context,"地图版本",provider));
        routeRow=row(context,"参考路线",route);addView(routeRow);
        refresh();
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
    boolean isZhanshi(){return provider.getIndex()==1;}
    String difficulty(String legacy){return legacy;}
    String mode(String legacy){return isZhanshi()?(route.getIndex()==1?"speed":"full"):legacy;}
    void refresh(){
        syncing=true;
        provider.setIndex(prefs.getString("map_provider","lianghapi").equals("zhanshi")?1:0);
        route.setIndex(prefs.getString("zhanshi_route","full").equals("speed")?1:0);
        updateVisibility();
        syncing=false;
    }
    private void updateVisibility(){routeRow.setVisibility(isZhanshi()?VISIBLE:GONE);}
}
