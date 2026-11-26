package com.crypticnotes.mobile;
import android.app.AlertDialog;
import android.content.*;
import android.os.*;
import android.view.View;
import android.widget.*;
import org.json.JSONObject;
/** Download-only state, or a compact final version fold. */
final class MatchingModuleManager extends LinearLayout {
    final MatchingModuleStore store;final Theme.ChalkButton action,delete;final TextView status;final PackageCaption caption;static volatile boolean operationRunning;Runnable changed;
    private static final Handler main=new Handler(Looper.getMainLooper());
    private static final java.util.Map<String,Transfer> transfers=new java.util.HashMap<>();
    private final Transfer transfer;
    private static final class Transfer {
        MatchingModuleManager view;boolean busy,checking;String message="";
        void progress(String text){message=text;if(view!=null)view.showMessage();}
        void finish(String error){
            operationRunning=false;busy=false;checking=false;message=error==null?"":error;
            if(view!=null){view.refresh();if(view.changed!=null)view.changed.run();}
        }
    }
    MatchingModuleManager(Context c){this(c,null);}
    MatchingModuleManager(Context c,String provider){super(c);setOrientation(VERTICAL);
        if(provider==null){store=null;transfer=null;action=null;delete=null;status=null;caption=null;
            for(String id:new String[]{"lianghapi","zhanshi"}){MatchingModuleManager row=new MatchingModuleManager(c,id);row.changed=()->{if(changed!=null)changed.run();};addView(row);}return;}
        transfer=transfers.computeIfAbsent(provider,key->new Transfer());
        boolean core=ModuleUpdates.core(provider);caption=new PackageCaption(c,ModuleUpdates.title(provider));addView(caption);
        store=new MatchingModuleStore(c,provider);LinearLayout row=new LinearLayout(c);action=new Theme.ChalkButton(c,"下载",true);delete=new Theme.ChalkButton(c,"删除");row.addView(action,new LayoutParams(0,-2,1));row.addView(delete);addView(row);status=Theme.muted(c,"");status.setVisibility(GONE);addView(status);action.setOnClickListener(v->run(false));delete.setOnClickListener(v->new AlertDialog.Builder(c).setTitle("删除"+ModuleUpdates.title(provider)+"？").setMessage(core?"同时移除本栏已下载的包，个人地图、存档和设置保留。":"个人地图和设置保留。").setNegativeButton("取消",null).setPositiveButton("删除",(d,w)->run(true)).show());refresh();}
    @Override protected void onAttachedToWindow(){super.onAttachedToWindow();if(transfer!=null){transfer.view=this;refresh();}}
    @Override protected void onDetachedFromWindow(){if(transfer!=null&&transfer.view==this)transfer.view=null;super.onDetachedFromWindow();}
    private void showMessage(){status.setText(transfer.message);status.setVisibility(transfer.message.isEmpty()?GONE:VISIBLE);}
    void refresh(){
        if(store==null){for(int index=0;index<getChildCount();index++)if(getChildAt(index) instanceof MatchingModuleManager)((MatchingModuleManager)getChildAt(index)).refresh();return;}
        boolean installed=store.installed();PackageState state=ModuleUpdates.state(store,installed);
        JSONObject remote=ModuleUpdates.metadata(store.id()),spec=installed?store.receipt():remote;
        String hash=installed?store.hash():remote==null?"":remote.optString("sha256");
        long size=spec==null?0:spec.optLong("size");
        if(size==0&&remote!=null&&hash.equals(remote.optString("sha256")))size=remote.optLong("size");
        caption.describe(installed,MatchingModuleStore.version(spec,hash),size);
        action.setText(transfer.busy?(transfer.checking?PackageState.CHECKING.label:"处理中…"):state.label);action.setUpdateDot(state==PackageState.UPDATE);
        action.setEnabled(!operationRunning&&state.actionable);delete.setVisibility(installed?VISIBLE:GONE);delete.setEnabled(!operationRunning);showMessage();
    }
    void run(boolean removing){
        if(operationRunning){Toast.makeText(getContext(),"已有操作进行中，请稍候",Toast.LENGTH_SHORT).show();return;}
        if(MiniGameOverlayService.running&&store.id().equals("games")){Toast.makeText(getContext(),"请先退出小游戏",Toast.LENGTH_SHORT).show();return;}
        PackageState state=ModuleUpdates.state(store,store.installed());if(!removing&&!state.actionable)return;
        boolean check=!removing&&(state==PackageState.UNCHECKED||state==PackageState.FAILED);
        operationRunning=true;transfer.busy=true;transfer.checking=check;transfer.message=check?"":"正在准备…";refresh();if(changed!=null)changed.run();
        if(!check)ModuleUpdates.stopUsing(store);
        work(store,transfer,check,removing);
    }
    private static void work(MatchingModuleStore store,Transfer transfer,boolean check,boolean removing){
        new Thread(()->{
            String error=null;
            try{
                if(check)ModuleUpdates.inspect(store,()->{});
                else if(removing)store.delete();
                else{store.download(text->main.post(()->transfer.progress(text)));ModuleUpdates.installed(store);}
            }catch(Exception problem){error=problem.getMessage()==null?"操作失败，请重试":problem.getMessage();}
            String result=error;main.post(()->transfer.finish(result));
        },"matching-module").start();
    }
}
