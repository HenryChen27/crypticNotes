package com.crypticnotes.mobile;
import android.app.AlertDialog;
import android.content.*;
import android.os.*;
import android.view.*;
import android.widget.*;
import org.json.JSONObject;
/** Dynamic independent games, with management in the final version fold. */
final class InlineGameManager extends LinearLayout {
    Runnable stateChanged;private boolean busy,syncing;private final Handler main=new Handler(Looper.getMainLooper());
    private final LinearLayout rows,versions;private final TextView status;private final Theme.SectionHeading versionHeading;private final java.util.List<View> preferences=new java.util.ArrayList<>();
    InlineGameManager(Context c){super(c);setOrientation(VERTICAL);rows=new LinearLayout(c);rows.setOrientation(VERTICAL);addView(rows);
        status=Theme.muted(c,"");addView(status);status.setVisibility(GONE);
        setting("小游戏声音","gameSound",true);setting("画面变化检测","gameSceneEnabled",true);
        versionHeading=new Theme.SectionHeading(c,"版本");addView(versionHeading);versions=new LinearLayout(c);versions.setOrientation(VERTICAL);versions.setVisibility(GONE);addView(versions);versionHeading.setOnClickListener(v->{boolean open=versions.getVisibility()!=VISIBLE;versions.setVisibility(open?VISIBLE:GONE);versionHeading.setExpanded(open);});
        refresh();sync();}
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
    void sync(){if(syncing||busy)return;syncing=true;new Thread(()->{String error=null;try{JSONObject games=MiniGameStore.collection();GameIcons.prefetch(getContext(),games);getContext().getSharedPreferences("mobile",0).edit().putString("gameCatalog",games.toString()).apply();}catch(Exception e){error=e.getMessage();}String result=error;main.post(()->{syncing=false;refresh();if(result!=null){status.setText("同步未完成，保留本地游戏："+result);status.setVisibility(VISIBLE);}});},"game-catalog").start();}
    void refresh(){rows.removeAllViews();versions.removeAllViews();JSONObject catalog=GameCatalog.cached(getContext());
        for(String id:GameCatalog.ids(getContext())){MiniGameStore store=new MiniGameStore(getContext(),id);boolean installed=store.installed();JSONObject spec=catalog.optJSONObject(id);long installedBytes=installed?displaySize(store):0;boolean update=installed&&spec!=null&&!spec.optString("sha256").equals(store.hash());
            LinearLayout row=new LinearLayout(getContext());row.setGravity(Gravity.CENTER_VERTICAL);GameIcons.addTo(row,id);row.addView(gameLabel(store,spec,installed,installedBytes),new LayoutParams(0,-2,1));Theme.ChalkButton open=new Theme.ChalkButton(getContext(),installed?"打开":"下载");row.addView(open,new LayoutParams(Theme.px(getContext(),76),Theme.px(getContext(),44)));open.setEnabled(!busy);open.setOnClickListener(v->{if(installed)launch(id);else download(store);});rows.addView(row);
            if(installed){LinearLayout line=new LinearLayout(getContext());line.setGravity(Gravity.CENTER_VERTICAL);GameIcons.addTo(line,id);line.addView(gameLabel(store,spec,true,installedBytes),new LayoutParams(0,-2,1));Theme.ChalkButton check=new Theme.ChalkButton(getContext(),spec==null?"检查更新":update?"更新":"已是最新版"),delete=new Theme.ChalkButton(getContext(),"删除");line.addView(check);line.addView(delete);check.setEnabled(!busy&&(update||spec==null));check.setOnClickListener(v->{if(spec==null)sync();else download(store);});delete.setEnabled(!busy&&!MiniGameOverlayService.running);delete.setOnClickListener(v->new AlertDialog.Builder(getContext()).setMessage("删除游戏包（"+formatSize(installedBytes)+"）？存档和偏好会保留。").setNegativeButton("取消",null).setPositiveButton("删除",(d,w)->{try{store.delete();refresh();}catch(Exception e){status.setText(e.getMessage());status.setVisibility(VISIBLE);}}).show());versions.addView(line);}
        }
        Theme.ChalkButton sync=new Theme.ChalkButton(getContext(),syncing?"正在检查…":"同步列表 / 检查更新");sync.setEnabled(!syncing&&!busy);sync.setOnClickListener(v->sync());versions.addView(sync);boolean any=false;for(String id:GameCatalog.ids(getContext()))if(new MiniGameStore(getContext(),id).installed())any=true;for(View v:preferences)v.setVisibility(any?VISIBLE:GONE);versionHeading.setVisibility(any?VISIBLE:GONE);if(!any)versions.setVisibility(GONE);if(stateChanged!=null)stateChanged.run();}
    private View gameLabel(MiniGameStore store,JSONObject spec,boolean installed,long installedBytes){
        LinearLayout label=new LinearLayout(getContext());label.setOrientation(VERTICAL);
        label.setPadding(0,Theme.px(getContext(),8),Theme.px(getContext(),8),Theme.px(getContext(),8));
        TextView title=Theme.muted(getContext(),store.title());title.setTextColor(Theme.TEXT);
        label.addView(title);
        String version=installed?store.version():spec==null?"":spec.optString("version","");
        if(!version.isEmpty()&&!version.startsWith("v"))version="v"+version;
        long bytes=installed?installedBytes:spec==null?0:spec.optLong("size",0);
        TextView detail=Theme.muted(getContext(),(version.isEmpty()?"":version+" · ")+(bytes>0?compactSize(bytes):"—"));
        detail.setTextSize(11);detail.setAlpha(.58f);label.addView(detail);
        return label;
    }
    private static String compactSize(long bytes){return String.format(java.util.Locale.ROOT,"%.1f",bytes/1048576.0).replaceAll("\\.0$","")+"MB";}
    private static String formatSize(long bytes){return bytes<=0?"大小统计中":String.format(java.util.Locale.ROOT,"%.1f MB",bytes/1048576.0);}
    private void launch(String id){Context c=getContext();if(c instanceof MainActivity)((MainActivity)c).startGame(id);else c.startActivity(new Intent(c,MainActivity.class).putExtra("launch_game",id).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_SINGLE_TOP));}
    private void download(MiniGameStore store){if(busy||MiniGameOverlayService.running){Toast.makeText(getContext(),"请先关闭小游戏再更新",Toast.LENGTH_SHORT).show();return;}busy=true;refresh();status.setVisibility(VISIBLE);status.setText("正在下载…");new Thread(()->{String error=null;try{store.download(text->main.post(()->status.setText(text)));}catch(Exception e){error=e.getMessage();}String result=error;main.post(()->{busy=false;status.setText(result==null?"下载完成":result);refresh();sync();});},"game-download").start();}
}
