package com.crypticnotes.mobile;

import android.app.Activity;
import android.app.Dialog;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.graphics.drawable.ColorDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.TextWatcher;
import android.util.DisplayMetrics;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Read-only browser for the maps bundled in the APK.
 *
 * Deliberately read-only: the library ships inside the APK and is re-synced into
 * app storage on every capture start, so enabling/disabling or deleting here
 * would either be undone or silently lie. Importing a map needs the desktop
 * feature extractor, so it is not offered either. Editing the library stays a
 * desktop task.
 */
public class MapLibraryActivity extends Activity {
    private static final String[][] FILTERS = {
            {"全部", ""}, {"困难", "hard"}, {"噩梦·单人", "nightmare/solo"}, {"噩梦·双人", "nightmare/duo"}};

    private final List<MapCatalog.Entry> all = new ArrayList<>();
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService decode = Executors.newSingleThreadExecutor();

    private LinearLayout list;
    private TextView summary;
    private EditText search;
    private int filterIndex;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);

        FrameLayout root = new FrameLayout(this);
        View wallpaper = new View(this);
        wallpaper.setBackground(new Theme.MistDrawable(this));
        root.addView(wallpaper, matchParent());
        root.addView(buildContent(), matchParent());
        setContentView(root);

        all.addAll(MapCatalog.load(this));
        render();
    }

    private View buildContent() {
        ScrollView scroll = new ScrollView(this);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        int pad = Theme.px(this, 20);
        content.setPadding(pad, Theme.px(this, 28), pad, Theme.px(this, 32));
        scroll.addView(content);

        TextView title = new TextView(this);
        title.setText("地图管理");
        content.addView(Theme.text(title, 29, Theme.TITLE));

        summary = Theme.muted(this, "");
        content.addView(summary);

        Theme.ChalkButton back = new Theme.ChalkButton(this, "返回");
        LinearLayout.LayoutParams backParams = wrap();
        backParams.topMargin = Theme.px(this, 14);
        backParams.width = Theme.px(this, 120);
        content.addView(back, backParams);
        back.setOnClickListener(v -> finish());

        content.addView(Theme.muted(this, "内置地图库只读：改动会被下次启动重新同步，录入新图请在电脑端完成。"));

        content.addView(heading("筛选"));
        Theme.MistPanel filters = panel();
        content.addView(filters);
        Theme.ChalkChoice filter = new Theme.ChalkChoice(this, new String[]{"全部", "困难", "噩梦·单人", "噩梦·双人"});
        filters.addView(filter, wrap());
        filter.setListener(index -> {
            filterIndex = index;
            render();
        });

        content.addView(heading("搜索"));
        Theme.MistPanel searchBox = panel();
        content.addView(searchBox);
        search = new EditText(this);
        search.setHint("按地图名称筛选");
        search.setSingleLine(true);
        search.setBackground(new Theme.ChalkDrawable(this, Theme.Chalk.DEEP, .7f, "rounded", true, true));
        search.setPadding(Theme.px(this, 12), Theme.px(this, 10), Theme.px(this, 12), Theme.px(this, 10));
        Theme.text(search, 15, Theme.TEXT);
        search.setHintTextColor(Theme.MUTED);
        search.addTextChangedListener(new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int a, int b, int c) {}
            public void onTextChanged(CharSequence s, int a, int b, int c) {}
            public void afterTextChanged(Editable s) { render(); }
        });
        searchBox.addView(search, wrap());

        content.addView(heading("地图"));
        list = new LinearLayout(this);
        list.setOrientation(LinearLayout.VERTICAL);
        content.addView(list, wrap());
        return scroll;
    }

    private void render() {
        if (list == null) return;
        list.removeAllViews();
        String[] filter = FILTERS[Math.max(0, Math.min(FILTERS.length - 1, filterIndex))];
        String query = search == null ? "" : search.getText().toString().trim().toLowerCase();
        int shown = 0;
        for (MapCatalog.Entry entry : all) {
            if (!filter[1].isEmpty()) {
                String key = entry.difficulty + ("hard".equals(entry.difficulty) ? "" : "/" + entry.mode);
                if (!filter[1].equals(key)) continue;
            }
            if (!query.isEmpty() && !entry.name.toLowerCase().contains(query)
                    && !entry.mapId.toLowerCase().contains(query)) continue;
            list.addView(row(entry));
            shown++;
        }
        if (shown == 0) {
            Theme.MistPanel empty = panel();
            empty.addView(Theme.muted(this, "没有符合条件的地图。"));
            list.addView(empty);
        }
        summary.setText("内置 " + all.size() + " 张 · 当前显示 " + shown + " 张 · 只读");
    }

    private View row(final MapCatalog.Entry entry) {
        Theme.MistPanel card = panel();
        LinearLayout.LayoutParams params = wrap();
        params.topMargin = Theme.px(this, 8);
        card.setLayoutParams(params);

        TextView name = new TextView(this);
        name.setText(entry.name);
        card.addView(Theme.text(name, 16, Theme.TEXT));

        TextView meta = new TextView(this);
        StringBuilder text = new StringBuilder(MapCatalog.contextText(entry.difficulty, entry.mode));
        String floors = MapCatalog.floorText(entry.floors);
        if (!floors.isEmpty()) text.append(" · ").append(floors);
        if (entry.width > 0) text.append(" · ").append(entry.width).append('×').append(entry.height);
        meta.setText(text.toString());
        card.addView(Theme.muted(this, meta.getText().toString()));

        TextView id = new TextView(this);
        id.setText(entry.mapId);
        card.addView(Theme.muted(this, id.getText().toString()));

        card.setOnClickListener(v -> showPreview(entry));
        card.setClickable(true);
        return card;
    }

    /** Whole-image preview, downsampled. Decoding runs off the main thread. */
    private void showPreview(final MapCatalog.Entry entry) {
        final Dialog dialog = new Dialog(this);
        Theme.MistPanel panel = new Theme.MistPanel(this);
        int pad = Theme.px(this, 16);
        panel.setPadding(pad, pad, pad, pad);

        TextView title = new TextView(this);
        title.setText(entry.name);
        panel.addView(Theme.text(title, 20, Theme.TITLE));

        final TextView subtitle = new TextView(this);
        subtitle.setText("正在载入原图…");
        panel.addView(Theme.muted(this, subtitle.getText().toString()));

        final ImageView image = new ImageView(this);
        image.setAdjustViewBounds(true);
        image.setScaleType(ImageView.ScaleType.FIT_CENTER);
        LinearLayout.LayoutParams imageParams = wrap();
        imageParams.topMargin = Theme.px(this, 10);
        panel.addView(image, imageParams);

        Theme.ChalkButton close = new Theme.ChalkButton(this, "关闭");
        LinearLayout.LayoutParams closeParams = wrap();
        closeParams.topMargin = Theme.px(this, 12);
        panel.addView(close, closeParams);
        close.setOnClickListener(v -> dialog.dismiss());

        dialog.setContentView(panel);
        Window window = dialog.getWindow();
        if (window != null) {
            window.setBackgroundDrawable(new ColorDrawable(Color.TRANSPARENT));
            window.setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        }
        dialog.show();

        decode.execute(() -> {
            final Bitmap bitmap = decodeAsset(entry.source, 1280);
            main.post(() -> {
                if (isFinishing() || isDestroyed()) {
                    if (bitmap != null) bitmap.recycle();
                    return;
                }
                if (bitmap == null) {
                    subtitle.setText("原图读取失败。");
                    return;
                }
                subtitle.setText(bitmap.getWidth() + "×" + bitmap.getHeight() + " · " + entry.mapId);
                // Fit inside the dialog box; a 1000x3000 map would otherwise run off screen.
                DisplayMetrics metrics = getResources().getDisplayMetrics();
                float fit = Math.min(metrics.widthPixels * .80f / bitmap.getWidth(),
                        metrics.heightPixels * .62f / bitmap.getHeight());
                image.setLayoutParams(new LinearLayout.LayoutParams(
                        Math.max(1, Math.round(bitmap.getWidth() * fit)),
                        Math.max(1, Math.round(bitmap.getHeight() * fit))));
                image.setImageBitmap(bitmap);
            });
        });
    }

    /** Bounds pass first so a 1000×3000 map is never decoded at full size for a preview. */
    private Bitmap decodeAsset(String path, int maxDimension) {
        try (InputStream probe = getAssets().open(path)) {
            BitmapFactory.Options bounds = new BitmapFactory.Options();
            bounds.inJustDecodeBounds = true;
            BitmapFactory.decodeStream(probe, null, bounds);
            int sample = 1;
            while (Math.max(bounds.outWidth, bounds.outHeight) / sample > maxDimension * 2) sample *= 2;
            BitmapFactory.Options options = new BitmapFactory.Options();
            options.inSampleSize = sample;
            options.inPreferredConfig = Bitmap.Config.RGB_565;
            try (InputStream stream = getAssets().open(path)) {
                return BitmapFactory.decodeStream(stream, null, options);
            }
        } catch (IOException | OutOfMemoryError error) {
            return null;
        }
    }

    @Override protected void onDestroy() {
        decode.shutdownNow();
        super.onDestroy();
    }

    private Theme.SectionHeading heading(String label) {
        Theme.SectionHeading view = new Theme.SectionHeading(this, label);
        LinearLayout.LayoutParams params = wrap();
        params.topMargin = Theme.px(this, 22);
        params.bottomMargin = Theme.px(this, 2);
        view.setLayoutParams(params);
        return view;
    }

    private Theme.MistPanel panel() {
        Theme.MistPanel panel = new Theme.MistPanel(this);
        int pad = Theme.px(this, 14);
        panel.setPadding(pad, pad, pad, pad);
        panel.setLayoutParams(wrap());
        return panel;
    }

    private static LinearLayout.LayoutParams wrap() {
        return new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
    }

    private static FrameLayout.LayoutParams matchParent() {
        return new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT);
    }
}
