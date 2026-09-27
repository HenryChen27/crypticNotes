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
    private Theme.ChalkChoice difficulty, party;
    private int opacity = 30;
    private AppUpdater updater;
    /** The scrolling column everything on this screen is added to. */
    private LinearLayout content;

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

        TextView title = new TextView(this);
        title.setText("加页手记");
        content.addView(Theme.text(title, 25, Theme.TITLE));
        TextView subtitle = new TextView(this);
        subtitle.setText("Android 预览版 · 截图只在本机处理，不上传");
        content.addView(Theme.muted(this, subtitle.getText().toString()));
        Theme.Rule rule = new Theme.Rule(this);
        LinearLayout.LayoutParams ruleParams = matchWrap();
        ruleParams.topMargin = Theme.px(this, 10);
        content.addView(rule, ruleParams);

        // Starting is what this screen is for, so it sits above everything else
        // and outside the fold: the primary surface, the largest control, and
        // the only one that never scrolls out of the way.
        LinearLayout actions = card();
        content.addView(actions);
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
        // first, then the display tweaks, then the once-in-a-while ones. Closed
        // by default, so the screen opens on starting; the state is a reading
        // preference, not a setting, so it is deliberately not persisted.
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
        more.addView(Theme.helpLabel(this, "点击触发", "可选功能，需要无障碍手势授权。仅转交地图入口范围的触摸；关闭后仍可通过画面自动检测地图。"));
        final Theme.ChalkToggle tapMode = new Theme.ChalkToggle(this, "启用", 140);
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
        TextView updateStatus = Theme.muted(this, "检查新版本，保留已有设置");
        LinearLayout.LayoutParams updateStatusParams = matchWrap();
        updateStatusParams.topMargin = Theme.px(this, 8);
        updates.addView(updateStatus, updateStatusParams);
        updater = new AppUpdater(this, updateStatus, spinner);
        update.setOnClickListener(v -> updater.check());
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
        content.addView(body);
        body.setVisibility(expanded ? View.VISIBLE : View.GONE);
        bar.setExpanded(expanded);
        bar.setOnClickListener(v -> {
            boolean open = body.getVisibility() != View.VISIBLE;
            body.setVisibility(open ? View.VISIBLE : View.GONE);
            bar.setExpanded(open);
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

    private LinearLayout choiceRow(TextView label, View choice) {
        LinearLayout row = new LinearLayout(this);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.addView(label, new LinearLayout.LayoutParams(Theme.px(this, 80), Theme.px(this, 46)));
        label.setGravity(Gravity.CENTER_VERTICAL);
        row.addView(choice, new LinearLayout.LayoutParams(0, Theme.px(this, 46), 1));
        return row;
    }

    private void startCapture() {
        if (!Settings.canDrawOverlays(this)) {
            status.setText("请允许显示在其他应用上层，返回后再次点击开启。");
            startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:" + getPackageName())));
            return;
        }
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS")
                != android.content.pm.PackageManager.PERMISSION_GRANTED)
            requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 2);
        MediaProjectionManager manager = (MediaProjectionManager) getSystemService(MEDIA_PROJECTION_SERVICE);
        Intent capture = Build.VERSION.SDK_INT >= 34
                ? manager.createScreenCaptureIntent(MediaProjectionConfig.createConfigForDefaultDisplay())
                : manager.createScreenCaptureIntent();
        startActivityForResult(capture, 10);
    }

    @Override protected void onResume() {
        super.onResume();
        if (updater != null) updater.resume();
        if (difficulty != null) {
            difficulty.setIndex(getSharedPreferences("mobile", 0).getString("difficulty", "hard").equals("nightmare") ? 1 : 0);
            party.setIndex(getSharedPreferences("mobile", 0).getString("mode", "solo").equals("duo") ? 1 : 0);
        }
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != 10) return;
        if (result != RESULT_OK || data == null) {
            status.setText("未授权屏幕采集");
            return;
        }
        stopService(new Intent(this, CaptureService.class));
        Intent service = new Intent(this, CaptureService.class)
                .putExtra("projection", data).putExtra("result", result)
                .putExtra("difficulty", difficulty.getIndex() == 0 ? "hard" : "nightmare")
                .putExtra("mode", party.getIndex() == 0 ? "solo" : "duo")
                .putExtra("opacity", opacity);
        startForegroundService(service);
        status.setText("正在启动，准备好后请回到游戏。通知栏可随时停止。");
    }
}
