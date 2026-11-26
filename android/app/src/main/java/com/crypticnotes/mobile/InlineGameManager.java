package com.crypticnotes.mobile;
import android.app.AlertDialog;
import android.content.*;
import android.os.*;
import android.view.*;
import android.widget.*;
import org.json.JSONObject;
/** Dynamic independent games, with management in the final version fold. */
final class InlineGameManager extends LinearLayout {
    Runnable stateChanged;private boolean busy,syncing,corePresent;private final Handler main=new Handler(Looper.getMainLooper());
    private final LinearLayout rows,versions;private final TextView status;private final Theme.SectionHeading versionHeading;private final java.util.List<View> preferences=new java.util.ArrayList<>();
    InlineGameManager(Context c){super(c);setOrientation(VERTICAL);rows=new LinearLayout(c);rows.setOrientation(VERTICAL);addView(rows);
        status=Theme.muted(c,"");addView(status);status.setVisibility(GONE);
        setting("小游戏声音","gameSound",true);setting("画面变化检测","gameSceneEnabled",true);
        versionHeading=new Theme.SectionHeading(c,"版本");addView(versionHeading);versions=new LinearLayout(c);versions.setOrientation(VERTICAL);versions.setVisibility(GONE);addView(versions);versionHeading.setOnClickListener(v->{boolean open=versions.getVisibility()!=VISIBLE;versions.setVisibility(open?VISIBLE:GONE);versionHeading.setExpanded(open);});
        refresh();}
    void setCorePresent(boolean present){if(corePresent==present)return;corePresent=present;refresh();if(present)probe();}
    void movePreferencesTo(LinearLayout settings){for(View row:preferences){removeView(row);settings.addView(row);}}
    LinearLayout takeVersions(){removeView(versions);removeView(versionHeading);versions.setVisibility(VISIBLE);return versions;}
    private final java.util.Map<String,Long> measuredSizes=new java.util.HashMap<>();
    private final java.util.Set<String> pendingSizes=new java.util.HashSet<>();
    private static final java.util.concurrent.ExecutorService sizeWorker=java.util.concurrent.Executors.newSingleThreadExecutor();
    private long displaySize(MiniGameStore store){
        String key=store.game.getAbsolutePath()+":"+store.hash();
        Long saved=measuredSizes.get(key);if(saved!=null)return saved;
        if(pendingSizes.add(key))sizeWorker.execute(()->{
            long bytes=store.size();
            main.post(()->{pendingSizes.remove(key);measuredSizes.put(key,bytes);
                if(getContext() instanceof android.app.Activity && ((android.app.Activity)getContext()).isDestroyed())return;
                refresh();
            });
        });
        return 0; // Size pending, never recursively walk game assets on the UI thread.
    }
    void setting(String label,String key,boolean fallback){LinearLayout row=new LinearLayout(getContext());row.setGravity(Gravity.CENTER_VERTICAL);row.addView(Theme.muted(getContext(),label),new LayoutParams(0,-2,1));Theme.ChalkChoice choice=new Theme.ChalkChoice(getContext(),new String[]{"开","关"});choice.setIndex(getContext().getSharedPreferences("mobile",0).getBoolean(key,fallback)?0:1);row.addView(choice,new LayoutParams(Theme.px(getContext(),120),Theme.px(getContext(),42)));choice.setListener(i->{getContext().getSharedPreferences("mobile",0).edit().putBoolean(key,i==0).apply();if(MiniGameOverlayService.current!=null)MiniGameOverlayService.current.applyHostSound();if(key.equals("gameSceneEnabled")&&i==1&&CaptureService.current!=null)CaptureService.current.releaseGameCapture();});preferences.add(row);addView(row);}
    void probe(){if(corePresent)sync(false);}
    void sync(boolean force){if(syncing||busy)return;syncing=true;
        MiniGameUpdates.check(getContext(),force,()->{syncing=false;if(getContext() instanceof android.app.Activity&&((android.app.Activity)getContext()).isDestroyed())return;refresh();});refresh();}
    void refresh(){rows.removeAllViews();versions.removeAllViews();JSONObject catalog=GameCatalog.cached(getContext());
        for(String id:GameCatalog.ids(getContext())){MiniGameStore store=new MiniGameStore(getContext(),id);boolean installed=store.installed();JSONObject spec=catalog.optJSONObject(id);
            PackageState state=MiniGameUpdates.state(store,installed,spec);long bytes=installed?store.downloadSize():spec==null?0:spec.optLong("size");if(installed&&bytes<=0)bytes=displaySize(store);
            String version=installed?store.version():spec==null?"":spec.optString("version");
            LinearLayout row=new LinearLayout(getContext());row.setGravity(Gravity.CENTER_VERTICAL);
            if(installed){GameIcons.addTo(row,id);TextView name=Theme.muted(getContext(),store.title());name.setSingleLine(true);name.setEllipsize(android.text.TextUtils.TruncateAt.END);row.addView(name,new LayoutParams(0,-2,1));}
            else{PackageCaption quick=new PackageCaption(getContext(),store.title());quick.describe(false,version,bytes);rows.addView(quick);}
            Theme.ChalkButton open=new Theme.ChalkButton(getContext(),installed?"打开":"下载");row.addView(open,new LayoutParams(installed?Theme.px(getContext(),76):-1,Theme.px(getContext(),44)));open.setEnabled(!busy&&!MatchingModuleManager.operationRunning);open.setOnClickListener(v->{if(installed)launch(id);else download(store);});rows.addView(row);
            PackageCaption caption=new PackageCaption(getContext(),store.title());caption.describe(installed,version,bytes);versions.addView(caption);
            LinearLayout line=new LinearLayout(getContext());Theme.ChalkButton check=new Theme.ChalkButton(getContext(),state.label,true),delete=new Theme.ChalkButton(getContext(),"删除");line.addView(check,new LayoutParams(0,-2,1));line.addView(delete);check.setUpdateDot(state==PackageState.UPDATE);check.setEnabled(!busy&&!MatchingModuleManager.operationRunning&&state.actionable);check.setOnClickListener(v->{if(state==PackageState.FAILED||state==PackageState.UNCHECKED)sync(true);else download(store);});delete.setVisibility(installed?VISIBLE:GONE);delete.setEnabled(!busy&&!MatchingModuleManager.operationRunning&&!MiniGameOverlayService.running);delete.setOnClickListener(v->new AlertDialog.Builder(getContext()).setMessage("删除游戏包？存档和偏好会保留。").setNegativeButton("取消",null).setPositiveButton("删除",(d,w)->{if(MatchingModuleManager.operationRunning)return;try{store.delete();refresh();}catch(Exception e){status.setText(e.getMessage());status.setVisibility(VISIBLE);}}).show());versions.addView(line);
        }
        Theme.ChalkButton sync=new Theme.ChalkButton(getContext(),syncing?"正在检查…":"刷新列表");sync.setEnabled(!syncing&&!busy);sync.setOnClickListener(v->sync(true));versions.addView(sync);if(stateChanged!=null)stateChanged.run();}
    private void launch(String id){Context c=getContext();if(c instanceof MainActivity)((MainActivity)c).startGame(id);else c.startActivity(new Intent(c,MainActivity.class).putExtra("launch_game",id).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_SINGLE_TOP));}
    private void download(MiniGameStore store){if(busy||MatchingModuleManager.operationRunning||MiniGameOverlayService.running){Toast.makeText(getContext(),"请先结束当前操作或退出小游戏",Toast.LENGTH_SHORT).show();return;}MatchingModuleManager.operationRunning=true;busy=true;refresh();status.setVisibility(VISIBLE);status.setText("正在下载…");new Thread(()->{String error=null;try{store.download(text->main.post(()->status.setText(text)));}catch(Exception e){error=e.getMessage();}String result=error;main.post(()->{busy=false;MatchingModuleManager.operationRunning=false;status.setText(result);status.setVisibility(result==null?GONE:VISIBLE);refresh();sync(true);});},"game-download").start();}
}
