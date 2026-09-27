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

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);

        FrameLayout root = new FrameLayout(this);
        View wallpaper = new View(this);
        wallpaper.setBackground(new Theme.MistDrawable(this));
        root.addView(wallpaper, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        ScrollView scroll = new ScrollView(this);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        int pad = Theme.px(this, 20);
        content.setPadding(pad, Theme.px(this, 28), pad, Theme.px(this, 32));
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
        content.addView(Theme.text(title, 29, Theme.TITLE));
        TextView subtitle = new TextView(this);
        subtitle.setText("Android 预览版 · 截图只在本机处理，不上传");
        content.addView(Theme.muted(this, subtitle.getText().toString()));

        content.addView(heading("识别设置"));
        LinearLayout recognition = card();
        content.addView(recognition);
        recognition.addView(fieldLabel("难度"));
        difficulty = new Theme.ChalkChoice(this, new String[]{"困难", "噩梦"});
        recognition.addView(difficulty, matchWrap());
        TextView routeLabel = fieldLabel("参考路线");
        recognition.addView(routeLabel);
        party = new Theme.ChalkChoice(this, new String[]{"单人路线", "多人路线"});
        recognition.addView(party, matchWrap());
        difficulty.setIndex(getSharedPreferences("mobile", 0).getString("difficulty", "hard").equals("nightmare") ? 1 : 0);
        party.setIndex(getSharedPreferences("mobile", 0).getString("mode", "solo").equals("duo") ? 1 : 0);
        difficulty.setListener(i -> {
            getSharedPreferences("mobile", 0).edit().putString("difficulty", i == 0 ? "hard" : "nightmare").apply();
            party.setVisibility(i == 1 ? View.VISIBLE : View.GONE);
            routeLabel.setVisibility(i == 1 ? View.VISIBLE : View.GONE);
        });
        party.setVisibility(difficulty.getIndex() == 1 ? View.VISIBLE : View.GONE);
        routeLabel.setVisibility(party.getVisibility());
        party.setListener(i -> getSharedPreferences("mobile", 0).edit().putString("mode", i == 0 ? "solo" : "duo").apply());

        final TextView opacityLabel = fieldLabel("叠图不透明度 30%");
        recognition.addView(opacityLabel);
        Theme.ChalkSlider slider = new Theme.ChalkSlider(this, 65, 25);
        recognition.addView(slider, matchWrap());
        slider.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            public void onProgressChanged(SeekBar bar, int value, boolean fromUser) {
                opacity = value + 5;
                opacityLabel.setText("叠图不透明度 " + opacity + "%");
            }
            public void onStartTrackingTouch(SeekBar bar) {}
            public void onStopTrackingTouch(SeekBar bar) {}
        });
        opacity = 30;

        LinearLayout actions = card();
        content.addView(actions, 2);
        LinearLayout serviceActions = new LinearLayout(this);
        actions.addView(serviceActions, matchWrap());
        Theme.ChalkButton start = new Theme.ChalkButton(this, "开启自动识图", true);
        LinearLayout.LayoutParams startParams = new LinearLayout.LayoutParams(0, Theme.px(this, 48), 2);
        startParams.rightMargin = Theme.px(this, 8);
        serviceActions.addView(start, startParams);
        start.setOnClickListener(v -> startCapture());
        Theme.ChalkButton stop = new Theme.ChalkButton(this, "停止");
        serviceActions.addView(stop, new LinearLayout.LayoutParams(0, Theme.px(this, 48), 1));
        stop.setOnClickListener(v -> {
            stopService(new Intent(this, CaptureService.class));
            status.setText("已停止");
        });

        Theme.ChalkButton advanced = new Theme.ChalkButton(this, "更多设置  ›");
        content.addView(advanced, matchWrap());
        LinearLayout extras = card();
        content.addView(extras);
        extras.setVisibility(View.GONE);
        advanced.setOnClickListener(v -> extras.setVisibility(extras.getVisibility() == View.VISIBLE ? View.GONE : View.VISIBLE));
        final Theme.ChalkToggle tapMode = new Theme.ChalkToggle(this, "点击区域触发（需无障碍手势授权）", 140);
        tapMode.setChecked(getSharedPreferences("mobile", 0).getBoolean("tap_mode", false));
        extras.addView(tapMode, matchWrap());
        tapMode.setListener(checked -> {
            getSharedPreferences("mobile", 0).edit().putBoolean("tap_mode", checked).apply();
            if (checked && TapRelayService.current == null)
                startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS));
        });
        Theme.ChalkButton manage = new Theme.ChalkButton(this, "地图管理");
        extras.addView(manage, matchWrap());
        manage.setOnClickListener(v -> startActivity(new Intent(this, MapLibraryActivity.class)));
        extras.addView(Theme.muted(this, "游戏内拖动小悬浮按钮调整位置，点击打开设置。"));

        status = Theme.status(this);
        status.setText("首次启动需要悬浮窗与屏幕采集授权。");
        LinearLayout.LayoutParams statusParams = matchWrap();
        statusParams.topMargin = Theme.px(this, 18);
        actions.addView(status, statusParams);
        content.addView(heading("应用更新"));
        LinearLayout updates = card();
        content.addView(updates);
        TextView updateStatus = Theme.muted(this, "检查新版本，保留已有设置");
        ProgressBar progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        progress.setProgressTintList(android.content.res.ColorStateList.valueOf(Theme.TEXT));
        progress.setProgressBackgroundTintList(android.content.res.ColorStateList.valueOf(0xff263b49));
        progress.setVisibility(View.GONE);
        updater = new AppUpdater(this, updateStatus, progress);
        Theme.ChalkButton update = new Theme.ChalkButton(this, "检查应用更新");
        updates.addView(update, matchWrap());
        updates.addView(progress, new LinearLayout.LayoutParams(-1, Theme.px(this, 12)));
        updates.addView(updateStatus, matchWrap());
        update.setOnClickListener(v -> updater.check());

        TextView footnote = new TextView(this);
        footnote.setText("识图全程单线程，避免与游戏争抢 CPU。采集期间请保持横屏，退出游戏后点通知栏停止。");
        LinearLayout.LayoutParams footnoteParams = matchWrap();
        footnoteParams.topMargin = Theme.px(this, 12);
        content.addView(Theme.muted(this, footnote.getText().toString()), footnoteParams);
    }

    private Theme.SectionHeading heading(String label) {
        Theme.SectionHeading view = new Theme.SectionHeading(this, label);
        LinearLayout.LayoutParams params = matchWrap();
        params.topMargin = Theme.px(this, 22);
        view.setLayoutParams(params);
        return view;
    }

    private LinearLayout card() {
        Theme.MistPanel panel = new Theme.MistPanel(this);
        int pad = Theme.px(this, 14);
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
