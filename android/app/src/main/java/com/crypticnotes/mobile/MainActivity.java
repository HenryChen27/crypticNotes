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
    private Theme.SectionHeading gameHeading;
    private InlineGameManager inlineGames;
    private Theme.ChalkChoice difficulty, party;
    private int opacity = 30;
    private AppUpdater updater;
    private boolean capturePermissionPending;
    private Theme.ChalkChoice recordingSound, recordingQuality, recordingFps;
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
    private LinearLayout content,mapPage,gamesPage,generalPage;
    private Theme.SectionHeading moduleHeading;
    private MatchingModuleManager moduleManager;
    private String pendingGame;
    private View mapActions;
    private DarkTab notesTab,gamesTab;
    private void switchModule(String name){mapPage.setVisibility(name.equals("notes")?View.VISIBLE:View.GONE);gamesPage.setVisibility(name.equals("games")?View.VISIBLE:View.GONE);generalPage.setVisibility(name.equals("settings")?View.VISIBLE:View.GONE);notesTab.select(name.equals("notes"));gamesTab.select(name.equals("games"));if(!name.equals("settings"))getSharedPreferences("mobile",0).edit().putString("last_module",name).apply();}
    private LinearLayout newPage(){LinearLayout page=new LinearLayout(this);page.setOrientation(LinearLayout.VERTICAL);return page;}
    private void updateModuleUi(){boolean installed=new MatchingModuleStore(this).installed();for(int i=0;i<mapPage.getChildCount();i++){View child=mapPage.getChildAt(i);boolean visible=installed;if(child.getTag() instanceof Theme.SectionHeading){Object state=((Theme.SectionHeading)child.getTag()).getTag();visible=installed&&!Boolean.FALSE.equals(state);}child.setVisibility(visible?View.VISIBLE:View.GONE);}moduleHeading.setVisibility(installed?View.VISIBLE:View.GONE);moduleManager.setVisibility(View.VISIBLE);moduleHeading.setExpanded(installed);}


    @Override public void onCreate(Bundle state) {
        super.onCreate(state);

        FrameLayout root = new FrameLayout(this);
        View wallpaper = new View(this);
        wallpaper.setBackground(new Theme.MistDrawable(this));
        root.addView(wallpaper, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        ScrollView scroll = new ScrollView(this);
        content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        int pad = Theme.px(this, 20);
        content.setPadding(pad, Theme.px(this, 16), pad, Theme.px(this, 20));
        scroll.addView(content);
        root.addView(scroll, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(root);
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            v.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                    insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            return insets.consumeSystemWindowInsets();
        });

        TextView subtitle = new TextView(this);
        subtitle.setText("Android 预览版 · 截图只在本机处理，不上传");
        content.addView(Theme.muted(this, subtitle.getText().toString()));
        Theme.Rule rule = new Theme.Rule(this);
        LinearLayout.LayoutParams ruleParams = matchWrap();
        ruleParams.topMargin = Theme.px(this, 10);
        content.addView(rule, ruleParams);

        LinearLayout host=content;
        LinearLayout navigation=new LinearLayout(this);notesTab=new DarkTab(this,"加页手记");gamesTab=new DarkTab(this,"小游戏");TextView gear=new TextView(this);ActionIcon.set(gear,ActionIcon.GEAR,false);gear.setGravity(Gravity.CENTER);
        navigation.addView(notesTab,new LinearLayout.LayoutParams(0,Theme.px(this,48),1));navigation.addView(gamesTab,new LinearLayout.LayoutParams(0,Theme.px(this,48),1));navigation.addView(gear,new LinearLayout.LayoutParams(Theme.px(this,48),Theme.px(this,48)));host.addView(navigation);
        mapPage=newPage();gamesPage=newPage();generalPage=newPage();host.addView(mapPage);host.addView(gamesPage);host.addView(generalPage);content=mapPage;
        notesTab.setOnClickListener(v->switchModule("notes"));gamesTab.setOnClickListener(v->switchModule("games"));gear.setOnClickListener(v->switchModule("settings"));
        // Starting is what this screen is for, so it sits above everything else
        // and outside the fold: the primary surface, the largest control, and
        // the only one that never scrolls out of the way.
        LinearLayout actions = card();
        content.addView(actions);mapActions=actions;
        status = Theme.status(this);
        status.setText("首次启动需要悬浮窗与屏幕采集授权。");
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

        difficulty = new Theme.ChalkChoice(this, new String[]{"困难", "噩梦"});
        settings.addView(choiceRow(fieldLabel("难度"), difficulty), matchWrap());
        TextView routeLabel = fieldLabel("参考路线");
        party = new Theme.ChalkChoice(this, new String[]{"单人路线", "多人路线"});
        LinearLayout routeRow = choiceRow(routeLabel, party);
        settings.addView(routeRow, matchWrap());
        difficulty.setIndex(getSharedPreferences("mobile", 0).getString("difficulty", "hard").equals("nightmare") ? 1 : 0);
        party.setIndex(getSharedPreferences("mobile", 0).getString("mode", "solo").equals("duo") ? 1 : 0);
        difficulty.setListener(i -> {
            getSharedPreferences("mobile", 0).edit().putString("difficulty", i == 0 ? "hard" : "nightmare").apply();
            party.setVisibility(i == 1 ? View.VISIBLE : View.GONE);
            routeLabel.setVisibility(i == 1 ? View.VISIBLE : View.GONE);
            routeRow.setVisibility(i == 1 ? View.VISIBLE : View.GONE);
        });
        party.setVisibility(difficulty.getIndex() == 1 ? View.VISIBLE : View.GONE);
        routeLabel.setVisibility(party.getVisibility());
        routeRow.setVisibility(party.getVisibility());
        party.setListener(i -> getSharedPreferences("mobile", 0).edit().putString("mode", i == 0 ? "solo" : "duo").apply());

        // Same preference key the in-game panel writes, so a value set mid-game
        // survives a restart instead of being reset here on every launch.
        opacity = getSharedPreferences("mobile", 0).getInt("opacity", 30);
        final TextView opacityLabel = fieldLabel("叠图不透明度 " + opacity + "%");
        settings.addView(opacityLabel);
        Theme.ChalkSlider slider = new Theme.ChalkSlider(this, 65,
                Math.max(0, Math.min(65, opacity - 5)));
        settings.addView(slider, matchWrap());
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
        settings.addView(badgeLabel);
        Theme.ChalkSlider badgeSlider = new Theme.ChalkSlider(this, 90,
                Math.max(0, Math.min(90, Math.round(badgeScale * 100) - 70)));
        settings.addView(badgeSlider, matchWrap());
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
        Theme.ChalkChoice powerSaving=new Theme.ChalkChoice(this,new String[]{"关","开"});
        powerSaving.setIndex(getSharedPreferences("mobile",0).getBoolean("power_saving",false)?1:0);
        more.addView(choiceRow(Theme.helpLabel(this,"省电模式","降低检查频率；小游戏采用更小动画缓存并最多请求60Hz，重开小游戏生效。手动识别不受等待限制。"),powerSaving,120),matchWrap());
        powerSaving.setListener(i -> getSharedPreferences("mobile",0).edit().putBoolean("power_saving",i==1).apply());
        Theme.ChalkChoice feedback = new Theme.ChalkChoice(this,new String[]{"关","开"});
        feedback.setIndex(getSharedPreferences("mobile",0).getBoolean("touch_feedback",true)?1:0);
        more.addView(choiceRow(fieldLabel("轻触反馈"),feedback,120),matchWrap());
        feedback.setListener(i -> getSharedPreferences("mobile",0).edit().putBoolean("touch_feedback",i==1).apply());
        more.addView(Theme.helpLabel(this, "点击触发", "可选功能，需要无障碍手势授权。仅转交地图入口范围的触摸；关闭后仍可通过画面自动检测地图。"));
        final Theme.ChalkToggle tapMode = new Theme.ChalkToggle(this, "启用", 120);
        tapMode.setChecked(getSharedPreferences("mobile", 0).getBoolean("tap_mode", false));
        more.addView(tapMode, matchWrap());
        tapMode.setListener(checked -> {
            getSharedPreferences("mobile", 0).edit().putBoolean("tap_mode", checked).apply();
            if (checked && TapRelayService.current == null)
                startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS));
        });
        Theme.ChalkButton manage = new Theme.ChalkButton(this, "地图管理");
        more.addView(manage, matchWrap());
        manage.setOnClickListener(v -> startActivity(new Intent(this, MapLibraryActivity.class)));
        // Dragging the button is easier than explaining where it went, so the
        // reset only has to forget the stored spot; the next start puts it back
        // at the default corner.
        Theme.ChalkButton reset = new Theme.ChalkButton(this, "重置悬浮球位置");
        more.addView(reset, matchWrap());
        reset.setOnClickListener(v -> {
            getSharedPreferences("mobile", 0).edit()
                    .remove("badge_x").remove("badge_y").apply();
            pushDisplayPreferences();
            Toast.makeText(this, "悬浮球已回到默认位置", Toast.LENGTH_SHORT).show();
        });
        more.addView(Theme.helpLabel(this, "悬浮操作", "拖动悬浮按钮移动位置，点击打开设置，长按关闭识别。通知栏也可停止采集。"));
        TextView footnote = new TextView(this);
        footnote.setText("识图全程单线程，避免与游戏争抢 CPU。采集期间请保持横屏，退出游戏后点通知栏停止。");
        LinearLayout.LayoutParams footnoteParams = matchWrap();
        footnoteParams.topMargin = Theme.px(this, 12);

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

        recordingSummary = Theme.muted(this,"");
        LinearLayout.LayoutParams summaryParams = matchWrap();
        summaryParams.topMargin = Theme.px(this, 8);
        recording.addView(recordingSummary, summaryParams);
        syncRecordingRows();
        recording.addView(Theme.helpLabel(this,"保存与操作","从悬浮球设置开始／停止录制。Android 10+ 保存到相册 Movies/CrypticNotes，转屏会保存当前视频。录叠图演示请选择共享整个屏幕。设置改动在下次录制生效。"));

        content=gamesPage;
        LinearLayout games = fold("小游戏", true);
        gameHeading=(Theme.SectionHeading)games.getTag();
        gameHeading.setUpdateAvailable(MiniGameUpdates.available(this));
        inlineGames=new InlineGameManager(this);
        inlineGames.stateChanged=()->gameHeading.setUpdateAvailable(MiniGameUpdates.available(this));
        games.addView(inlineGames,matchWrap());
        content=generalPage;
        content.addView(Theme.muted(this,"主程序版本 "+BuildConfig.VERSION_NAME+"（"+BuildConfig.VERSION_CODE+"）"));
        LinearLayout appearance=fold("界面设置",true);
        Theme.ChalkChoice fontChoice=new Theme.ChalkChoice(this,new String[]{"游戏字体","系统字体"});fontChoice.setIndex(getSharedPreferences("mobile",0).getBoolean("fontSystem",false)?1:0);appearance.addView(choiceRow(fieldLabel("字体"),fontChoice));fontChoice.setListener(i->{getSharedPreferences("mobile",0).edit().putBoolean("fontSystem",i==1).apply();recreate();});
        SeekBar fontSize=new SeekBar(this);fontSize.setMax(10);fontSize.setProgress(getSharedPreferences("mobile",0).getInt("fontSize",16)-12);appearance.addView(Theme.muted(this,"字号（12～22）"));appearance.addView(fontSize);fontSize.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){public void onProgressChanged(SeekBar s,int p,boolean user){}public void onStartTrackingTouch(SeekBar s){}public void onStopTrackingTouch(SeekBar s){getSharedPreferences("mobile",0).edit().putInt("fontSize",12+s.getProgress()).apply();recreate();}});
        LinearLayout updates = fold("应用更新", false);
        Theme.ChalkButton update = new Theme.ChalkButton(this, "检查应用更新");
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
        TextView updateStatus = Theme.muted(this, "当前版本 " + BuildConfig.VERSION_NAME + " · 检查新版本，保留已有设置");
        LinearLayout.LayoutParams updateStatusParams = matchWrap();
        updateStatusParams.topMargin = Theme.px(this, 8);
        updates.addView(updateStatus, updateStatusParams);
        updater = new AppUpdater(this, updateStatus, spinner);
        Theme.SectionHeading updateHeading = (Theme.SectionHeading) updates.getTag();
        updater.onAvailability(updateHeading::setUpdateAvailable);
        update.setOnClickListener(v -> updater.check());
        updater.checkSilently();
        content=mapPage;moduleManager=new MatchingModuleManager(this);moduleHeading=heading("版本");moduleHeading.setExpanded(false);mapPage.addView(moduleHeading);mapPage.addView(moduleManager);moduleHeading.setOnClickListener(v->{boolean open=moduleManager.getVisibility()!=View.VISIBLE;moduleManager.setVisibility(open?View.VISIBLE:View.GONE);moduleHeading.setExpanded(open);});moduleManager.changed=()->{updateModuleUi();};updateModuleUi();
        if(new MatchingModuleStore(this).installed()){moduleManager.setVisibility(View.GONE);moduleHeading.setExpanded(false);}
        switchModule(getIntent().getStringExtra("open_module")!=null?getIntent().getStringExtra("open_module"):getSharedPreferences("mobile",0).getString("last_module","notes"));
        if(state!=null)pendingGame=state.getString("pendingGame");
        String launch=getIntent().getStringExtra("launch_game");if(launch!=null){getIntent().removeExtra("launch_game");startGame(launch);}
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
    private LinearLayout fold(String title, boolean expanded) {
        Theme.SectionHeading bar = heading(title);
        content.addView(bar);
        LinearLayout body = card();
        body.setTag(bar);
        content.addView(body);
        body.setVisibility(expanded ? View.VISIBLE : View.GONE);
        bar.setExpanded(expanded);bar.setTag(expanded);
        bar.setOnClickListener(v -> {
            boolean open = body.getVisibility() != View.VISIBLE;
            body.setVisibility(open ? View.VISIBLE : View.GONE);
            bar.setExpanded(open);bar.setTag(open);
        });
        return body;
    }

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

    private TextView fieldLabel(String value) {
        TextView view = new TextView(this);
        view.setText(value);
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
        if(!new MiniGameStore(this,id).installed()){Toast.makeText(this,"请先下载小游戏",Toast.LENGTH_SHORT).show();return;}
        if(MiniGameOverlayService.running&&!id.equals(MiniGameOverlayService.activeGameId)){Toast.makeText(this,"请先关闭当前小游戏",Toast.LENGTH_SHORT).show();return;}
        if(!Settings.canDrawOverlays(this)){Toast.makeText(this,"请允许显示悬浮窗后再次打开",Toast.LENGTH_LONG).show();startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,Uri.parse("package:"+getPackageName())));return;}
        boolean detection=getSharedPreferences("mobile",0).getBoolean("gameSceneEnabled",true);
        CaptureService service=CaptureService.current;
        if(service!=null&&(!detection||service.hasProjection())){service.openGame(id);return;}
        if(!detection){startForegroundService(new Intent(this,CaptureService.class).setAction("games_only").putExtra("gameOnly",true).putExtra("launchGame",id));return;}
        if(capturePermissionPending)return;pendingGame=id;requestCapturePermission();
    }
    @Override protected void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);String module=intent.getStringExtra("open_module");if(module!=null)switchModule(module);String game=intent.getStringExtra("launch_game");if(game!=null){intent.removeExtra("launch_game");startGame(game);}}
    @Override protected void onSaveInstanceState(Bundle state){super.onSaveInstanceState(state);state.putString("pendingGame",pendingGame);}

    private void startCapture() {
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
        syncingRecording = false;
        boolean missingPermission = audio && checkSelfPermission(android.Manifest.permission.RECORD_AUDIO)
                != android.content.pm.PackageManager.PERMISSION_GRANTED;
        recordingAudioHint.setVisibility(missingPermission ? View.VISIBLE : View.GONE);
        recordingSummary.setText(RecordPresets.describe(quality, RecordPresets.fpsValue(fpsIndex)));
    }

    @Override protected void onResume() {
        super.onResume();
        if(inlineGames!=null)inlineGames.refresh();
        if(gameHeading!=null){gameHeading.setUpdateAvailable(MiniGameUpdates.available(this));MiniGameUpdates.check(this,()->{if(!isDestroyed()&&gameHeading!=null)gameHeading.setUpdateAvailable(MiniGameUpdates.available(this));if(inlineGames!=null)inlineGames.refresh();});}
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
        if (difficulty != null) {
            difficulty.setIndex(getSharedPreferences("mobile", 0).getString("difficulty", "hard").equals("nightmare") ? 1 : 0);
            party.setIndex(getSharedPreferences("mobile", 0).getString("mode", "solo").equals("duo") ? 1 : 0);
        }
    }

    @Override protected void onPause() {
        super.onPause();
        UpdateService.unobserve();
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if(DataBackup.handle(this,request,result,data))return;
        if (request != 10) return;
        capturePermissionPending = false;
        if (result != RESULT_OK || data == null) {
            pendingGame=null;status.setText("未授权屏幕采集，未启动采集");
            return;
        }
        stopService(new Intent(this, CaptureService.class));
        Intent service = new Intent(this, CaptureService.class)
                .putExtra("projection", data).putExtra("result", result)
                .putExtra("difficulty", difficulty.getIndex() == 0 ? "hard" : "nightmare")
                .putExtra("mode", party.getIndex() == 0 ? "solo" : "duo")
                .putExtra("opacity", opacity)
                .putExtra("gameOnly",pendingGame!=null).putExtra("launchGame",pendingGame);
        startForegroundService(service);pendingGame=null;
        status.setText("正在启动，准备好后请回到游戏。通知栏可随时停止。");
    }
}
