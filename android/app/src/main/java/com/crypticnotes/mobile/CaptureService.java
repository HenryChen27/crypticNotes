package com.crypticnotes.mobile;

import android.app.*;
import android.content.*;
import android.content.res.Configuration;
import android.graphics.*;
import android.hardware.display.*;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.*;
import android.os.*;
import android.util.DisplayMetrics;
import android.view.*;
import android.widget.*;
import com.chaquo.python.*;
import com.chaquo.python.android.AndroidPlatform;
import org.json.JSONObject;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.concurrent.*;

public class CaptureService extends Service {
    /**
     * Milliseconds the overlay stays hidden while a clean frame is grabbed.
     *
     * The projected display includes our own overlay window, so the only way to
     * photograph the game is to take our layer down first. This is the public API
     * documented in android/README.md: a short blink, not a missing overlay.
     */
    private static final int HIDE_MILLIS = 110;
    /**
     * Cadence while a fit is on screen. Affordable only because
     * {@link #sampleViewport} reads the capture buffer in place; the previous
     * grab-a-full-Bitmap path could not run this often.
     */
    private static final int WATCH_MS = 200;
    /** Cadence with nothing on screen. */
    private static final int POLL_IDLE_MS = 500;
    /** Re-poll delay while a negative gate verdict is being double-checked. */
    private static final int CONFIRM_MS = 150;
    /**
     * Provisional thresholds, all counted over the 4824 viewport samples
     * {@link #difference} inspects. Never validated against a real device, so
     * treat them as starting points rather than measurements.
     */
    private static final int GATE_SKIP_LIMIT = 30;
    /** Above this the map has moved enough that the alignment is probably stale. */
    private static final int REALIGN_LIMIT = 60;
    /**
     * Above this the whole viewport changed at once: a scene cut or the map
     * panel closing, not a pan. Hiding immediately is worth it there because
     * there is nothing valid left to show.
     */
    private static final int HIDE_NOW_LIMIT = 2650;
    /** Quiet period after motion, before a re-registration is worth paying for. */
    private static final long SETTLE_MS = 250;
    /**
     * Fallback arm deadline. The through-overlay reference normally arms once
     * two consecutive samples agree, but a scene that never stops animating
     * would then never arm and the overlay would freeze stale forever.
     */
    private static final long ARM_TIMEOUT_MS = 1000;
    private static final long RETRY_MS = 900;
    private long lastGateAt = 0;
    private boolean gateOnly = false;
    private View quickSettings;
    private boolean badgeMessage = false;
    private final Runnable hideBadgeMessage = () -> { badgeMessage = false; layoutBadge(); };
    /** A hung match must not wedge the loop with `busy` stuck true. */
    private static final long BUSY_TIMEOUT_MS = 5000;
    /** Consecutive negative gate verdicts before the fit is discarded outright. */
    private static final int MISS_LIMIT = 2;
    /**
     * The map viewport in 160x90 sample cells: x 0.4125-0.8625, y 0.1222-0.8667.
     * Same rectangle the geometric evidence mask and the stability check use.
     */
    private static final int SAMPLE_X0 = 66, SAMPLE_X1 = 138, SAMPLE_Y0 = 11, SAMPLE_Y1 = 78;
    /** Status strip geometry, as fractions of the screen. */
    private static final float BADGE_X = .195f, BADGE_Y = .01f, BADGE_W = .20f, BADGE_NARROW_W = .09f;
    /**
     * Nothing of ours may sit right of this.
     *
     * The gate needs all three control templates — x .70-1.0, .78-1.0 and
     * .65-1.0 — to match at .78 or better, and the geometric-evidence viewport
     * starts at x .41. A status strip dragged into either region feeds its own
     * text into the gate, so recognition fails outright and never recovers.
     * Anything left of .41 is safe at any height, which is ample room.
     */
    private static final float BADGE_MAX_X = .41f;

    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService compute = Executors.newSingleThreadExecutor();
    private final ExecutorService inspect = Executors.newSingleThreadExecutor();
    private MediaProjection projection; private VirtualDisplay display; private ImageReader reader;
    private WindowManager windows; private ImageView overlay; private LinearLayout badge;
    // `bridge` and `ready` are written on the compute thread and read on the
    // main thread. Volatile keeps that handoff explicit rather than relying on
    // the Handler hop that happens to publish it today.
    private volatile PyObject bridge;
    private volatile boolean destroyed = false, ready = false;
    /** Owned by the main thread: set in runMatch, cleared in its callback. */
    private boolean checking = false;
    private int width, height, density;
    /**
     * Invalidates in-flight async work. Bumped only by events that make an
     * already-computed answer wrong — rotation, lock, portrait, an explicit
     * re-recognition, or the map closing. Deliberately NOT bumped per frame:
     * that is what used to discard a good overlay before it was ever shown.
     */
    private int generation = 0;
    private float opacity = .3f;
    private Bitmap overlayLayer; private boolean overlayAttached = false;
    /**
     * Viewport samples. {@code overlayPixels} is the reference taken *through*
     * our own layer, so it is only ever compared against other through-layer
     * samples; {@code prevPixels} is just the previous sample of any kind.
     * Both are voided whenever the layer's visibility changes, because a
     * comparison across that boundary would be comparing two different images.
     */
    private int[] overlayPixels, prevPixels;
    private boolean prevOverlayUp = false;
    /** When the reference last went void, for the {@link #ARM_TIMEOUT_MS} fallback. */
    private long armSince = 0;
    /** Timestamp of the last sample-to-sample motion, for the settle debounce. */
    private long lastChangeAt = 0;
    /** The clean viewport the in-flight match was computed from. */
    private int[] matchPixels;
    private int[] controlPixels;
    private boolean busy = false;
    private long busySince = 0;
    private int missStreak = 0;
    private long lastMatch = 0;
    private String badgeText = "";
    private int state = S_IDLE;
    private View tapRegion; private RegionCalibrationView calibration;
    private RectF tapBounds;
    private Path touchPath; private long touchStart;
    private WindowManager.LayoutParams badgeParams;
    private TextView badgeLabel; private Theme.Chevron badgeHandle;
    private boolean badgeCollapsed = false;
    private Runnable badgeLongPress; private boolean badgeLongPressed = false;
    private float badgeDownX, badgeDownY; private int badgeStartX, badgeStartY;
    private boolean badgeDragged = false;
    private boolean refreshBundledMaps = false;

    private static final int S_IDLE = 0, S_MATCHING = 1, S_MATCHED = 2, S_FAILED = 3;

    private final Runnable poll = new Runnable() { public void run() { sample(); } };

    @Override public IBinder onBind(Intent i) { return null; }

    @Override public void onCreate() {
        super.onCreate();
        windows = (WindowManager) getSystemService(WINDOW_SERVICE);
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        nm.createNotificationChannel(new NotificationChannel("capture", "地图识别", NotificationManager.IMPORTANCE_LOW));
    }

    @Override public int onStartCommand(Intent intent, int flags, int id) {
        if (intent == null || "stop".equals(intent.getAction())) { stopSelf(); return START_NOT_STICKY; }
        if (projection != null) return START_NOT_STICKY;
        Intent stop = new Intent(this, CaptureService.class).setAction("stop");
        PendingIntent action = PendingIntent.getService(this, 0, stop, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification note = new Notification.Builder(this, "capture").setSmallIcon(android.R.drawable.ic_menu_mapmode)
                .setContentTitle("加页手记正在本机识图").setContentText("点击停止可结束屏幕采集")
                .addAction(new Notification.Action.Builder(null, "停止", action).build()).setOngoing(true).build();
        startForeground(1, note);
        try {
            Intent permission = intent.getParcelableExtra("projection");
            projection = ((MediaProjectionManager) getSystemService(MEDIA_PROJECTION_SERVICE))
                    .getMediaProjection(intent.getIntExtra("result", -1), permission);
            projection.registerCallback(new MediaProjection.Callback() { @Override public void onStop() { stopSelf(); } }, main);
            opacity = intent.getIntExtra("opacity", 30) / 100f;
            setupOverlay(); resizeCapture();
            String difficulty = intent.getStringExtra("difficulty"), mode = intent.getStringExtra("mode");
            getSharedPreferences("mobile", 0).edit().putString("difficulty", difficulty).putString("mode", mode).apply();
            compute.execute(() -> {
                try {
                    int appVersion = getPackageManager().getPackageInfo(getPackageName(), 0).versionCode;
                    refreshBundledMaps = getSharedPreferences("mobile", 0).getInt("map_asset_version", -1) != appVersion;
                    copyAssets("maps", new File(getFilesDir(), "maps"));
                    getSharedPreferences("mobile", 0).edit().putInt("map_asset_version", appVersion).apply();
                    refreshBundledMaps = false;
                    if (!Python.isStarted()) Python.start(new AndroidPlatform(this));
                    bridge = Python.getInstance().getModule("mobile_bridge");
                    bridge.callAttr("initialize", getFilesDir().toString(), difficulty, mode);
                    main.post(() -> { if (!destroyed) { ready = true; setStatus(S_IDLE, "等待地图"); main.post(poll); } });
                } catch (Exception e) {
                    main.post(() -> {
                        if (destroyed) return;
                        setStatus(S_FAILED, "初始化失败");
                        Toast.makeText(this, e.toString(), Toast.LENGTH_LONG).show();
                        stopSelf();
                    });
                }
            });
        } catch (Exception e) {
            Toast.makeText(this, "采集启动失败：" + e.getMessage(), Toast.LENGTH_LONG).show();
            stopSelf();
        }
        return START_NOT_STICKY;
    }

    private WindowManager.LayoutParams params(int w, int h, boolean touch) {
        int flags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN;
        if (!touch) flags |= WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE;
        WindowManager.LayoutParams p = new WindowManager.LayoutParams(w, h,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY, flags, PixelFormat.TRANSLUCENT);
        p.gravity = Gravity.TOP | Gravity.LEFT;
        if (Build.VERSION.SDK_INT >= 28)
            p.layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;
        return p;
    }

    private void setupOverlay() {
        overlay = new ImageView(this);
        overlay.setScaleType(ImageView.ScaleType.FIT_XY);
        overlay.setVisibility(View.INVISIBLE);
        WindowManager.LayoutParams layer = params(-1, -1, false);
        layer.alpha = opacity;
        windows.addView(overlay, layer);

        badge = new LinearLayout(this);
        badge.setOrientation(LinearLayout.HORIZONTAL);
        Theme.ChalkDrawable background = new Theme.ChalkDrawable(this, Theme.Chalk.DEEP, .7f, "rounded", true, true);
        background.setOpacity(.9f);
        badge.setBackground(background);
        int pad = Theme.px(this, 8);
        badge.setPadding(pad, pad, pad, pad);

        badgeLabel = new TextView(this);
        badgeLabel.setTextColor(Theme.TEXT);
        badgeLabel.setTextSize(android.util.TypedValue.COMPLEX_UNIT_DIP, 12);
        badgeLabel.setTypeface(Theme.typeface(this));
        badgeLabel.setMaxLines(3);
        badgeLabel.setEllipsize(android.text.TextUtils.TruncateAt.END);
        badge.addView(badgeLabel, new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

        badgeHandle = new Theme.Chevron(this);
        badgeHandle.setContentDescription("折叠或展开状态条");
        badgeHandle.setOnClickListener(v -> setBadgeCollapsed(!badgeCollapsed));
        badge.addView(badgeHandle, new LinearLayout.LayoutParams(Theme.px(this, 20),
                LinearLayout.LayoutParams.MATCH_PARENT));

        badgeParams = params(-2, -2, true);
        windows.addView(badge, badgeParams);
        badge.setOnTouchListener(this::onBadgeTouch);
        layoutBadge();
    }

    /**
     * Drag the strip by its body, tap to re-identify, hold to recalibrate.
     *
     * A touch listener swallows the click listeners, so the tap and the hold
     * are both resolved here rather than via setOnClickListener.
     */
    private boolean onBadgeTouch(View view, MotionEvent event) {
        float dx = event.getRawX() - badgeDownX, dy = event.getRawY() - badgeDownY;
        switch (event.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                badgeDownX = event.getRawX();
                badgeDownY = event.getRawY();
                badgeStartX = badgeParams.x;
                badgeStartY = badgeParams.y;
                badgeDragged = false;
                badgeLongPressed = false;
                badgeLongPress = () -> { badgeLongPressed = true; showQuickSettings(); };
                main.postDelayed(badgeLongPress, ViewConfiguration.getLongPressTimeout());
                return true;
            case MotionEvent.ACTION_MOVE:
                if (!badgeDragged
                        && Math.hypot(dx, dy) < ViewConfiguration.get(this).getScaledTouchSlop()) {
                    return true;
                }
                badgeDragged = true;
                main.removeCallbacks(badgeLongPress);
                moveBadge(badgeStartX + Math.round(dx), badgeStartY + Math.round(dy));
                return true;
            case MotionEvent.ACTION_UP:
                main.removeCallbacks(badgeLongPress);
                if (badgeDragged) {
                    saveBadgePosition();
                    if (badgeCollapsed) setBadgeCollapsed(true);
                }
                else if (!badgeLongPressed) {
                    setBadgeCollapsed(!badgeCollapsed);
                }
                badgeDragged = false;
                badgeLongPressed = false;
                return true;
            case MotionEvent.ACTION_CANCEL:
                main.removeCallbacks(badgeLongPress);
                if (badgeDragged) saveBadgePosition();
                badgeDragged = false;
                badgeLongPressed = false;
                return true;
            default:
                return true;
        }
    }

    /** Move the strip, honouring {@link #BADGE_MAX_X}; does not persist. */
    private void moveBadge(int x, int y) {
        if (badge == null || width <= 0) return;
        int limit = width - badgeParams.width;
        badgeParams.x = Math.max(0, Math.min(x, Math.max(0, limit)));
        // Measure the strip itself: the window is WRAP_CONTENT high, so
        // badgeParams.height is -2 and would leave y effectively unclamped.
        badgeParams.y = Math.max(0, Math.min(y, Math.max(0, height - badge.getHeight())));
        try { windows.updateViewLayout(badge, badgeParams); } catch (Exception ignored) {}
    }

    private void saveBadgePosition() {
        if (badge == null || width <= 0) return;
        getSharedPreferences("mobile", 0).edit()
                .putFloat("badge_x", badgeParams.x / (float) width)
                .putFloat("badge_y", badgeParams.y / (float) height).apply();
    }

    private void setBadgeCollapsed(boolean value) {
        main.removeCallbacks(hideBadgeMessage);
        badgeMessage = false;
        boolean right = badgeParams.x + badgeParams.width / 2 > width / 2;
        saveBadgePosition();
        getSharedPreferences("mobile", 0).edit().putBoolean("badge_right", right).apply();
        badgeCollapsed = value;
        badgeLabel.setMaxLines(value ? 1 : 3);
        badgeHandle.setPointingLeft(!value);
        getSharedPreferences("mobile", 0).edit().putBoolean("badge_collapsed", value).apply();
        layoutBadge();
    }

    /**
     * Put the strip back where the player left it.
     *
     * Every region the app inspects sits on the right (the gate's three
     * controls) or in the middle (the 0.41-0.86 x 0.12-0.87 viewport used for
     * stability and for geometric evidence), so the strip is confined to the
     * left of {@link #BADGE_MAX_X}. Hiding it on every frame was what made it
     * strobe; keeping it out of those regions means it never has to move.
     */
    private void layoutBadge() {
        if (badge == null || width <= 0) return;
        SharedPreferences prefs = getSharedPreferences("mobile", 0);
        badgeCollapsed = prefs.getBoolean("badge_collapsed", false);
        badgeLabel.setMaxLines(badgeCollapsed ? 1 : 3);
        badgeHandle.setPointingLeft(!badgeCollapsed);
        badgeLabel.setVisibility(badgeCollapsed && !badgeMessage ? View.GONE : View.VISIBLE);
        badgeParams.width = badgeCollapsed && !badgeMessage ? Theme.px(this, 36) : Math.round(width * BADGE_W);
        int limit = width - badgeParams.width;
        badgeParams.x = Math.max(0, Math.min(Math.round(prefs.getFloat("badge_x", BADGE_X) * width),
                Math.max(0, limit)));
        badgeParams.y = Math.max(0, Math.min(height - Theme.px(this, 60), Math.round(prefs.getFloat("badge_y", BADGE_Y) * height)));
        if (badgeCollapsed) badgeParams.x = prefs.getBoolean("badge_right", false) ? width - badgeParams.width : 0;
        try { windows.updateViewLayout(badge, badgeParams); } catch (Exception ignored) {}
    }

    private void resizeCapture() {
        clearOverlay();
        DisplayMetrics metrics = new DisplayMetrics();
        windows.getDefaultDisplay().getRealMetrics(metrics);
        width = metrics.widthPixels; height = metrics.heightPixels; density = metrics.densityDpi;
        ImageReader previous = reader;
        reader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2);
        if (display == null)
            display = projection.createVirtualDisplay("CrypticNotes", width, height, density,
                    DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR, reader.getSurface(), null, main);
        else { display.resize(width, height, density); display.setSurface(reader.getSurface()); }
        if (previous != null) previous.close();
        layoutBadge();
        refreshTapRegion();
    }

    // ---- overlay lifetime --------------------------------------------------

    private void showOverlay(boolean visible) {
        if (overlay == null) return;
        if (visible && overlayLayer != null) {
            if (!overlayAttached) { overlay.setImageBitmap(overlayLayer); overlayAttached = true; }
            if (overlay.getVisibility() != View.VISIBLE) {
                overlay.setVisibility(View.VISIBLE);
                invalidateSamples();
            }
        } else if (!visible && overlay.getVisibility() != View.INVISIBLE) {
            overlay.setVisibility(View.INVISIBLE);
            invalidateSamples();
        }
    }

    private void replaceLayer(Bitmap layer) {
        // The previous bitmap is released by dropping the reference; recycling it
        // here could pull it out from under a draw already queued on the render thread.
        overlayLayer = layer;
        overlayAttached = false;
        invalidateSamples();
        showOverlay(true);
    }

    /**
     * Void the viewport references.
     *
     * Both are only meaningful against frames from the same visibility state,
     * so anything that changes what the capture buffer contains — showing or
     * hiding the layer, swapping in a new bitmap — has to call this. Skipping
     * it makes the next comparison read as a huge change and re-registers for
     * nothing, over and over.
     */
    private void invalidateSamples() {
        overlayPixels = null;
        prevPixels = null;
        armSince = SystemClock.elapsedRealtime();
    }

    /**
     * The 160x90 sample grid {@link #difference} compares over, read straight
     * out of the capture buffer.
     *
     * Going through {@link #grab} would allocate a full-screen Bitmap plus a
     * scaled copy on every poll; at {@link #WATCH_MS} that is tens of MB/s of
     * garbage on the main thread, next to a running game. This touches only the
     * viewport cells. Falls back to the Bitmap path if the plane is not the
     * 4-byte RGBA this arithmetic assumes.
     *
     * The fallback is not interchangeable with the fast path: this one point
     * samples, {@link #signature} bilinearly averages, so the same frame scores
     * differently under each. Only one of them ever runs on a given device --
     * pixel stride is fixed by the display -- which is what keeps every
     * threshold in {@link #difference} meaningful. Do not mix them.
     */
    private int[] sampleViewport() {
        try (Image image = reader.acquireLatestImage()) {
            if (image == null) return null;
            Image.Plane plane = image.getPlanes()[0];
            if (plane.getPixelStride() != 4) {
                Bitmap fallback = grab();
                if (fallback == null) return null;
                int[] pixels = signature(fallback);
                fallback.recycle();
                return pixels;
            }
            ByteBuffer buffer = plane.getBuffer().order(ByteOrder.nativeOrder());
            int rowStride = plane.getRowStride(), capacity = buffer.capacity();
            // Grid from the image's own size, not the window metrics: a frame
            // still in the queue when resizeCapture() swaps the reader would
            // otherwise be sampled at the wrong offsets, silently.
            int w = image.getWidth(), h = image.getHeight();
            if (w <= 0 || h <= 0) return null;
            int[] pixels = new int[160 * 90];
            for (int y = 0; y < 90; y++) {
                int row = (y * h / 90) * rowStride;
                for (int x = 0; x < 160; x++) {
                    int offset = row + (x * w / 160) * 4;
                    if (offset < 0 || offset + 4 > capacity) continue;
                    // RGBA_8888 in memory reads little-endian as 0xAABBGGRR.
                    // Flip to ARGB so Color.red/green/blue stay truthful.
                    int v = buffer.getInt(offset);
                    pixels[y * 160 + x] = (v & 0xff00ff00) | ((v & 0xff) << 16) | ((v >> 16) & 0xff);
                }
            }
            return pixels;
        } catch (Exception e) {
            return null;
        }
    }

    /** Bilinear 160x90 reduction, used only when the plane layout is unexpected. */
    private static int[] signature(Bitmap bitmap) {
        int[] pixels = new int[160 * 90];
        for (int y = 0; y < 90; y++)
            for (int x = 0; x < 160; x++)
                pixels[y * 160 + x] = bitmap.getPixel(x * bitmap.getWidth() / 160, y * bitmap.getHeight() / 90);
        return pixels;
    }

    private void clearOverlay() {
        generation++;
        overlayLayer = null;
        overlayAttached = false;
        matchPixels = null;
        controlPixels = null;
        missStreak = 0;
        invalidateSamples();
        if (overlay != null) {
            overlay.setImageDrawable(null);
            overlay.setVisibility(View.INVISIBLE);
        }
    }

    /** The single place the loop is re-armed. Every path out of a step lands here. */
    private void repoll(int delayMs) {
        if (destroyed) return;
        main.removeCallbacks(poll);
        main.postDelayed(poll, delayMs);
    }

    private void setStatus(int newState, String text) {
        state = newState;
        if (text == null || text.equals(badgeText)) return;
        badgeText = text;
        badgeLabel.setText(text);
        if (badgeCollapsed) {
            badgeMessage = true; layoutBadge();
            main.removeCallbacks(hideBadgeMessage);
            main.postDelayed(hideBadgeMessage, 1800);
        }
    }

    // ---- capture loop ------------------------------------------------------

    /**
     * One step of the loop. Every exit re-arms {@link #poll}.
     *
     * There are two regimes and they are not symmetric. With a fit on screen we
     * can only photograph *through* our own layer, so the reference is another
     * through-layer sample and a change means "re-register". With no fit on
     * screen the frames are clean and a change just means "still moving".
     */
    private void sample() {
        if (destroyed || !ready) return;
        if (calibration != null || quickSettings != null) { repoll(500); return; }
        if (checking) { repoll(100); return; }
        if (SystemClock.elapsedRealtime() - lastGateAt >= 800) {
            // Map controls lie outside the map layer: inspect them without
            // removing either window. Never feed this composited frame to matching.
            gateOnly = true;
            capture(); return;
        }
        // A match that never returned would otherwise hold `busy` forever and
        // freeze the overlay with nothing on screen to explain it.
        if (busy && SystemClock.elapsedRealtime() - busySince > BUSY_TIMEOUT_MS) {
            clearOverlay();
            busySince = SystemClock.elapsedRealtime();
            setStatus(S_FAILED, "识别超时，请重试");
        }

        int[] pixels = sampleViewport();
        if (pixels == null) { repoll(POLL_IDLE_MS); return; }
        // Map controls are outside the rendered map. Watch them even when the
        // central scene barely changes, including while registration is busy.
        if (controlPixels != null && controlsChanged(controlPixels, pixels)) {
            clearOverlay(); lastMatch = 0; gateOnly = false;
            blink(); return;
        }

        // "Up" has to mean composited into the frame, not just "we hold a
        // bitmap". After blink() the bitmap survives while the layer is off
        // screen, and treating those frames as through-layer samples would
        // compare a clean frame against a layer reference.
        boolean overlayUp = overlayLayer != null && overlay.getVisibility() == View.VISIBLE;
        long now = SystemClock.elapsedRealtime();
        // Only motion *within* one regime counts. The transition itself changes
        // the whole frame, and reading that as motion would restart the settle
        // debounce on every blink.
        boolean comparable = prevPixels != null && prevOverlayUp == overlayUp;
        boolean moving = comparable && difference(prevPixels, pixels) >= GATE_SKIP_LIMIT;
        if (moving) lastChangeAt = now;
        boolean settled = now - lastChangeAt >= SETTLE_MS;

        prevPixels = pixels;
        prevOverlayUp = overlayUp;

        if (!overlayUp) {
            // Nothing on screen. Wait for the picture to hold still before
            // spending a gate call plus a match on it.
            if (!settled || busy || throttled()) { repoll(WATCH_MS); return; }
            blink();
            return;
        }

        if (overlayPixels == null) {
            // Reference not armed yet. Two consecutive agreeing through-layer
            // samples are what makes it trustworthy; `armSince` is the escape
            // hatch for a scene that never holds still. `comparable` is part of
            // the test because the first sample in a regime has nothing to
            // agree with, and arming off it is how a pre-composite frame — one
            // taken before the new layer was actually drawn — becomes the
            // reference, after which every later comparison reads as motion.
            if ((comparable && !moving) || now - armSince >= ARM_TIMEOUT_MS) overlayPixels = pixels;
            repoll(WATCH_MS);
            return;
        }

        int drift = difference(overlayPixels, pixels);
        if (drift < REALIGN_LIMIT) { repoll(WATCH_MS); return; }

        // A stale fit must never remain visible during panning or floor changes.
        clearOverlay();
        lastMatch = 0;
        gateOnly = false;
        lastChangeAt = now;
        repoll(WATCH_MS);
    }

    /**
     * Take our own layer down so the next grab is a clean frame.
     *
     * The projected display includes our overlay window, so the only way to
     * photograph the game is to take the layer down first. This is the blink
     * android/README.md documents; the watch path above exists to make it rare.
     * The drain frees one of the two reader slots so SurfaceFlinger can enqueue
     * a post-hide composition into it.
     */
    private void blink() {
        invalidateSamples();
        showOverlay(false);
        try (Image stale = reader.acquireLatestImage()) {} catch (Exception ignored) {}
        main.postDelayed(this::capture, HIDE_MILLIS);
    }

    private void capture() {
        if (destroyed) return;
        if (calibration != null || quickSettings != null) { repoll(500); return; }
        if (((KeyguardManager) getSystemService(KEYGUARD_SERVICE)).isKeyguardLocked()) {
            clearOverlay();
            setStatus(S_IDLE, "屏幕已锁定");
            repoll(1000);
            return;
        }
        if (width <= height) {
            clearOverlay();
            setStatus(S_IDLE, "请横屏打开游戏");
            repoll(800);
            return;
        }
        // blink() guaranteed the layer is down, so this grab is a clean frame.
        // Nothing here may put it back up before the grab happens.
        Bitmap bitmap = grab();
        if (bitmap == null) { badge.setVisibility(View.VISIBLE); repoll(200); return; }

        final int[] framePixels = signature(bitmap);
        // Remove the permanent badge from evidence in the captured copy only.
        final float[] excluded = {Math.max(0, badgeParams.x - 6) / (float) width,
                Math.max(0, badgeParams.y - 6) / (float) height,
                Math.min(width, badgeParams.x + badgeParams.width + 6) / (float) width,
                Math.min(height, badgeParams.y + badge.getHeight() + 6) / (float) height};
        Canvas clean = new Canvas(bitmap);
        Paint erase = new Paint(); erase.setColor(Color.BLACK);
        clean.drawRect(excluded[0]*width, excluded[1]*height, excluded[2]*width, excluded[3]*height, erase);
        final boolean verifyOnly = gateOnly;
        gateOnly = false;
        lastGateAt = SystemClock.elapsedRealtime();
        final int token = generation;
        checking = true;
        try {
            inspect.execute(() -> {
                byte[] frame = encode(bitmap);      // takes ownership, off the main thread
                boolean ok = false, visible = false;
                if (frame != null) {
                    try {
                        visible = new JSONObject(
                                bridge.callAttr("inspect", frame, excluded).toString()).getBoolean("visible");
                        ok = true;
                    } catch (Exception ignored) {
                    }
                }
                final byte[] bytes = frame;
                final boolean passed = visible, ran = ok;
                main.post(() -> {
                    checking = false;
                    if (!destroyed && calibration == null && quickSettings == null) badge.setVisibility(View.VISIBLE);
                    if (destroyed || token != generation) { repoll(POLL_IDLE_MS); return; }
                    if (!ran) {
                        clearOverlay();
                        setStatus(S_FAILED, "画面检测失败");
                        repoll(1000);
                        return;
                    }
                    if (!passed) {
                        clearOverlay();
                        lastMatch = 0;
                        setStatus(S_IDLE, "等待地图");
                        repoll(WATCH_MS);
                        return;
                    }
                    missStreak = 0;
                    controlPixels = framePixels;
                    if (verifyOnly) {
                        // Watch samples handle motion. A heartbeat only checks
                        // visibility and must not realign against our own overlay.
                        repoll(WATCH_MS);
                        return;
                    }
                    if (overlayLayer != null) { clearOverlay(); lastMatch = 0; }
                    if (busy || throttled()) { repoll(WATCH_MS); return; }
                    if (state != S_FAILED) setStatus(S_MATCHING, "正在识别…");
                    runMatch(bytes, framePixels);
                    repoll(WATCH_MS);
                });
            });
        } catch (Exception e) {
            checking = false;
            badge.setVisibility(View.VISIBLE);
            bitmap.recycle();
            repoll(1000);
        }
    }

    /**
     * Downscale, PNG-encode, release. Runs on a worker thread: a full-screen
     * PNG encode on the main thread is a long stall right where the next hide
     * window needs the main thread responsive.
     */
    private static byte[] encode(Bitmap bitmap) {
        try {
            Bitmap source = bitmap;
            if (bitmap.getWidth() > 1440) {
                source = Bitmap.createScaledBitmap(bitmap, 1440,
                        Math.round(bitmap.getHeight() * 1440f / bitmap.getWidth()), true);
            }
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            byte[] bytes = source.compress(Bitmap.CompressFormat.PNG, 100, output)
                    ? output.toByteArray() : null;
            if (source != bitmap) source.recycle();
            return bytes;
        } catch (Exception e) {
            return null;
        } finally {
            bitmap.recycle();
        }
    }

    /** lastMatch == 0 means "never matched"; comparing against uptime would stall a fresh boot. */
    private boolean throttled() {
        return lastMatch != 0 && SystemClock.elapsedRealtime() - lastMatch < RETRY_MS;
    }

    /**
     * @param framePixels the clean viewport {@code frame} was taken from, so a
     *                    result that arrives after the player has moved on can
     *                    be dropped instead of flashed at the wrong position.
     */
    private void runMatch(byte[] frame, int[] framePixels) {
        busy = true;
        busySince = SystemClock.elapsedRealtime();
        lastMatch = busySince;
        matchPixels = framePixels;
        final int token = generation;
        compute.execute(() -> {
            Bitmap layer = null;
            String label = "识别失败，请重试";
            try {
                File file = new File(getCacheDir(), "overlay.png");
                // gated=True: capture() already confirmed the panel is open on
                // this exact frame, so the adapter need not re-run the gate.
                JSONObject result = new JSONObject(
                        bridge.callAttr("match", frame, file.toString(), true).toString());
                boolean ok = result.getBoolean("ok");
                if (ok) layer = BitmapFactory.decodeFile(file.toString());
                String message = result.optString("message");
                label = ok ? describe(result, message) : message;
            } catch (Exception ignored) {
            }
            final Bitmap decoded = layer;
            final String text = label;
            main.post(() -> {
                busy = false;
                if (destroyed || token != generation) {
                    if (decoded != null) decoded.recycle();
                    repoll(WATCH_MS);
                    return;
                }
                if (decoded == null) {
                    if (overlayLayer == null) setStatus(S_FAILED, text);
                    repoll(WATCH_MS);
                    return;
                }
                // Python took the better part of a second. If the viewport has
                // moved on since, this fit is aligned to a frame the player
                // already left; showing it would be a misaligned flash.
                int[] now = sampleViewport();
                if (matchPixels == null || now == null
                        || difference(matchPixels, now) >= REALIGN_LIMIT) {
                    decoded.recycle();
                    lastMatch = 0;
                    invalidateSamples();
                    repoll(WATCH_MS);
                    return;
                }
                replaceLayer(decoded);
                setStatus(S_MATCHED, text);
                repoll(WATCH_MS);
            });
        });
    }

    /** "识别成功：南-三缺一门" over "1F · 试用叠图 · 请核对路口". */
    private static String describe(JSONObject result, String message) {
        String name = result.optString("name");
        if (name.isEmpty()) name = result.optString("map_id");
        StringBuilder label = new StringBuilder("识别成功：").append(name);
        StringBuilder detail = new StringBuilder();
        if (result.has("floor") && !result.isNull("floor")) {
            int floor = result.optInt("floor");
            detail.append(floor == 1 ? "1F" : floor == 2 ? "2F" : floor == -1 ? "地下室" : floor + "F");
        }
        // The matcher only ever offers a provisional fit; keep saying so.
        if (!message.isEmpty()) {
            if (detail.length() > 0) detail.append(" · ");
            detail.append(message);
        }
        if (detail.length() > 0) label.append('\n').append(detail);
        return label.toString();
    }

    private Bitmap grab() {
        try (Image image = reader.acquireLatestImage()) {
            if (image == null) return null;
            Image.Plane plane = image.getPlanes()[0];
            ByteBuffer bytes = plane.getBuffer();
            int paddedWidth = plane.getRowStride() / plane.getPixelStride();
            Bitmap padded = Bitmap.createBitmap(paddedWidth, height, Bitmap.Config.ARGB_8888);
            padded.copyPixelsFromBuffer(bytes);
            Bitmap full = Bitmap.createBitmap(padded, 0, 0, width, height);
            if (full != padded) padded.recycle();
            return full;
        } catch (Exception e) {
            return null;
        }
    }

    /** Differing samples inside the map viewport; see {@link #SAMPLE_X0}. */
    private int compareRegion(int[] a, int[] b, int x0, int y0, int x1, int y1, int threshold) {
        int left=-1, top=-1, right=-1, bottom=-1;
        if (badgeParams != null && badge != null && width>0 && height>0) {
            left=(badgeParams.x-4)*160/width; right=(badgeParams.x+badgeParams.width+4)*160/width;
            top=(badgeParams.y-4)*90/height; bottom=(badgeParams.y+badge.getHeight()+4)*90/height;
        }
        return FrameEvidence.changes(a,b,x0,y0,x1,y1,threshold,left,top,right,bottom);
    }

    private int difference(int[] a, int[] b) {
        return compareRegion(a,b,SAMPLE_X0,SAMPLE_Y0,SAMPLE_X1,SAMPLE_Y1,60);
    }

    private boolean controlsChanged(int[] a, int[] b) {
        return compareRegion(a,b,140,2,155,88,75)>=24;
    }

    // ---- tap relay ---------------------------------------------------------

    private RectF readBounds() {
        SharedPreferences prefs = getSharedPreferences("mobile", 0);
        return new RectF(prefs.getFloat("tap_left", .04f), prefs.getFloat("tap_top", .065f),
                prefs.getFloat("tap_right", .19f), prefs.getFloat("tap_bottom", .265f));
    }

    private void refreshTapRegion() {
        if (tapRegion != null) { windows.removeView(tapRegion); tapRegion = null; }
        if (destroyed || width <= height || calibration != null
                || !getSharedPreferences("mobile", 0).getBoolean("tap_mode", false)
                || TapRelayService.current == null) return;
        tapBounds = readBounds();
        tapRegion = new View(this);
        WindowManager.LayoutParams p = params(Math.round(width * tapBounds.width()),
                Math.round(height * tapBounds.height()), true);
        p.x = Math.round(width * tapBounds.left); p.y = Math.round(height * tapBounds.top);
        tapRegion.setOnTouchListener((v, e) -> {
            if (e.getAction() == MotionEvent.ACTION_DOWN) {
                touchStart = SystemClock.uptimeMillis();
                touchPath = new Path();
                touchPath.moveTo(e.getRawX(), e.getRawY());
            } else if (e.getAction() == MotionEvent.ACTION_MOVE && touchPath != null) {
                touchPath.lineTo(e.getRawX(), e.getRawY());
            } else if (e.getAction() == MotionEvent.ACTION_UP && touchPath != null) {
                Path path = new Path(touchPath);
                touchPath = null;
                long duration = SystemClock.uptimeMillis() - touchStart;
                v.setVisibility(View.GONE);
                clearOverlay();
                lastMatch = 0;
                main.postDelayed(() -> {
                    TapRelayService relay = TapRelayService.current;
                    if (relay != null) relay.relay(path, duration, () -> main.postDelayed(() -> {
                        if (!destroyed) refreshTapRegion();
                    }, 150));
                    else refreshTapRegion();
                }, 70);
            } else if (e.getAction() == MotionEvent.ACTION_CANCEL) touchPath = null;
            return true;
        });
        windows.addView(tapRegion, p);
    }

    private void showQuickSettings() {
        if (quickSettings != null || calibration != null || !ready) return;
        clearOverlay();
        badge.setVisibility(View.INVISIBLE);
        if (tapRegion != null) { windows.removeView(tapRegion); tapRegion = null; }
        SharedPreferences prefs = getSharedPreferences("mobile", 0);
        Theme.MistPanel panel = new Theme.MistPanel(this);
        int pad = Theme.px(this, 16); panel.setPadding(pad, pad, pad, pad);
        panel.addView(Theme.muted(this, "游戏设置 · 长按状态条打开"));
        Theme.ChalkChoice difficulty = new Theme.ChalkChoice(this, new String[]{"困难", "噩梦"});
        difficulty.setIndex(prefs.getString("difficulty", "hard").equals("nightmare") ? 1 : 0);
        panel.addView(difficulty);
        Theme.ChalkChoice party = new Theme.ChalkChoice(this, new String[]{"单人路线", "多人路线"});
        party.setIndex(prefs.getString("mode", "solo").equals("duo") ? 1 : 0);
        panel.addView(party);
        party.setVisibility(difficulty.getIndex() == 1 ? View.VISIBLE : View.GONE);
        difficulty.setListener(i -> party.setVisibility(i == 1 ? View.VISIBLE : View.GONE));
        Theme.ChalkButton save = new Theme.ChalkButton(this, "应用设置 / 重新识别", true);
        panel.addView(save);
        save.setOnClickListener(v -> {
            String d = difficulty.getIndex() == 0 ? "hard" : "nightmare";
            String m = party.getIndex() == 0 ? "solo" : "duo";
            prefs.edit().putString("difficulty", d).putString("mode", m).apply();
            closeQuickSettings(); clearOverlay(); ready = false;
            compute.execute(() -> {
                try {
                    bridge.callAttr("initialize", getFilesDir().toString(), d, m);
                    main.post(() -> { if (!destroyed) { ready = true; lastMatch = 0; setStatus(S_IDLE, "设置已应用"); repoll(100); } });
                } catch (Exception e) { main.post(() -> { if (!destroyed) { setStatus(S_FAILED, "设置失败，请重新启动识图"); } }); }
            });
        });
        Theme.ChalkButton region = new Theme.ChalkButton(this, "校准地图入口"); panel.addView(region);
        region.setOnClickListener(v -> { closeQuickSettings(); showCalibration(); });
        Theme.ChalkButton close = new Theme.ChalkButton(this, "返回游戏"); panel.addView(close);
        close.setOnClickListener(v -> closeQuickSettings());
        quickSettings = panel;
        WindowManager.LayoutParams p = params(Math.min(width - pad * 2, Theme.px(this, 320)), -2, true);
        p.x = (width - p.width) / 2; p.y = Theme.px(this, 20);
        windows.addView(panel, p);
    }

    private void closeQuickSettings() {
        if (quickSettings != null) { windows.removeView(quickSettings); quickSettings = null; }
        badge.setVisibility(View.VISIBLE); refreshTapRegion(); repoll(200);
    }

    private void showCalibration() {
        if (width <= height) { Toast.makeText(this, "请先横屏打开游戏", Toast.LENGTH_SHORT).show(); return; }
        if (calibration != null) return;
        clearOverlay();
        badge.setVisibility(View.INVISIBLE);
        if (tapRegion != null) { windows.removeView(tapRegion); tapRegion = null; }
        calibration = new RegionCalibrationView(this, readBounds(), new RegionCalibrationView.Listener() {
            public void saved(RectF r) {
                getSharedPreferences("mobile", 0).edit()
                        .putFloat("tap_left", r.left).putFloat("tap_top", r.top)
                        .putFloat("tap_right", r.right).putFloat("tap_bottom", r.bottom).apply();
                finishCalibration();
            }
            public void cancel() { finishCalibration(); }
        });
        windows.addView(calibration, params(-1, -1, true));
    }

    private void finishCalibration() {
        if (calibration != null) { windows.removeView(calibration); calibration = null; }
        badge.setVisibility(View.VISIBLE);
        clearOverlay();
        setStatus(S_IDLE, "入口范围已设置");
        refreshTapRegion();
    }

    @Override public void onConfigurationChanged(Configuration c) { super.onConfigurationChanged(c); if (projection != null) resizeCapture(); }

    private void copyAssets(String name, File target) throws IOException {
        String[] children = getAssets().list(name);
        if (children != null && children.length > 0) {
            target.mkdirs();
            for (String child : children) copyAssets(name + "/" + child, new File(target, child));
        } else if (refreshBundledMaps || !target.isFile()) {
            target.getParentFile().mkdirs();
            File temp = new File(target + ".tmp");
            try (InputStream in = getAssets().open(name); OutputStream out = new FileOutputStream(temp)) {
                byte[] b = new byte[65536];
                int n;
                while ((n = in.read(b)) != -1) out.write(b, 0, n);
            }
            if (!temp.renameTo(target)) throw new IOException("Cannot install map library");
        }
    }

    @Override public void onDestroy() {
        destroyed = true;
        generation++;
        main.removeCallbacksAndMessages(null);
        if (display != null) display.release();
        if (reader != null) reader.close();
        if (projection != null) projection.stop();
        if (overlay != null) windows.removeView(overlay);
        if (badge != null) windows.removeView(badge);
        if (tapRegion != null) windows.removeView(tapRegion);
        if (calibration != null) windows.removeView(calibration);
        if (quickSettings != null) windows.removeView(quickSettings);
        compute.shutdownNow();
        inspect.shutdownNow();
        super.onDestroy();
    }
}
