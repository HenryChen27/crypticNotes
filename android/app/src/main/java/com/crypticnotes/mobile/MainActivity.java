package com.crypticnotes.mobile;

import android.app.*;
import android.content.*;
import android.media.projection.*;
import android.net.Uri;
import android.os.*;
import android.provider.Settings;
import android.view.*;
import android.widget.*;

/** Settings screen. Visual language mirrors the desktop client (see {@link Theme}). */
public class MainActivity extends Activity {
    private TextView status;
    private boolean uiReady,resumed;
    private FrameLayout startupHost;
    private View loadingOverlay;
    private Theme.SectionHeading gameHeading;
    private InlineGameManager inlineGames;
    private Theme.ChalkChoice difficulty, party;
    private MapLibraryChoice libraryChoice;
    private int opacity = 30;
    private AppUpdater updater;
    private boolean capturePermissionPending;
    private Theme.ChalkChoice recordingSound, recordingQuality, recordingFps, recordingReplay;
    private TextView recordingAudioHint, recordingSummary;
    /**
     * True while the recording rows are being repositioned from saved values.
     *
     * {@link Theme.ChalkChoice#setIndex} fires its listener on any change, so a
     * programmatic revert would otherwise be written back as if the user had
     * chosen it. With internal sound now the default that is not cosmetic: the
     * Android 9 path reverts to "无声" at construction, and without this guard
     * it would persist that and quietly opt every old device out for good.
     */
    private boolean syncingRecording;
    /** The scrolling column everything on this screen is added to. */
    private LinearLayout content,mapPage,gamesPage,generalPage,pvpPage;
    private LinearLayout mailSection;
    private ScrollView scroll;
    private ModulePage notesPackages,pvpPackages,gamePackages;
    private TextView gearIcon,batchStatus;private boolean unread,hostUpdate,checkingPackages;
    private long checkedPackagesAt;
    private String activeModule;
    private Runnable deferredCapture;
    private MatchingModuleManager moduleManager,pvpManager;
    private final android.content.SharedPreferences.OnSharedPreferenceChangeListener packagesChanged=(prefs,key)->{
        if(uiReady&&key!=null&&(key.startsWith("matchingHash_")||key.equals("gameCatalog")))refreshPackages();
    };
    private String pendingGame;
    private View mapActions;
    private DarkTab notesTab,gamesTab,pvpTab;
    private boolean pendingPvp;
    private TextView pvpStatus,pvpLast;
    private void switchModule(String name){
        if(!"pvp".equals(name)&&!"games".equals(name)&&!"settings".equals(name))name="notes";
        boolean enteringSettings="settings".equals(name)&&!name.equals(activeModule);
        activeModule=name;
        if(enteringSettings){
            setFoldExpanded(mailSection,true);
            scroll.post(()->{if("settings".equals(activeModule))scroll.scrollTo(0,0);});
        }
        refreshPackages();
        mapPage.setVisibility(name.equals("notes")?View.VISIBLE:View.GONE);gamesPage.setVisibility(name.equals("games")?View.VISIBLE:View.GONE);generalPage.setVisibility(name.equals("settings")?View.VISIBLE:View.GONE);pvpPage.setVisibility(name.equals("pvp")?View.VISIBLE:View.GONE);pvpTab.select(name.equals("pvp"));notesTab.select(name.equals("notes"));gamesTab.select(name.equals("games"));if(!name.equals("settings"))getSharedPreferences("mobile",0).edit().putString("last_module",name).apply();}
    private LinearLayout newPage(){LinearLayout page=new LinearLayout(this);page.setOrientation(LinearLayout.VERTICAL);return page;}

    private final class ModulePage {
        final LinearLayout first,body,versions;final MatchingModuleManager core;final Theme.SectionHeading heading;
        ModulePage(LinearLayout page,String id){
            body=newPage();while(page.getChildCount()>0){View view=page.getChildAt(0);page.removeViewAt(0);body.addView(view);}
            first=card();page.addView(first);page.addView(body);content=page;versions=fold("版本",false);heading=(Theme.SectionHeading)versions.getTag();
            heading.setOnClickListener(view->{boolean open=versions.getVisibility()!=View.VISIBLE;setFoldExpanded(versions,open);
                if(open){checkPackages(false);if(id.equals("games"))inlineGames.probe();}});
            core=new MatchingModuleManager(MainActivity.this,id);core.changed=MainActivity.this::moduleActionChanged;
        }
        void refresh(boolean update){boolean installed=core.store.installed();LinearLayout slot=installed?versions:first;
            if(core.getParent()!=slot){if(core.getParent()!=null)((LinearLayout)core.getParent()).removeView(core);slot.addView(core,0);}
            first.setVisibility(installed?View.GONE:View.VISIBLE);body.setVisibility(installed?View.VISIBLE:View.GONE);
            heading.setVisibility(installed?View.VISIBLE:View.GONE);versions.setVisibility(installed&&Boolean.TRUE.equals(heading.getTag())?View.VISIBLE:View.GONE);
            heading.setUpdateAvailable(update);core.refresh();
        }
    }
    private void moduleActionChanged(){refreshPackages();if(inlineGames!=null)inlineGames.refresh();}
    private void refreshPackages(){
        if(gamePackages==null||isDestroyed())return;
        boolean notes=ModuleUpdates.flag(this,"notes")||ModuleUpdates.flag(this,"lianghapi")||ModuleUpdates.flag(this,"zhanshi"),pvp=ModuleUpdates.flag(this,"pvp"),games=ModuleUpdates.flag(this,"games")||MiniGameUpdates.available(this);
        notes&=notesPackages.core.store.installed();pvp&=pvpPackages.core.store.installed();games&=gamePackages.core.store.installed();
        notesPackages.refresh(notes);gamePackages.refresh(games);pvpPackages.refresh(pvp);moduleManager.refresh();
        inlineGames.setCorePresent(gamePackages.core.store.installed());
        notesTab.setUpdate(notes);pvpTab.setUpdate(pvp);gamesTab.setUpdate(games);if(libraryChoice!=null){libraryChoice.refresh();libraryChoice.changed.run();}
    }
    private void checkPackages(boolean install){
        if(install&&(checkingPackages||MatchingModuleManager.operationRunning||MiniGameOverlayService.running)){Toast.makeText(this,"请先结束当前检查、下载或小游戏",Toast.LENGTH_SHORT).show();return;}
        if(!install&&(checkingPackages||MatchingModuleManager.operationRunning||SystemClock.elapsedRealtime()-checkedPackagesAt<60000&&checkedPackagesAt!=0))return;
        if(install){MatchingModuleManager.operationRunning=true;batchStatus.setVisibility(View.VISIBLE);batchStatus.setText("正在检查已安装的包…");moduleActionChanged();}else checkingPackages=true;
        new Thread(()->{String result;
            try{result=ModuleUpdates.process(this,install,text->runOnUiThread(()->{if(!isDestroyed())batchStatus.setText(text);}),()->runOnUiThread(this::refreshPackages));}
            catch(Exception error){result="检查未完成："+error.getMessage();}
            String message=result;runOnUiThread(()->{if(install)MatchingModuleManager.operationRunning=false;else checkingPackages=false;checkedPackagesAt=SystemClock.elapsedRealtime();if(isDestroyed())return;if(install)batchStatus.setText(message);inlineGames.refresh();refreshPackages();});
        },install?"module-update-installed":"module-check").start();
    }


    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        if(state!=null){pendingGame=state.getString("pendingGame");pendingPvp=state.getBoolean("pendingPvp");capturePermissionPending=state.getBoolean("capturePermissionPending");}
        MapLibraryChoice.providerOf(getSharedPreferences("mobile",0));
        LinearLayout loading=new LinearLayout(this);loading.setOrientation(LinearLayout.VERTICAL);
        loading.setGravity(Gravity.CENTER);loading.setBackgroundColor(0xff1d3040);
        loading.addView(new DollLoadingView(this),new LinearLayout.LayoutParams(Theme.px(this,152),Theme.px(this,171)));
        startupHost=new FrameLayout(this);
        loadingOverlay=loading;
        startupHost.addView(loading,new FrameLayout.LayoutParams(-1,-1));
        setContentView(startupHost);
        new Thread(()->{
            try{
                Theme.typeface(getApplicationContext());
                MapCatalog.load(getApplicationContext());
                MailboxSync.box(getApplicationContext());
                PackageEvents.launched(getApplicationContext());
            }catch(Exception error){android.util.Log.w("CrypticNotes","Startup preload failed; continuing",error);}
            runOnUiThread(()->{if(!isDestroyed()&&!isFinishing())buildContent(state);});
        },"startup-preload").start();
    }

    private void buildContent(Bundle state){
        final long startupAt=SystemClock.uptimeMillis();

        FrameLayout root = new FrameLayout(this);
        View wallpaper = new View(this);
        wallpaper.setBackground(new Theme.MistDrawable(this));
        root.addView(wallpaper, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        scroll = new ScrollView(this);
        content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        int pad = Theme.px(this, 20);
        content.setPadding(pad, Theme.px(this, 16), pad, Theme.px(this, 20));
        scroll.addView(content);
        root.addView(scroll, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        startupHost.addView(root,0,new FrameLayout.LayoutParams(-1,-1));
        root.requestApplyInsets();
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            v.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                    insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            return insets.consumeSystemWindowInsets();
        });

        TextView subtitle = new TextView(this);
        subtitle.setVisibility(View.GONE);
        content.addView(Theme.muted(this, subtitle.getText().toString()));
        Theme.HandRule rule = new Theme.HandRule(this);
        LinearLayout.LayoutParams ruleParams = matchWrap();
        ruleParams.topMargin = Theme.px(this, 10);
        content.addView(rule, ruleParams);

        LinearLayout host=content;
        LinearLayout navigation=new LinearLayout(this);notesTab=new DarkTab(this,"加页手记");pvpTab=new DarkTab(this,"禁选辅助");gamesTab=new DarkTab(this,"小游戏");TextView gear=new TextView(this);gearIcon=gear;ActionIcon.set(gear,ActionIcon.GEAR,false);gear.setGravity(Gravity.CENTER);
        gear.setContentDescription("通用设置");gear.setTooltipText("通用设置");
        navigation.addView(notesTab,new LinearLayout.LayoutParams(0,Theme.px(this,48),1.2f));navigation.addView(pvpTab,new LinearLayout.LayoutParams(0,Theme.px(this,48),1.2f));navigation.addView(gamesTab,new LinearLayout.LayoutParams(0,Theme.px(this,48),1));navigation.addView(gear,new LinearLayout.LayoutParams(Theme.px(this,48),Theme.px(this,48)));host.addView(navigation);
        mapPage=newPage();gamesPage=newPage();generalPage=newPage();pvpPage=newPage();host.addView(mapPage);host.addView(pvpPage);host.addView(gamesPage);host.addView(generalPage);content=mapPage;
        notesTab.setOnClickListener(v->switchModule("notes"));pvpTab.setOnClickListener(v->switchModule("pvp"));gamesTab.setOnClickListener(v->switchModule("games"));gear.setOnClickListener(v->switchModule("settings"));
        // Starting is what this screen is for, so it sits above everything else
        // and outside the fold: the primary surface, the largest control, and
        // the only one that never scrolls out of the way.
        LinearLayout actions = card();
        content.addView(actions);mapActions=actions;
        status = Theme.status(this);
        status.setText("准备就绪");
        LinearLayout serviceActions = new LinearLayout(this);
        actions.addView(serviceActions, matchWrap());
        Theme.ChalkButton start = new Theme.ChalkButton(this, "开启自动识图", true);
        Theme.text(start, 16, Theme.INK);
        LinearLayout.LayoutParams startParams = new LinearLayout.LayoutParams(0, Theme.px(this, 46), 1);
        startParams.rightMargin = Theme.px(this, 8);
        serviceActions.addView(start, startParams);
        start.setOnClickListener(v -> startCapture());
        Theme.ChalkButton stop = new Theme.ChalkButton(this, "停止");
        serviceActions.addView(stop, new LinearLayout.LayoutParams(Theme.px(this, 76), Theme.px(this, 46)));
        stop.setOnClickListener(v -> {
            stopService(new Intent(this, CaptureService.class));
            status.setText("已停止");
        });
        LinearLayout.LayoutParams statusParams = matchWrap();
        statusParams.topMargin = Theme.px(this, 12);
        actions.addView(status, statusParams);

        // Everything else folds under one header, matching the desktop client's
        // fold sections, in the order the settings get reached for: difficulty
        // first, then the display tweaks, then the once-in-a-while ones. Open by
        // default: it was closed, and the section went missing twice while it
        // was, so the screen now opens with the settings in evidence. The state
        // is a reading preference, not a setting, so it is not persisted.
        LinearLayout settings = fold("游戏设置", true);
        LinearLayout mapSettings = fold("地图设置", false);

        libraryChoice = new MapLibraryChoice(this);
        settings.addView(libraryChoice);
        mapSettings.addView(libraryChoice.detachProvider());
        difficulty = new Theme.ChalkChoice(this, new String[]{"困难", "噩梦"});
        LinearLayout difficultyRow=choiceRow(fieldLabel("难度"), difficulty);
        settings.addView(difficultyRow, matchWrap());
        View sceneNote = Theme.helpLabel(this, "磷光症", "凉哈皮有困难（13 张）和噩梦（15 张），展十有困难十六棺（12 张）和噩梦十四棺（15 张）；按本局难度选作者和难度。楼层按右侧负一到负四的按钮识别，负四层暂无参考图。");
        settings.addView(sceneNote, matchWrap());
        settings.addView(libraryChoice.detachRoute(), matchWrap());
        TextView routeLabel = fieldLabel("参考路线");
        party = new Theme.ChalkChoice(this, new String[]{"单人路线", "多人路线"});
        LinearLayout routeRow = choiceRow(routeLabel, party);
        settings.addView(routeRow, matchWrap());
        libraryChoice.refreshDifficulty(difficulty);
        party.setIndex(getSharedPreferences("mobile", 0).getString("mode", "solo").equals("duo") ? 1 : 0);
        difficulty.setListener(i -> {
            getSharedPreferences("mobile", 0).edit().putString("difficulty",libraryChoice.selected(difficulty)).apply();
            // Solo/duo routes exist only for 厄运之女 噩梦 by 凉哈皮.
            int partyShown = libraryChoice.selected(difficulty).equals("nightmare") && libraryChoice.hasParty() ? View.VISIBLE : View.GONE;
            party.setVisibility(partyShown);
            routeLabel.setVisibility(partyShown);
            routeRow.setVisibility(partyShown);
        });
        party.setVisibility(difficulty.getIndex() == 1 ? View.VISIBLE : View.GONE);
        routeLabel.setVisibility(party.getVisibility());
        routeRow.setVisibility(party.getVisibility());
        party.setListener(i -> getSharedPreferences("mobile", 0).edit().putString("mode", i == 0 ? "solo" : "duo").apply());
        libraryChoice.changed=()->{
            libraryChoice.refreshDifficulty(difficulty);
            boolean linguang=libraryChoice.isLinguang();
            // 磷光症: both authors offer 困难 and 噩梦.
            difficultyRow.setVisibility(View.VISIBLE);
            sceneNote.setVisibility(linguang&&!libraryChoice.provider().equals("original")?View.VISIBLE:View.GONE);
            routeRow.setVisibility(libraryChoice.hasParty()&&libraryChoice.selected(difficulty).equals("nightmare")?View.VISIBLE:View.GONE);
            routeLabel.setVisibility(routeRow.getVisibility());
            party.setVisibility(routeRow.getVisibility());
        };
        libraryChoice.changed.run();

        // Same preference key the in-game panel writes, so a value set mid-game
        // survives a restart instead of being reset here on every launch.
        opacity = getSharedPreferences("mobile", 0).getInt("opacity", 30);
        final TextView opacityLabel = fieldLabel("叠图不透明度 " + opacity + "%");
        mapSettings.addView(opacityLabel);
        Theme.ChalkSlider slider = new Theme.ChalkSlider(this, 65,
                Math.max(0, Math.min(65, opacity - 5)));
        mapSettings.addView(slider, matchWrap());
        slider.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            public void onProgressChanged(SeekBar bar, int value, boolean fromUser) {
                opacity = value + 5;
                opacityLabel.setText("叠图不透明度 " + opacity + "%");
                getSharedPreferences("mobile", 0).edit().putInt("opacity", opacity).apply();
                pushDisplayPreferences();
            }
            public void onStartTrackingTouch(SeekBar bar) {}
            public void onStopTrackingTouch(SeekBar bar) {}
        });

        // How much of the map the floating button is allowed to cover. Stored
        // the same way the in-game panel reads it, in tenths of a percent so a
        // slider can carry it.
        float badgeScale = getSharedPreferences("mobile", 0).getFloat("badge_scale", 1f);
        final TextView badgeLabel = fieldLabel("悬浮球尺寸 " + Math.round(badgeScale * 100) + "%");
        content=generalPage;
        Theme.ChalkButton batch=new Theme.ChalkButton(this,"一键更新");
        generalPage.addView(batch,matchWrap());batch.setOnClickListener(v->checkPackages(true));
        batchStatus=Theme.muted(this,"");batchStatus.setVisibility(View.GONE);generalPage.addView(batchStatus,matchWrap());
        mailSection=fold("邮箱",true);
        Theme.SectionHeading mailHeading=((Theme.SectionHeading)mailSection.getTag()).setHeightDp(44);
        MailboxView mailbox=new MailboxView(this);
        mailSection.addView(mailbox,matchWrap());
        mailbox.setUnreadChanged(count->{
            mailHeading.setLabel(count>0?"邮箱（"+count+"）":"邮箱");
            mailHeading.setContentDescription(count>0?"邮箱，"+count+" 封未读":"邮箱");
            unread=count>0;ActionIcon.set(gear,ActionIcon.GEAR,unread||hostUpdate);
            gear.setContentDescription(count>0?"通用设置，有未读邮件":"通用设置");
        });
        LinearLayout floating=fold("悬浮球",false);
        content=mapPage;
        floating.addView(badgeLabel);
        Theme.ChalkSlider badgeSlider = new Theme.ChalkSlider(this, 90,
                Math.max(0, Math.min(90, Math.round(badgeScale * 100) - 70)));
        floating.addView(badgeSlider, matchWrap());
        badgeSlider.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            public void onProgressChanged(SeekBar bar, int value, boolean fromUser) {
                int percent = value + 70;
                badgeLabel.setText("悬浮球尺寸 " + percent + "%");
                getSharedPreferences("mobile", 0).edit().putFloat("badge_scale", percent / 100f).apply();
                pushDisplayPreferences();
            }
            public void onStartTrackingTouch(SeekBar bar) {}
            public void onStopTrackingTouch(SeekBar bar) {}
        });

        LinearLayout more = fold("辅助设置", false);
        Theme.ChalkChoice highRefresh=new Theme.ChalkChoice(this,new String[]{"关","开"});
        highRefresh.setIndex(getSharedPreferences("mobile",0).getBoolean("game_high_refresh",false)?1:0);
        View highRefreshRow=choiceRow(Theme.helpLabel(this,"小游戏高刷新率","开启后小游戏窗口按屏幕最高刷新率运行；默认 60 帧，省电模式下仍为 60 帧。"),highRefresh,120);
        highRefresh.setListener(i -> {
            getSharedPreferences("mobile",0).edit().putBoolean("game_high_refresh",i==1).apply();
            MiniGameOverlayService game=MiniGameOverlayService.current;
            if(game!=null)game.requestHighRefreshRate();
        });
        Theme.ChalkChoice feedback = new Theme.ChalkChoice(this,new String[]{"关","开"});
        feedback.setIndex(getSharedPreferences("mobile",0).getBoolean("touch_feedback",true)?1:0);
        floating.addView(choiceRow(fieldLabel("轻触反馈"),feedback,120),matchWrap());
        feedback.setListener(i -> getSharedPreferences("mobile",0).edit().putBoolean("touch_feedback",i==1).apply());
        more.addView(Theme.helpLabel(this,"自动展开检测","低分辨率采集，只检查地图控件；不拦截触摸，无需无障碍权限。关闭后须从悬浮球点重新识别。"));
        Theme.ChalkToggle automaticProbe=new Theme.ChalkToggle(this,"启用",120);
        automaticProbe.setChecked(getSharedPreferences("mobile",0).getBoolean("automatic_map_probe",true));
        more.addView(automaticProbe,matchWrap());
        automaticProbe.setListener(value->{getSharedPreferences("mobile",0).edit().putBoolean("automatic_map_probe",value).apply();pushDisplayPreferences();});
        Theme.ChalkButton diagnostic=new Theme.ChalkButton(this,"复制识图诊断");more.addView(diagnostic,matchWrap());
        diagnostic.setOnClickListener(v->{CaptureService service=CaptureService.current;
            if(service!=null)service.copyRecognitionDiagnostic();else Toast.makeText(this,"请先启动识图",Toast.LENGTH_SHORT).show();});
        Theme.ChalkButton manage = new Theme.ChalkButton(this, "地图库");
        mapSettings.addView(manage, matchWrap());
        manage.setOnClickListener(v -> startActivity(new Intent(this, MapLibraryActivity.class)));
        // Dragging the button is easier than explaining where it went, so the
        // reset only has to forget the stored spot; the next start puts it back
        // at the default corner.
        Theme.ChalkButton reset = new Theme.ChalkButton(this, "重置悬浮球位置");
        floating.addView(reset, matchWrap());
        reset.setOnClickListener(v -> {
            getSharedPreferences("mobile", 0).edit()
                    .remove("badge_x").remove("badge_y").apply();
            pushDisplayPreferences();
            Toast.makeText(this, "悬浮球已回到默认位置", Toast.LENGTH_SHORT).show();
        });
        floating.addView(Theme.helpLabel(this, "悬浮操作", "拖动悬浮按钮移动位置，点击打开设置，长按关闭识别。通知栏也可停止采集。"));
        TextView footnote = new TextView(this);
        footnote.setText("识图全程单线程，避免与游戏争抢 CPU。采集期间请保持横屏，退出游戏后点通知栏停止。");
        LinearLayout.LayoutParams footnoteParams = matchWrap();
        footnoteParams.topMargin = Theme.px(this, 12);

        content=generalPage;
        LinearLayout recording = fold("录屏设置", false);
        recordingSound = new Theme.ChalkChoice(this,new String[]{"无声","内部声音"});
        recording.addView(choiceRow(Theme.helpLabel(this,"声音","内部声音需要系统录音授权，但不采集麦克风。Android 10+ 可用；游戏不允许采集时仍可能静音，也可能录到其他应用播放的媒体声音。"),recordingSound),matchWrap());
        recordingSound.setListener(i -> {
            if(syncingRecording) return;
            if(i==0) { RecordPresets.setInternalAudio(this,false); syncRecordingRows(); return; }
            if(Build.VERSION.SDK_INT<29) { syncRecordingRows(); Toast.makeText(this,"内部声音需要 Android 10 或以上",Toast.LENGTH_SHORT).show(); return; }
            if(checkSelfPermission(android.Manifest.permission.RECORD_AUDIO)!=android.content.pm.PackageManager.PERMISSION_GRANTED) {
                syncRecordingRows(); startActivity(new Intent(this,AudioPermissionActivity.class));
            } else { RecordPresets.setInternalAudio(this,true); syncRecordingRows(); }
        });
        // Shown only when the choice is "internal sound" but the permission is
        // missing, so the row never claims something the recorder cannot do.
        recordingAudioHint = Theme.muted(this,"尚未授予录音权限，录制会是无声的 —— 点这里开启。");
        recordingAudioHint.setOnClickListener(v -> startActivity(new Intent(this,AudioPermissionActivity.class)));
        recording.addView(recordingAudioHint,matchWrap());

        recordingQuality = new Theme.ChalkChoice(this,RecordPresets.QUALITY_LABELS);
        recording.addView(choiceRow(Theme.helpLabel(this,"画质","流畅／标准／高清对应最长边 720／1280／1920 像素与约 2／4／8 Mbps。只影响录屏文件，不影响识图。"),recordingQuality),matchWrap());
        recordingQuality.setListener(i -> {
            if(syncingRecording) return;
            RecordPresets.setQualityIndex(this,i); syncRecordingRows();
        });

        recordingFps = new Theme.ChalkChoice(this,RecordPresets.FPS_LABELS);
        recording.addView(choiceRow(Theme.helpLabel(this,"帧率","24 帧与原设置一致；30／60 帧更顺滑，但更吃性能和存储。手机编码器不支持时会自动降档并提示。"),recordingFps),matchWrap());
        recordingFps.setListener(i -> {
            if(syncingRecording) return;
            RecordPresets.setFpsIndex(this,i); syncRecordingRows();
        });

        recordingReplay = new Theme.ChalkChoice(this,RecordPresets.REPLAY_LABELS);
        recording.addView(choiceRow(Theme.helpLabel(this,"回溯录制","选一个时长后，横屏识图期间一直在后台录着，但只在内存里留最近这么多秒，不写文件；在悬浮球设置里点「回溯录屏」才存成视频。编码器会一直工作，更耗电，默认关闭。时长越长、画质越高越占内存：20s 约 7～28 MB，50s 约 17～66 MB。画质、帧率、声音沿用上面的设置。"),recordingReplay),matchWrap());
        recordingReplay.setListener(i -> {
            if(syncingRecording) return;
            RecordPresets.setReplayIndex(this,i); syncRecordingRows();
            CaptureService service=CaptureService.current;
            if(service!=null) service.replaySettingChanged();
        });

        recordingSummary = Theme.muted(this,"");
        LinearLayout.LayoutParams summaryParams = matchWrap();
        summaryParams.topMargin = Theme.px(this, 8);
        recording.addView(recordingSummary, summaryParams);
        syncRecordingRows();
        recording.addView(Theme.helpLabel(this,"保存与操作","从悬浮球设置开始／停止录制。Android 10+ 保存到相册 Movies/CrypticNotes，转屏会保存当前视频；回溯录制转屏后从头开始攒。录叠图演示请选择共享整个屏幕。设置改动在下次录制生效。"));

        content=pvpPage;
        // Same shape as the 加页手记 page: the one action first, outside any fold.
        LinearLayout pvpActions = card();
        content.addView(pvpActions);
        LinearLayout pvpButtons = new LinearLayout(this);
        pvpActions.addView(pvpButtons, matchWrap());
        Theme.ChalkButton pvpStart = new Theme.ChalkButton(this, "开启禁选辅助", true);
        Theme.text(pvpStart, 16, Theme.INK);
        LinearLayout.LayoutParams pvpStartParams = new LinearLayout.LayoutParams(0, Theme.px(this, 46), 1);
        pvpStartParams.rightMargin = Theme.px(this, 8);
        pvpButtons.addView(pvpStart, pvpStartParams);
        pvpStart.setOnClickListener(v -> startPvp());
        Theme.ChalkButton pvpStop = new Theme.ChalkButton(this, "停止");
        pvpButtons.addView(pvpStop, new LinearLayout.LayoutParams(Theme.px(this, 76), Theme.px(this, 46)));
        pvpStop.setOnClickListener(v -> { stopService(new Intent(this, CaptureService.class)); pvpStatus.setText("已停止"); });
        pvpStatus = Theme.status(this);
        pvpStatus.setText("准备就绪");
        LinearLayout.LayoutParams pvpStatusParams = matchWrap();
        pvpStatusParams.topMargin = Theme.px(this, 12);
        pvpActions.addView(pvpStatus, pvpStatusParams);
        LinearLayout pvpSetup = fold("对局设置", true);
        // Short labels: the ranks have to share one row. The first segment is "not chosen", so a
        // player who never touched this is not reported as 一阶.
        final String[] rankNames = {"", "一阶", "二阶", "三阶", "四阶", "五阶", "六阶", "七阶", "巅峰七阶"};
        Theme.ChalkChoice rank = new Theme.ChalkChoice(this, new String[]{"未选", "一", "二", "三", "四", "五", "六", "七", "巅七"});
        String savedRank = getSharedPreferences("mobile", 0).getString("pvp_rank", "");
        for (int i = 0; i < rankNames.length; i++) if (rankNames[i].equals(savedRank)) rank.setIndex(i);
        rank.setListener(i -> getSharedPreferences("mobile", 0).edit().putString("pvp_rank", rankNames[i]).apply());
        pvpSetup.addView(choiceRow(Theme.helpLabel(this, "段位", "你当前的排位段位。和禁用角色、地图一起发给服务器，用来估计监管者。也可以在悬浮球面板里改。"), rank), matchWrap());
        LinearLayout pvpResult = fold("识别结果", true);
        pvpLast = Theme.text(new TextView(this), 15, Theme.TEXT);
        pvpResult.addView(pvpLast, matchWrap());
        pvpActions.addView(Theme.helpLabel(this,"选角识别","回到选角界面双击悬浮球识别，点头像或地图纠正结果。确认后发送段位、地图和禁选结果，不上传画面。"));
        content=gamesPage;
        LinearLayout games = fold("小游戏", true);
        gameHeading=(Theme.SectionHeading)games.getTag();
        gameHeading.setUpdateAvailable(MiniGameUpdates.available(this));
        inlineGames=new InlineGameManager(this);
        inlineGames.stateChanged=this::refreshPackages;
        games.addView(inlineGames,matchWrap());
        LinearLayout gameSettings=fold("小游戏设置",false);inlineGames.movePreferencesTo(gameSettings);gameSettings.addView(highRefreshRow,matchWrap());
        content=generalPage;
        LinearLayout systemSettings=fold("系统设置",true);
        Theme.ChalkChoice powerSaving=new Theme.ChalkChoice(this,new String[]{"关","开"});
        powerSaving.setIndex(getSharedPreferences("mobile",0).getBoolean("power_saving",false)?1:0);
        systemSettings.addView(choiceRow(Theme.helpLabel(this,"省电模式","降低后台识图检查和小游戏动画的频率。"),powerSaving,120),matchWrap());
        powerSaving.setListener(i -> getSharedPreferences("mobile",0).edit().putBoolean("power_saving",i==1).apply());
        Theme.ChalkChoice fontChoice=new Theme.ChalkChoice(this,new String[]{"游戏字体","系统字体"});fontChoice.setIndex(getSharedPreferences("mobile",0).getBoolean("fontSystem",false)?1:0);systemSettings.addView(choiceRow(fieldLabel("字体"),fontChoice));fontChoice.setListener(i->{getSharedPreferences("mobile",0).edit().putBoolean("fontSystem",i==1).apply();recreate();});
        SeekBar fontSize=new SeekBar(this);fontSize.setMax(10);fontSize.setProgress(getSharedPreferences("mobile",0).getInt("fontSize",16)-12);systemSettings.addView(Theme.muted(this,"字号（12～22）"));systemSettings.addView(fontSize);fontSize.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){public void onProgressChanged(SeekBar s,int p,boolean user){}public void onStartTrackingTouch(SeekBar s){}public void onStopTrackingTouch(SeekBar s){getSharedPreferences("mobile",0).edit().putInt("fontSize",12+s.getProgress()).apply();recreate();}});
        LinearLayout updates = fold("版本", false);
        Theme.ChalkButton update = new Theme.ChalkButton(this, "检查更新");
        updates.addView(update, matchWrap());
        // The emblem turns while the check runs, in place of a progress bar:
        // the same object, and the same motion, as the in-game button uses to
        // say it is working.
        Theme.Spinner spinner = new Theme.Spinner(this);
        LinearLayout.LayoutParams spinnerParams =
                new LinearLayout.LayoutParams(Theme.px(this, 40), Theme.px(this, 40));
        spinnerParams.topMargin = Theme.px(this, 12);
        spinnerParams.gravity = Gravity.CENTER_HORIZONTAL;
        updates.addView(spinner, spinnerParams);
        updates.addView(Theme.muted(this,"插件主程序 · "+BuildConfig.VERSION_NAME));
        TextView updateStatus = Theme.muted(this, "");
        LinearLayout.LayoutParams updateStatusParams = matchWrap();
        updateStatusParams.topMargin = Theme.px(this, 8);
        updates.addView(updateStatus, updateStatusParams);
        updater = new AppUpdater(this, updateStatus, spinner);
        Theme.SectionHeading updateHeading = (Theme.SectionHeading) updates.getTag();
        updater.onAvailability(available->{hostUpdate=available;updateHeading.setUpdateAvailable(available);update.setUpdateDot(available);update.setText(available?"更新":"检查更新");ActionIcon.set(gearIcon,ActionIcon.GEAR,unread||available);});
        update.setOnClickListener(v -> updater.check());
        updater.checkSilently();
        notesPackages=new ModulePage(mapPage,"notes");moduleManager=new MatchingModuleManager(this);notesPackages.versions.addView(moduleManager);moduleManager.changed=this::moduleActionChanged;
        pvpPackages=new ModulePage(pvpPage,"pvp");pvpManager=pvpPackages.core;
        gamePackages=new ModulePage(gamesPage,"games");gamePackages.versions.addView(inlineGames.takeVersions());
        String initial=state==null?null:state.getString("activeModule");
        if(initial==null)initial=getIntent().getStringExtra("open_module");
        switchModule(initial!=null?initial:getSharedPreferences("mobile",0).getString("last_module","notes"));
        String launch=getIntent().getStringExtra("launch_game");if(launch!=null){getIntent().removeExtra("launch_game");startGame(launch);}
        root.post(()->{
            if(isDestroyed()||isFinishing()||loadingOverlay==null)return;
            final View overlay=loadingOverlay;
            overlay.animate().alpha(0f).setDuration(180).withEndAction(()->{
                startupHost.removeView(overlay);
                if(loadingOverlay==overlay)loadingOverlay=null;
                ReleaseNews.show(this);
            }).start();
        });
        uiReady=true;
        if(deferredCapture!=null){Runnable delivery=deferredCapture;deferredCapture=null;delivery.run();}
        if(resumed)refreshResumedUi();
        // Test builds may carry a game map inside the APK (assets/bundled); merge
        // it into the library once per package. Release builds have no asset.
        new Thread(() -> {
            String note = MatchingModuleStore.installBundled(this, text -> runOnUiThread(() -> { if (!isDestroyed()) status.setText(text); }));
            if (note != null) runOnUiThread(() -> {
                if (isDestroyed()) return;
                status.setText(note);
                if (libraryChoice != null) { libraryChoice.refresh(); libraryChoice.changed.run(); }
            });
        }, "bundled-maps").start();
        android.util.Log.i("CrypticNotes","Main UI constructed: elapsedMs="+(SystemClock.uptimeMillis()-startupAt));
    }

    /**
     * Hand display-only changes to the running service, if there is one.
     *
     * Capture and this screen share a process and both do their work on the main
     * thread, so the call is direct rather than through an Intent. Without it a
     * size or opacity change made here only took effect on the next start.
     */
    private void pushDisplayPreferences() {
        CaptureService service = CaptureService.current;
        if (service != null) service.applyDisplayPreferences();
    }

    /**
     * A fold: the bar and the body it hides, built and added together.
     *
     * The two are separate views and used to be assembled by hand at each call
     * site -- make a heading, make a card, remember to add both. A dropped
     * addView left a section with no bar: nothing on screen to read or to tap,
     * no compile error, no lint, no exception. It happened twice, and the
     * settings it hid were unreachable from this screen both times. Building
     * the pair in one place removes the state where only half of it exists.
     *
     * Returns the body, for the caller to fill.
     */
    private LinearLayout fold(String title, boolean expanded, String icon) {
        Theme.SectionHeading bar = heading(title).setIcon(icon);
        content.addView(bar);
        LinearLayout body = card();
        body.setTag(bar);
        content.addView(body);
        setFoldExpanded(body,expanded);
        bar.setOnClickListener(v -> setFoldExpanded(body,body.getVisibility()!=View.VISIBLE));
        return body;
    }

    private static void setFoldExpanded(LinearLayout body,boolean expanded){
        Theme.SectionHeading bar=(Theme.SectionHeading)body.getTag();
        body.setVisibility(expanded?View.VISIBLE:View.GONE);
        bar.setExpanded(expanded);bar.setTag(expanded);
    }

    private LinearLayout fold(String title, boolean expanded) { return fold(title, expanded, null); }

    private Theme.SectionHeading heading(String label) {
        Theme.SectionHeading view = new Theme.SectionHeading(this, label);
        LinearLayout.LayoutParams params = matchWrap();
        params.topMargin = Theme.px(this, 12);
        view.setLayoutParams(params);
        return view;
    }

    private LinearLayout card() {
        Theme.MistPanel panel = new Theme.MistPanel(this);
        int pad = Theme.px(this, 10);
        panel.setPadding(pad, pad, pad, pad);
        LinearLayout.LayoutParams params = matchWrap();
        params.topMargin = Theme.px(this, 6);
        panel.setLayoutParams(params);
        return panel;
    }

    private TextView fieldLabel(String value) { return fieldLabel(value, null); }
    private TextView fieldLabel(String value, String icon) {
        TextView view = new TextView(this);
        view.setText(value);
        if (icon != null) LineIcon.set(view, icon, Theme.TEXT, 16);
        LinearLayout.LayoutParams params = matchWrap();
        params.topMargin = Theme.px(this, 10);
        params.bottomMargin = Theme.px(this, 4);
        view.setLayoutParams(params);
        return Theme.text(view, 15, Theme.TEXT);
    }

    private static LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
    }

    private LinearLayout choiceRow(View label, View choice) { return choiceRow(label, choice, 0); }
    private LinearLayout choiceRow(View label, View choice, int width) {
        LinearLayout row = new LinearLayout(this);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.addView(label, width>0 ? new LinearLayout.LayoutParams(0, Theme.px(this,46),1) : new LinearLayout.LayoutParams(Theme.px(this,80),Theme.px(this,46)));
        if(label instanceof TextView) ((TextView)label).setGravity(Gravity.CENTER_VERTICAL);
        row.addView(choice, width>0 ? new LinearLayout.LayoutParams(Theme.px(this,width),Theme.px(this,42)) : new LinearLayout.LayoutParams(0,Theme.px(this,46),1));
        return row;
    }

    public void startGame(String id){
        if(!new MatchingModuleStore(this,"games").installed()||!new MiniGameStore(this,id).installed()){switchModule("games");Toast.makeText(this,"请先下载小游戏",Toast.LENGTH_SHORT).show();return;}
        if(MiniGameOverlayService.current!=null&&!id.equals(MiniGameOverlayService.activeGameId)){MiniGameOverlayService.current.switchTo(id);return;}
        if(!Settings.canDrawOverlays(this)){Toast.makeText(this,"请允许显示悬浮窗后再次打开",Toast.LENGTH_LONG).show();startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,Uri.parse("package:"+getPackageName())));return;}
        boolean detection=getSharedPreferences("mobile",0).getBoolean("gameSceneEnabled",true);
        CaptureService service=CaptureService.current;
        if(service!=null&&(!detection||service.hasProjection())){service.openGame(id);return;}
        if(!detection){startForegroundService(new Intent(this,CaptureService.class).setAction("games_only").putExtra("gameOnly",true).putExtra("launchGame",id));return;}
        if(capturePermissionPending)return;pendingGame=id;pendingPvp=false;requestCapturePermission();
    }
    @Override protected void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);if(!uiReady)return;String module=intent.getStringExtra("open_module");if(module!=null)switchModule(module);String game=intent.getStringExtra("launch_game");if(game!=null){intent.removeExtra("launch_game");startGame(game);}}
    @Override protected void onSaveInstanceState(Bundle state){super.onSaveInstanceState(state);state.putString("activeModule",activeModule);state.putString("pendingGame",pendingGame);state.putBoolean("pendingPvp",pendingPvp);state.putBoolean("capturePermissionPending",capturePermissionPending);}

    private void startPvp() {
        if(!pvpManager.store.installed()){refreshPackages();return;}
        if (capturePermissionPending) return;
        if (!Settings.canDrawOverlays(this)) {
            pvpStatus.setText("请允许显示在其他应用上层，返回后再次点击开启。");
            startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName())));
            return;
        }
        pendingGame=null;pendingPvp=true;capturePermissionPending=true;
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS")
                != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 2);
            return;
        }
        requestCapturePermission();
    }

    private void startCapture() {
        pendingPvp=false;
        if(!new MatchingModuleStore(this,libraryChoice.provider()).installed()){
            status.setText("请先下载所选作者的地图库，再开始共享");return;
        }
        pendingGame=null;
        if(!new MatchingModuleStore(this).installed()){status.setText("请先下载加页手记模块");return;}
        if (capturePermissionPending) return;
        if (!Settings.canDrawOverlays(this)) {
            status.setText("请允许显示在其他应用上层，返回后再次点击开启。");
            startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:" + getPackageName())));
            return;
        }
        capturePermissionPending = true;
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS")
                != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 2);
            return;
        }
        requestCapturePermission();
    }

    @Override public void onRequestPermissionsResult(int request, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(request, permissions, results);
        // Notifications are optional. Wait for that dialog to close before
        // presenting projection consent, even when the user declined it.
        if (request == 2) requestCapturePermission();
    }

    private void requestCapturePermission() {
        capturePermissionPending = true;
        MediaProjectionManager manager = (MediaProjectionManager) getSystemService(MEDIA_PROJECTION_SERVICE);
        Intent capture = manager.createScreenCaptureIntent();
        startActivityForResult(capture, 10);
    }

    /**
     * Draw the recording rows from the saved values.
     *
     * One place, because three things can change them: first construction, the
     * return from the permission dialog, and a revert of an unsupported choice.
     * The summary line is derived rather than written out, so it cannot end up
     * describing a tier the switches are not on.
     */
    private void syncRecordingRows() {
        if (recordingSound == null) return;
        // Below Android 10 playback capture does not exist, so "内部声音" is not
        // a choice we can offer -- show 无声 without writing it back.
        boolean audio = RecordPresets.storedInternalAudio(this) && Build.VERSION.SDK_INT >= 29;
        int quality = RecordPresets.storedQualityIndex(this);
        int fpsIndex = RecordPresets.storedFpsIndex(this);
        syncingRecording = true;
        recordingSound.setIndex(audio ? 1 : 0);
        recordingQuality.setIndex(quality);
        recordingFps.setIndex(fpsIndex);
        recordingReplay.setIndex(RecordPresets.replayIndex(RecordPresets.storedReplaySeconds(this)));
        syncingRecording = false;
        boolean missingPermission = audio && checkSelfPermission(android.Manifest.permission.RECORD_AUDIO)
                != android.content.pm.PackageManager.PERMISSION_GRANTED;
        recordingAudioHint.setVisibility(missingPermission ? View.VISIBLE : View.GONE);
        recordingSummary.setText(RecordPresets.describe(quality, RecordPresets.fpsValue(fpsIndex)));
    }

    @Override protected void onResume() {
        super.onResume();resumed=true;
        getSharedPreferences("mobile",0).registerOnSharedPreferenceChangeListener(packagesChanged);
        if(uiReady)refreshResumedUi();
    }
    private void refreshResumedUi(){
        refreshPackages();checkPackages(false);if(inlineGames!=null)inlineGames.probe();
        moduleManager.refresh();
        if(inlineGames!=null)inlineGames.refresh();
        if (updater != null) {
            // Re-attach before resuming: a download started from this screen keeps
            // running after it is left, and its progress should still be here.
            UpdateService.observe(updater);
            updater.resume();
            TextView updateStatus = updater.statusView();
            // Empty means no download has run in this process; leave the standing
            // "检查新版本" line alone rather than blanking it.
            if (!UpdateService.statusText().isEmpty()) updateStatus.setText(UpdateService.statusText());
            // Settle what a download left behind, then finish it. The re-hash runs
            // off the main thread and, with nothing pending, costs two reads.
            new Thread(() -> {
                AppInstaller.reconcile(this, text -> runOnUiThread(() -> updateStatus.setText(text)));
                runOnUiThread(() -> { if (updater != null && !isDestroyed()) updater.installPending(); });
            }, "update-reconcile").start();
        }
        syncRecordingRows();
        if (pvpLast != null) pvpLast.setText(getSharedPreferences("mobile",0).getString("pvp_last","还没有识别到禁用角色"));
        if (libraryChoice != null) {libraryChoice.refresh();libraryChoice.changed.run();}
        if (difficulty != null) {
            libraryChoice.refreshDifficulty(difficulty);
            party.setIndex(getSharedPreferences("mobile", 0).getString("mode", "solo").equals("duo") ? 1 : 0);
        }
    }

    @Override protected void onPause() {
        resumed=false;super.onPause();
        getSharedPreferences("mobile",0).unregisterOnSharedPreferenceChangeListener(packagesChanged);
        UpdateService.unobserve();
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if(DataBackup.handle(this,request,result,data))return;
        if (request != 10) return;
        if(!uiReady){deferredCapture=()->finishCaptureRequest(result,data);return;}
        finishCaptureRequest(result,data);
    }
    private void finishCaptureRequest(int result,Intent data){
        capturePermissionPending = false;
        if(pendingPvp&&!pvpManager.store.installed()){pendingPvp=false;refreshPackages();return;}
        if (result != RESULT_OK || data == null) {
            pendingGame=null;pendingPvp=false;status.setText("未授权屏幕采集，未启动采集");pvpStatus.setText("未授权屏幕采集，未启动采集");
            return;
        }
        stopService(new Intent(this, CaptureService.class));
        Intent service = new Intent(this, CaptureService.class)
                .putExtra("projection", data).putExtra("result", result)
                .putExtra("provider", libraryChoice.provider())
                .putExtra("scene", libraryChoice.scene())
                .putExtra("difficulty", libraryChoice.selected(difficulty))
                .putExtra("mode", libraryChoice.mode(party.getIndex() == 0 ? "solo" : "duo"))
                .putExtra("opacity", opacity)
                .putExtra("gameOnly",pendingGame!=null).putExtra("launchGame",pendingGame).putExtra("pvp",pendingPvp);
        startForegroundService(service);pendingGame=null;
        if(pendingPvp){pendingPvp=false;pvpStatus.setText("悬浮球已开启。回到游戏，在排位选角界面双击悬浮球读取禁用角色。通知栏可随时停止。");return;}
        status.setText("正在启动，准备好后请回到游戏。通知栏可随时停止。");
    }
}
