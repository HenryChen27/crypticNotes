package com.crypticnotes.mobile;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.*;
import android.graphics.drawable.Drawable;
import android.util.LruCache;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.TextView;

import java.util.Random;

/**
 * Android port of the desktop theme (mapmatching/theme.py).
 *
 * Same idea as the desktop: every surface is a chalk/frost texture painted from
 * a deterministic noise field, not a flat fill. Colours and geometry mirror the
 * desktop palette so both clients read as one product.
 *
 * One deliberate difference: the desktop renders the texture into a 2x buffer
 * and lets Qt scale it down, because Qt sizes are logical pixels. Android view
 * sizes are already device pixels, so the numbers here are the desktop's 2x-grid
 * values converted to density-independent units and then multiplied back by the
 * display density. That reproduces the same physical grain size instead of the
 * same pixel count.
 */
public final class Theme {
    private Theme() {}

    // ---- palette (stylesheet() in theme.py) ----
    public static final int TEXT = 0xffd4e1e8;
    public static final int TITLE = 0xffe3edf2;
    public static final int MUTED = 0xff9cadbb;
    public static final int HEADING = 0xffd3dfe6;
    public static final int INK = 0xff152635;          // dark text on light chalk
    public static final int CHOICE_IDLE = 0xffb5c9d7;
    public static final int ACCENT = 0xff859daf;

    /** Chalk palette selector. Mirrors the `bright` argument of chalk_texture(). */
    public enum Chalk { NORMAL, BRIGHT, WHITE, DARK, DEEP }

    private static final LruCache<String, Bitmap> CACHE = new LruCache<>(64);
    /** Shared blit paint; drawing only ever happens on the UI thread. */
    public static final Paint SCALE = new Paint(Paint.FILTER_BITMAP_FLAG);
    private static Typeface typeface;

    public static float dp(Context context) {
        return context.getResources().getDisplayMetrics().density;
    }

    public static int px(Context context, float value) {
        return Math.round(value * dp(context));
    }

    /** Bundled desktop font, staged from mapmatching/assets/fonts by prepare_android.py. */
    public static Typeface typeface(Context context) {
        if (typeface == null) {
            try {
                typeface = Typeface.createFromAsset(context.getAssets(), "fonts/HYDiWRGJ.ttf");
            } catch (Exception ignored) {
                typeface = Typeface.SANS_SERIF;
            }
        }
        return typeface;
    }

    public static <T extends TextView> T text(T view, float sizeDp, int color) {
        view.setTextSize(TypedValue.COMPLEX_UNIT_DIP, sizeDp);
        view.setTextColor(color);
        view.setTypeface(typeface(view.getContext()));
        return view;
    }

    // ---- chalk texture -----------------------------------------------------

    /**
     * Deterministic chalk surface with feathered, broken edges.
     *
     * Direct translation of chalk_texture(); the random draws stay in the same
     * order (grain, then feather jitter, then alpha jitter) so the texture reads
     * the same as the desktop one.
     */
    public static Bitmap chalk(Context context, int width, int height, Chalk mode,
                               float roughness, String shape,
                               boolean leftEdge, boolean rightEdge) {
        float scale = dp(context);
        int w = Math.max(2, width), h = Math.max(2, height);
        String key = w + "x" + h + mode + roughness + shape + leftEdge + rightEdge;
        Bitmap cached = CACHE.get(key);
        if (cached != null) return cached;

        boolean dark = mode == Chalk.DARK || mode == Chalk.DEEP;
        boolean bright = mode != Chalk.NORMAL;
        int[] palette;
        switch (mode) {
            case DEEP: palette = new int[]{16, 29, 40}; break;
            case DARK: palette = new int[]{35, 54, 70}; break;
            case WHITE: palette = new int[]{210, 225, 232}; break;
            case BRIGHT: palette = new int[]{190, 209, 219}; break;
            default: palette = new int[]{158, 181, 197}; break;
        }
        float grain = 10f, featherUnit = 6f * scale, jitter = 2.5f * scale;
        // Softer than the desktop's 4dp: phone controls sit alone against a
        // bright game, where the squarer corner read as a clipped rectangle.
        float radius = 3f * scale;
        float alphaBase = bright ? 235f : 190f, alphaJitter = 4f * scale;

        int[] pixels = new int[w * h];
        Random random = new Random(23);
        float[] grainField = new float[w * h];
        for (int i = 0; i < grainField.length; i++) grainField[i] = (float) random.nextGaussian();
        float[] edgeJitter = new float[w * h];
        for (int i = 0; i < edgeJitter.length; i++) edgeJitter[i] = random.nextFloat() * 5f * roughness;
        float[] alphaField = new float[w * h];
        for (int i = 0; i < alphaField.length; i++) alphaField[i] = (float) random.nextGaussian();

        for (int y = 0; y < h; y++) {
            for (int x = 0; x < w; x++) {
                int i = y * w + x;
                float edge = Math.min(y, h - 1 - y);
                if (leftEdge) edge = Math.min(edge, x);
                if (rightEdge) edge = Math.min(edge, w - 1 - x);
                if ("circle".equals(shape)) {
                    edge = Math.min(w, h) / 2f - .5f
                            - (float) Math.hypot(x - (w - 1) / 2f, y - (h - 1) / 2f);
                } else if ("band".equals(shape)) {
                    // Feather the two ends only, leaving flat top and bottom
                    // edges: a message that grows sideways out of the round
                    // button reads as one strip instead of a floating blob.
                    // Doubled so the fade is a soft ramp rather than a barely
                    // visible bevel -- callers keep the label clear of it with
                    // horizontal padding, so a wider feather costs no text.
                    edge = Math.min(x, w - 1 - x) * 2f;
                } else if ("rounded".equals(shape)) {
                    float dx = Math.max(leftEdge ? radius - x : 0,
                            rightEdge ? x - (w - 1 - radius) : 0);
                    float dy = Math.max(radius - y, y - (h - 1 - radius));
                    float corner = radius - (float) Math.hypot(Math.max(dx, 0), Math.max(dy, 0));
                    edge = Math.min(edge, corner);
                }
                float feather = (edge - edgeJitter[i]) / (featherUnit * roughness);
                feather = Math.max(0f, Math.min(1f, feather));
                float wave = 8f * (1f - y / (float) Math.max(1, h - 1))
                        + 5f * (float) Math.sin(x / (float) Math.max(1, w - 1) * Math.PI) - 5f;
                int alpha = Math.round(feather * alphaBase + alphaField[i] * alphaJitter * feather);
                alpha = Math.max(0, Math.min(255, alpha));
                int r = channel(palette[0], grainField[i] * grain * (dark ? .35f : 1f) + wave);
                int g = channel(palette[1], grainField[i] * grain * (dark ? .35f : 1f) + wave);
                int b = channel(palette[2], grainField[i] * grain * (dark ? .35f : 1f) + wave);
                pixels[i] = (alpha << 24) | (r << 16) | (g << 8) | b;
            }
        }
        Bitmap bitmap = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888);
        bitmap.setPixels(pixels, 0, w, 0, 0, w, h);
        CACHE.put(key, bitmap);
        return bitmap;
    }

    private static int channel(int base, float delta) {
        return Math.max(0, Math.min(255, Math.round(base + delta)));
    }

    // ---- drawables ---------------------------------------------------------

    /** Frosted panel: diagonal gradient, one pass of grain, a soft glow and worn edges. */
    public static class MistDrawable extends Drawable {
        private final Paint gradientPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint grainPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint glowPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint linePaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint tickPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final float scale;
        private float opacity = 1f;

        public MistDrawable(Context context) {
            this.scale = dp(context);
            linePaint.setStyle(Paint.Style.STROKE);
            linePaint.setStrokeWidth(Math.max(1f, scale));
            linePaint.setColor(0x3ca4bfcf);
            tickPaint.setStrokeWidth(Math.max(1f, scale));
        }

        public void setOpacity(float value) { opacity = value; invalidateSelf(); }

        @Override protected void onBoundsChange(Rect bounds) {
            int w = Math.max(1, bounds.width());
            gradientPaint.setShader(new LinearGradient(bounds.left, bounds.top, bounds.right, bounds.bottom,
                    new int[]{0xf03b5264, 0xf02c4355, 0xf31d3040},
                    new float[]{0f, .55f, 1f}, Shader.TileMode.CLAMP));
            glowPaint.setShader(new RadialGradient(bounds.left + w * .4f, bounds.top + 30 * scale,
                    Math.max(1f, w * .8f), 0x189cb7cc, 0x009cb7cc, Shader.TileMode.CLAMP));
            grainPaint.setShader(new BitmapShader(grainTile(), Shader.TileMode.REPEAT, Shader.TileMode.REPEAT));
        }

        /**
         * One deterministic alpha-9 noise tile, repeated instead of drawn per pixel.
         * Shared across every panel: a settings screen with 70 list rows would
         * otherwise allocate 70 identical tiles.
         */
        private static Bitmap grain;

        private static synchronized Bitmap grainTile() {
            if (grain == null) {
                int size = 128;
                int[] pixels = new int[size * size];
                Random random = new Random(5);
                for (int i = 0; i < pixels.length; i++) {
                    int v = random.nextInt(256);
                    pixels[i] = (9 << 24) | (v << 16) | (v << 8) | v;
                }
                grain = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
                grain.setPixels(pixels, 0, size, 0, 0, size, size);
            }
            return grain;
        }

        @Override public void draw(Canvas canvas) {
            Rect b = getBounds();
            float alpha = Math.max(0f, Math.min(1f, opacity));
            int save = alpha >= .999f ? -1 : canvas.saveLayerAlpha(null, Math.round(255 * alpha));
            canvas.drawRect(b, gradientPaint);
            canvas.drawRect(b, grainPaint);
            canvas.drawRect(b, glowPaint);
            float inset = 18 * scale;
            canvas.drawLine(b.left + inset, b.top + scale, b.right - inset, b.top + scale, linePaint);
            canvas.drawLine(b.left + inset, b.bottom - 2 * scale, b.right - inset, b.bottom - 2 * scale, linePaint);
            // Fine worn vertical edges, deterministic geometry rather than animation.
            Random random = new Random(5);
            int step = Math.max(3, Math.round(6 * scale));
            int length = Math.max(1, Math.round(3 * scale));
            int margin = Math.max(4, Math.round(8 * scale));
            for (int x : new int[]{b.left + Math.round(scale), b.right - Math.round(2 * scale)}) {
                for (int y = b.top + margin; y < b.bottom - margin; y += step) {
                    tickPaint.setColor((random.nextInt(51) + 15) << 24 | 0x9cb7cc);
                    canvas.drawLine(x, y, x, y + length, tickPaint);
                }
            }
            if (save >= 0) canvas.restoreToCount(save);
        }

        @Override public void setAlpha(int alpha) { setOpacity(alpha / 255f); }
        @Override public void setColorFilter(ColorFilter filter) {}
        @Override public int getOpacity() { return PixelFormat.TRANSLUCENT; }
    }

    /** Feathered chalk surface behind a control. */
    public static class ChalkDrawable extends Drawable {
        private final Context context;
        private final Chalk mode;
        private final float roughness;
        private final String shape;
        private final boolean leftEdge, rightEdge;
        private float opacity = 1f;

        public ChalkDrawable(Context context, Chalk mode, float roughness, String shape,
                             boolean leftEdge, boolean rightEdge) {
            this.context = context;
            this.mode = mode;
            this.roughness = roughness;
            this.shape = shape;
            this.leftEdge = leftEdge;
            this.rightEdge = rightEdge;
        }

        public void setOpacity(float value) { opacity = value; invalidateSelf(); }

        @Override public void draw(Canvas canvas) {
            Rect b = getBounds();
            if (b.width() <= 0 || b.height() <= 0) return;
            float alpha = Math.max(0f, Math.min(1f, opacity));
            int save = alpha >= .999f ? -1 : canvas.saveLayerAlpha(null, Math.round(255 * alpha));
            Bitmap bitmap = chalk(context, b.width(), b.height(), mode, roughness, shape, leftEdge, rightEdge);
            canvas.drawBitmap(bitmap, null, b, SCALE);
            if (save >= 0) canvas.restoreToCount(save);
        }

        @Override public void setAlpha(int alpha) { setOpacity(alpha / 255f); }
        @Override public void setColorFilter(ColorFilter filter) {}
        @Override public int getOpacity() { return PixelFormat.TRANSLUCENT; }
    }

    // ---- controls ----------------------------------------------------------

    /** QPushButton stand-in: chalk surface, dark ink label. `primary` matches QPushButton#primary. */
    public static class ChalkButton extends Button {
        private ChalkDrawable surface;

        public ChalkButton(Context context, String label) {
            this(context, label, false);
        }

        public ChalkButton(Context context, String label, boolean primary) {
            super(context);
            surface = new ChalkDrawable(context, primary ? Chalk.WHITE : Chalk.NORMAL, .7f, "rounded", true, true);
            setBackground(null);
            setText(label);
            setAllCaps(false);
            setGravity(Gravity.CENTER);
            setMinHeight(px(context, 46));
            setMinimumHeight(px(context, 46));
            setStateListAnimator(null);
            setPadding(px(context, 12), px(context, 8), px(context, 12), px(context, 8));
            text(this, 15, INK);
        }

        @Override protected void drawableStateChanged() {
            super.drawableStateChanged();
            if (surface != null) surface.setOpacity(!isEnabled() ? .38f : isPressed() ? .75f : .96f);
            invalidate();
        }

        @Override protected void onDraw(Canvas canvas) {
            int inset = px(getContext(), 4);
            surface.setBounds(0, inset, getWidth(), getHeight() - inset);
            surface.draw(canvas);
            super.onDraw(canvas);
        }
    }

    /**
     * Dark frosted group heading — the FoldSection heading. Once
     * {@link #setExpanded} has been called it also draws the fold arrow, so the
     * heading itself becomes the section's only control and no separate
     * disclosure button is needed.
     */
    public static class SectionHeading extends View {
        private final ChalkDrawable surface = new ChalkDrawable(getContext(), Chalk.DEEP, .7f, "rounded", true, true);
        private final String label;
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Path arrow = new Path();
        private final Paint arrowPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private boolean foldable, expanded;

        public SectionHeading(Context context, String label) {
            super(context);
            this.label = label;
            paint.setTypeface(typeface(context));
            paint.setTextSize(px(context, 15));
            paint.setColor(HEADING);
            arrowPaint.setColor(HEADING);
            arrowPaint.setStyle(Paint.Style.FILL);
        }

        /** Mark the heading foldable and record which way it currently points. */
        public void setExpanded(boolean value) {
            foldable = true;
            expanded = value;
            invalidate();
        }

        public boolean isExpanded() { return expanded; }

        @Override protected void onMeasure(int widthSpec, int heightSpec) {
            setMeasuredDimension(resolveSize(0, widthSpec), px(getContext(), 32));
        }

        @Override protected void onDraw(Canvas canvas) {
            surface.setOpacity(.86f);
            surface.setBounds(0, 0, getWidth(), getHeight());
            surface.draw(canvas);
            Paint.FontMetrics metrics = paint.getFontMetrics();
            float baseline = getHeight() / 2f - (metrics.ascent + metrics.descent) / 2f;
            canvas.drawText(label, px(getContext(), 14), baseline, paint);
            if (!foldable) return;
            // Drawn, not typed: the bundled font has no verified triangle glyph,
            // and a missing one renders as a tofu box.
            float size = px(getContext(), 5);
            float cx = getWidth() - px(getContext(), 18), cy = getHeight() / 2f;
            arrow.reset();
            if (expanded) {
                arrow.moveTo(cx - size, cy - size / 2f);
                arrow.lineTo(cx + size, cy - size / 2f);
                arrow.lineTo(cx, cy + size);
            } else {
                arrow.moveTo(cx - size / 2f, cy - size);
                arrow.lineTo(cx + size, cy);
                arrow.lineTo(cx - size / 2f, cy + size);
            }
            arrow.close();
            canvas.drawPath(arrow, arrowPaint);
        }
    }

    /** Segmented chalk switch. One surface, only the selected cell is highlighted. */
    public static class ChalkChoice extends View {
        public interface Listener { void onChanged(int index); }

        private final String[] labels;
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private int index;
        private Listener listener;

        public ChalkChoice(Context context, String[] labels) {
            super(context);
            this.labels = labels;
            setMinimumHeight(px(context, 42));
            setClickable(true);
            paint.setTypeface(typeface(context));
            paint.setTextSize(px(context, 15));
            paint.setTextAlign(Paint.Align.CENTER);
        }

        /**
         * Labels are read at arm's length in-game, where the app's normal size
         * is too small; the in-game panel raises it without changing the home
         * screen, which is read at a normal distance.
         */
        public void setLabelSizeDp(float dp) {
            paint.setTextSize(px(getContext(), dp));
            invalidate();
        }

        public void setListener(Listener value) { listener = value; }

        public int getIndex() { return index; }

        @Override protected void onMeasure(int widthSpec, int heightSpec) {
            setMeasuredDimension(resolveSize(px(getContext(), 220), widthSpec),
                    resolveSize(px(getContext(), 42), heightSpec));
        }

        public void setIndex(int value) {
            if (value < 0 || value >= labels.length || value == index) return;
            index = value;
            invalidate();
            if (listener != null) listener.onChanged(index);
        }

        @Override public boolean onTouchEvent(android.view.MotionEvent event) {
            if (event.getAction() == android.view.MotionEvent.ACTION_DOWN) return true;
            if (event.getAction() == android.view.MotionEvent.ACTION_UP) {
                setIndex(Math.min(labels.length - 1, (int) (event.getX() * labels.length / getWidth())));
                performClick();
                return true;
            }
            return super.onTouchEvent(event);
        }

        @Override public boolean performClick() { return super.performClick(); }

        @Override protected void onDraw(Canvas canvas) {
            int cell = Math.round(getWidth() / (float) labels.length);
            Paint.FontMetrics metrics = paint.getFontMetrics();
            float baseline = getHeight() / 2f - (metrics.ascent + metrics.descent) / 2f;
            for (int i = 0; i < labels.length; i++) {
                int left = Math.round(i * getWidth() / (float) labels.length);
                int width = (i == labels.length - 1 ? getWidth() : cell * (i + 1)) - left;
                if (width <= 0) continue;
                int inset = px(getContext(), 4);
                Bitmap bitmap = chalk(getContext(), width, Math.max(2, getHeight() - inset * 2),
                        i == index ? Chalk.BRIGHT : Chalk.DARK, .7f, "rounded",
                        i == 0, i == labels.length - 1);
                canvas.drawBitmap(bitmap, null, new Rect(left, inset, left + width, getHeight() - inset),
                        SCALE);
                paint.setColor(i == index ? INK : CHOICE_IDLE);
                canvas.drawText(labels[i], left + width / 2f, baseline, paint);
            }
        }
    }

    /**
     * Round chalk button drawing a cross, for dismissing a panel.
     *
     * The cross is painted rather than typed: the bundled font has no verified
     * glyph for any of the multiplication or ballot-x characters, and a missing
     * one renders as a tofu box.
     */
    public static class CloseButton extends View {
        private final ChalkDrawable surface = new ChalkDrawable(getContext(), Chalk.DARK, .7f, "circle", true, true);
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);

        public CloseButton(Context context) {
            super(context);
            setClickable(true);
            setContentDescription("关闭");
            paint.setColor(TEXT);
            paint.setStrokeWidth(Math.max(2f, 1.6f * dp(context)));
            paint.setStrokeCap(Paint.Cap.ROUND);
        }

        @Override protected void drawableStateChanged() {
            super.drawableStateChanged();
            surface.setOpacity(isPressed() ? 1f : .8f);
            invalidate();
        }

        @Override protected void onMeasure(int widthSpec, int heightSpec) {
            int size = px(getContext(), 34);
            setMeasuredDimension(resolveSize(size, widthSpec), resolveSize(size, heightSpec));
        }

        @Override protected void onDraw(Canvas canvas) {
            surface.setBounds(0, 0, getWidth(), getHeight());
            surface.draw(canvas);
            float arm = Math.min(getWidth(), getHeight()) * .19f;
            float cx = getWidth() / 2f, cy = getHeight() / 2f;
            canvas.drawLine(cx - arm, cy - arm, cx + arm, cy + arm, paint);
            canvas.drawLine(cx + arm, cy - arm, cx - arm, cy + arm, paint);
        }
    }

    /** ChalkSlider: dark groove, light fill, circular knob. */
    public static class ChalkSlider extends android.widget.SeekBar {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);

        public ChalkSlider(Context context, int max, int value) {
            super(context);
            setMax(max);
            setProgress(value);
            setMinimumHeight(px(context, 34));
        }

        @Override protected synchronized void onDraw(Canvas canvas) {
            int mid = getHeight() / 2;
            int trackHeight = Math.max(2, Math.round(10 * dp(getContext()) / 2f));
            float usable = getWidth() - px(getContext(), 20);
            float fraction = getMax() == 0 ? 0 : getProgress() / (float) getMax();
            float knobX = px(getContext(), 10) + usable * fraction;
            Rect track = new Rect(px(getContext(), 10), mid - trackHeight / 2,
                    getWidth() - px(getContext(), 10), mid + trackHeight / 2);
            canvas.drawBitmap(chalk(getContext(), track.width(), track.height(), Chalk.DARK, 1f, "rect", true, true),
                    null, track, SCALE);
            Rect filled = new Rect(track.left, track.top, Math.max(track.left + 1, Math.round(knobX)), track.bottom);
            canvas.drawBitmap(chalk(getContext(), filled.width(), filled.height(), Chalk.NORMAL, 1f, "rect", true, true),
                    null, filled, SCALE);
            int knob = Math.round(21 * dp(getContext()));
            Rect circle = new Rect(Math.round(knobX - knob / 2f), mid - knob / 2,
                    Math.round(knobX + knob / 2f), mid + knob / 2);
            canvas.drawBitmap(chalk(getContext(), circle.width(), circle.height(), Chalk.BRIGHT, .5f, "circle", true, true),
                    null, circle, SCALE);
        }
    }

    /**
     * The emblem, turning. Used wherever the app is waiting on something.
     *
     * A spinner rather than a progress bar: the update check spends most of its
     * time on a single opaque transfer, so a percentage would sit still and read
     * as a stall, while the turning emblem is the same object the in-game button
     * uses to say "working" -- one vocabulary for both screens.
     */
    public static class Spinner extends android.widget.ImageView {
        private static final long TURN_MS = 1100;
        private android.animation.ObjectAnimator turn;

        public Spinner(Context context) {
            super(context);
            setImageResource(R.drawable.floating_emblem);
            setScaleType(ScaleType.FIT_CENTER);
            setContentDescription("正在加载");
            setVisibility(GONE);
        }

        @Override protected void onAttachedToWindow() {
            super.onAttachedToWindow();
            if (getVisibility() == VISIBLE) start();
        }

        @Override protected void onDetachedFromWindow() {
            stop();
            super.onDetachedFromWindow();
        }

        public void start() {
            if (turn == null) {
                turn = android.animation.ObjectAnimator.ofFloat(this, "rotation", 0f, 360f);
                turn.setDuration(TURN_MS);
                turn.setRepeatCount(android.animation.ValueAnimator.INFINITE);
                turn.setInterpolator(new android.view.animation.LinearInterpolator());
            }
            if (!turn.isStarted()) turn.start();
        }

        public void stop() {
            if (turn != null) turn.cancel();
            setRotation(0f);
        }
    }

    /** ChalkToggle equivalent: a labelled 开/关 pair on one switch surface. */
    public static class ChalkToggle extends android.widget.LinearLayout {
        public interface Listener { void onToggled(boolean checked); }

        private final ChalkChoice choice;
        private Listener listener;
        private boolean checked;

        public ChalkToggle(Context context, String label, float widthDp) {
            super(context);
            setOrientation(HORIZONTAL);
            setGravity(Gravity.CENTER_VERTICAL);
            TextView caption = new TextView(context);
            caption.setText(label);
            addView(text(caption, 15, TEXT), new android.widget.LinearLayout.LayoutParams(0, -2, 1));
            choice = new ChalkChoice(context, new String[]{"开", "关"});
            android.widget.LinearLayout.LayoutParams params = new android.widget.LinearLayout.LayoutParams(
                    px(context, widthDp), android.view.ViewGroup.LayoutParams.WRAP_CONTENT);
            params.topMargin = px(context, 6);
            addView(choice, params);
            choice.setListener(index -> {
                checked = index == 0;
                if (listener != null) listener.onToggled(checked);
            });
        }

        public void setListener(Listener value) { listener = value; }

        public boolean isChecked() { return checked; }

        public void setChecked(boolean value) {
            checked = value;
            choice.setIndex(value ? 0 : 1);
        }
    }

    // ---- layout helpers ----------------------------------------------------

    /** Compact superscript help with a generous touch target, also accessible by tap. */
    public static android.widget.LinearLayout helpLabel(Context context, String label, String explanation) {
        android.widget.LinearLayout row = new android.widget.LinearLayout(context);
        row.setGravity(Gravity.CENTER_VERTICAL);
        TextView caption = new TextView(context);
        caption.setText(label);
        row.addView(text(caption, 15, TEXT), new android.widget.LinearLayout.LayoutParams(0, -2, 1));
        TextView help = new TextView(context);
        help.setText("?"); help.setTypeface(Typeface.DEFAULT_BOLD);
        help.setTextColor(MUTED); help.setTextSize(12);
        help.setGravity(Gravity.TOP | Gravity.CENTER_HORIZONTAL);
        help.setPadding(0, px(context, 6), 0, 0);
        help.setContentDescription(label + "说明：" + explanation);
        row.addView(help, new android.widget.LinearLayout.LayoutParams(px(context, 44), px(context, 44)));
        Runnable show = () -> {
            TextView detail = muted(context, explanation);
            detail.setPadding(px(context, 16), px(context, 12), px(context, 16), px(context, 12));
            detail.setBackground(new MistDrawable(context));
            android.widget.PopupWindow popup = new android.widget.PopupWindow(detail,
                    Math.min(context.getResources().getDisplayMetrics().widthPixels - px(context, 32), px(context, 280)), -2, true);
            popup.setBackgroundDrawable(new android.graphics.drawable.ColorDrawable(Color.TRANSPARENT));
            popup.setOutsideTouchable(true);
            popup.showAsDropDown(help, -px(context, 220), 0);
        };
        help.setOnLongClickListener(v -> { show.run(); return true; });
        help.setOnClickListener(v -> show.run());
        return row;
    }

    /** Dark frosted panel. */
    public static class MistPanel extends android.widget.LinearLayout {
        private final MistDrawable surface;

        public MistPanel(Context context) {
            super(context);
            surface = new MistDrawable(context);
            setBackground(surface);
            setOrientation(VERTICAL);
        }

        public MistDrawable surface() { return surface; }
    }

    /** Hairline that fades out at both ends, for separating blocks of content. */
    public static class Rule extends View {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);

        public Rule(Context context) {
            super(context);
        }

        @Override protected void onSizeChanged(int width, int height, int oldWidth, int oldHeight) {
            paint.setShader(new LinearGradient(0, 0, Math.max(1, width), 0,
                    new int[]{0x00859daf, 0x66859daf, 0x00859daf},
                    new float[]{0f, .5f, 1f}, Shader.TileMode.CLAMP));
        }

        @Override protected void onMeasure(int widthSpec, int heightSpec) {
            setMeasuredDimension(resolveSize(0, widthSpec), resolveSize(px(getContext(), 1), heightSpec));
        }

        @Override protected void onDraw(Canvas canvas) {
            canvas.drawRect(0, 0, getWidth(), getHeight(), paint);
        }
    }

    public static View space(Context context, float heightDp) {
        View view = new View(context);
        view.setLayoutParams(new ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, px(context, heightDp)));
        return view;
    }

    /** Muted helper text, matching QLabel#muted. */
    public static TextView muted(Context context, String value) {
        TextView view = new TextView(context);
        view.setText(value);
        return text(view, 13, MUTED);
    }

    /** QLabel#status: translucent slab with an accent rule down the left edge. */
    public static class StatusDrawable extends Drawable {
        private final Paint fill = new Paint();
        private final Paint rule = new Paint();
        private final float scale;

        public StatusDrawable(Context context) {
            scale = dp(context);
            fill.setColor(0x6408141f);
            rule.setColor(ACCENT);
        }

        @Override public void draw(Canvas canvas) {
            Rect b = getBounds();
            canvas.drawRect(b, fill);
            canvas.drawRect(b.left, b.top, b.left + Math.max(1, 2 * scale), b.bottom, rule);
        }

        @Override public void setAlpha(int alpha) { fill.setAlpha(alpha); }
        @Override public void setColorFilter(ColorFilter filter) {}
        @Override public int getOpacity() { return PixelFormat.TRANSLUCENT; }
    }

    /** Status line, matching QLabel#status. */
    public static TextView status(Context context) {
        TextView view = new TextView(context);
        view.setBackground(new StatusDrawable(context));
        view.setPadding(px(context, 12), px(context, 10), px(context, 12), px(context, 10));
        return text(view, 14, TEXT);
    }
}
