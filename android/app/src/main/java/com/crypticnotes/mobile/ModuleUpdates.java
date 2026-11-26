package com.crypticnotes.mobile;

import android.content.Context;
import android.content.Intent;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.List;

final class ModuleUpdates {
    static final String[] IDS={"notes","lianghapi","zhanshi","pvp","games"};
    static boolean core(String id){return "notes".equals(id)||"pvp".equals(id)||"games".equals(id);}
    static String title(String id){switch(id){case "notes":return "加页手记主程序";case "pvp":return "禁选辅助主程序";case "games":return "小游戏主程序";default:return MapLibraryChoice.title(id)+"地图库";}}
    private static final class Probe {
        final JSONObject spec;final boolean checking,failed;
        Probe(JSONObject spec,boolean checking,boolean failed){this.spec=spec;this.checking=checking;this.failed=failed;}
    }
    private static final java.util.concurrent.ConcurrentMap<String,Probe> probes=new java.util.concurrent.ConcurrentHashMap<>();
    static JSONObject metadata(String id){Probe probe=probes.get(id);return probe==null?null:probe.spec;}
    static PackageState state(MatchingModuleStore store,boolean installed){
        Probe probe=probes.get(store.id());
        return PackageState.resolve(installed,probe!=null&&probe.checking,probe!=null&&probe.failed,
                probe==null||probe.spec==null?null:probe.spec.optString("sha256"),installed?store.hash():"");
    }
    static boolean flag(Context context,String id){MatchingModuleStore store=new MatchingModuleStore(context,id);return state(store,store.installed())==PackageState.UPDATE;}
    static void installed(MatchingModuleStore store){probes.put(store.id(),new Probe(store.latest,false,false));}
    static boolean inspect(MatchingModuleStore store,Runnable changed)throws Exception{
        String id=store.id();Probe pending=new Probe(metadata(id),true,false);probes.put(id,pending);changed.run();
        try{boolean newer=store.updateAvailable();return probes.replace(id,pending,new Probe(store.latest,false,false))&&newer;}
        catch(Exception error){probes.replace(id,pending,new Probe(pending.spec,false,true));throw error;}
        finally{changed.run();}
    }
    static void stopUsing(MatchingModuleStore store){
        CaptureService service=CaptureService.current;
        if(service!=null&&(service.pvp?store.id().equals("pvp"):service.gameOnly?store.id().equals("games"):!store.id().equals("pvp")&&!store.id().equals("games")))store.c.stopService(new Intent(store.c,CaptureService.class));
    }
    static String process(Context context,boolean install,MiniGameStore.Progress progress,Runnable changed){
        int updated=0;List<String> errors=new ArrayList<>();
        List<MatchingModuleStore> targets=new ArrayList<>();
        for(String id:IDS){MatchingModuleStore store=new MatchingModuleStore(context,id);if(store.installed())targets.add(0,store);else if(!install)targets.add(store);}
        for(MatchingModuleStore store:targets){String id=store.id();
            try{String checkedHash=store.hash();boolean newer=inspect(store,changed);
                if(install&&newer&&store.installed()&&checkedHash.equals(store.hash())){stopUsing(store);store.download(text->progress.update(title(id)+" · "+text));installed(store);updated++;}
            }catch(Exception error){errors.add(title(id)+"："+error.getMessage());}
        }
        if(install&&new MatchingModuleStore(context,"games").installed()){
            List<MiniGameStore> installed=new ArrayList<>();for(String id:GameCatalog.ids(context)){MiniGameStore game=new MiniGameStore(context,id);if(game.installed())installed.add(game);}
            if(!installed.isEmpty())try{JSONObject catalog=MiniGameUpdates.fetch(context);
                for(MiniGameStore game:installed){JSONObject spec=catalog.optJSONObject(game.id);if(spec==null||spec.optString("sha256").equals(game.hash()))continue;
                    if(install&&game.installed())try{game.download(text->progress.update(game.title()+" · "+text));updated++;}catch(Exception error){errors.add(game.title()+"："+error.getMessage());}}
            }catch(Exception error){errors.add("小游戏："+error.getMessage());}
        }
        return (updated>0?"已更新 "+updated+" 个包":errors.isEmpty()?"已安装的包均无可用更新":"检查未完成")+(errors.isEmpty()?"":"\n"+String.join("\n",errors));
    }
}
