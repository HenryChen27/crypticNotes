package com.crypticnotes.mobile;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;

/**
 * Downloads an update while the app is in the background.
 *
 * The download used to run in a bare thread owned by the settings screen, and
 * its `finally` deleted the partial file -- so leaving the app threw away
 * everything already transferred. A `dataSync` foreground service survives that:
 * the user taps 检查更新, can go back to the map, and the phone downloads on its
 * own.
 *
 * What this deliberately does not do is promise the install dialog will appear.
 * Starting an activity from the background is dropped *silently* on Android 10+
 * when the app has no visible overlay, so the code cannot tell success from being
 * ignored. Every outcome therefore leaves something the user can tap, and the
 * verified package stays on disk in {@code cacheDir/update.apk} -- which is
 * exactly what {@code UpdateProvider} serves -- so the next launch finishes the
 * job even if this process is never resumed.
 */
public class UpdateService extends Service {
    private static final String CHANNEL_PROGRESS = "update";
    private static final int NOTIFICATION = 2;
    private static final long MAX_APK = 400_000_000L;

    /** Persisted so a resumed transfer needs no Intent, and so the home screen
     *  can tell "downloading" apart from "died mid-transfer". */
    static final String BUSY = "update_busy";
    private static final String KEY_URL = "update_url";
    private static final String KEY_DIGEST = "update_digest";
    private static final String KEY_SIZE = "update_size";
    private static final String KEY_VERSION = "update_version";

    @android.annotation.SuppressLint("StaticFieldLeak")   // a Service, not a context to leak
    static volatile UpdateService current;

    /** Live progress for whoever is on screen. Called from the download thread. */
    interface Listener { void onUpdate(String text, int percent, boolean running); }

    private static Listener listener;
    /** Kept so a screen that arrives mid-download can draw before the next tick. */
    private static String latestText = "";

    private Thread worker;
    private PowerManager.WakeLock lock;
    private volatile boolean cancelled;

    /**
     * Start (or re-attach to) the transfer. Called from the settings screen, so
     * the foreground service is started from a visible Activity -- which is what
     * Android 12+ requires and what Android 15 still allows.
     */
    static void start(Context context, String url, String digest, long size, long version) {
        context.getSharedPreferences("mobile", 0).edit()
                .putString(KEY_URL, url).putString(KEY_DIGEST, digest)
                .putLong(KEY_SIZE, size).putLong(KEY_VERSION, version).apply();
        Intent intent = new Intent(context, UpdateService.class);
        if (Build.VERSION.SDK_INT >= 26) context.startForegroundService(intent);
        else context.startService(intent);
    }

    static void observe(Listener value) { listener = value; }
    static void unobserve() { listener = null; }
    static String statusText() { return latestText; }

    private static void publish(String text, int percent, boolean running) {
        latestText = text;
        Listener target = listener;
        if (target != null) target.onUpdate(text, percent, running);
    }

    @Override public IBinder onBind(Intent intent) { return null; }

    @Override public void onCreate() {
        super.onCreate();
        current = this;
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        manager.createNotificationChannel(new NotificationChannel(
                CHANNEL_PROGRESS, "更新下载", NotificationManager.IMPORTANCE_LOW));
    }

    @Override public int onStartCommand(Intent intent, int flags, int id) {
        startForeground(NOTIFICATION, notification("正在后台下载更新", 0));
        if (worker != null && worker.isAlive()) return START_NOT_STICKY;
        android.content.SharedPreferences prefs = getSharedPreferences("mobile", 0);
        final String url = prefs.getString(KEY_URL, "");
        final String digest = prefs.getString(KEY_DIGEST, "");
        final long size = prefs.getLong(KEY_SIZE, 0), version = prefs.getLong(KEY_VERSION, 0);
        prefs.edit().putBoolean(BUSY, true).apply();
        worker = new Thread(() -> {
            String failure = null;
            try {
                download(url, digest, size, version);
                File apk = AppInstaller.apk(this);
                long installed = AppInstaller.installedVersion(this);
                clearPartial();
                if (version <= installed) {
                    apk.delete();
                    publish("已是最新版本", -1, false);
                    return;
                }
                prefs.edit().putBoolean(AppInstaller.PENDING, true)
                        .putString(AppInstaller.READY_DIGEST, digest)
                        .putLong(AppInstaller.READY_VERSION, version).apply();
                // Ask the system installer first, then leave a notification either
                // way: a dropped background launch raises nothing to catch.
                AppInstaller.install(this);
                AppInstaller.ready(this, "更新已下载，点按完成安装");
                publish("更新已下载，点按通知完成安装", 100, false);
            } catch (Exception e) {
                failure = e.getMessage();
                clearPartial();
                publish("更新失败：" + failure + "。可稍后重试。", -1, false);
            } finally {
                getSharedPreferences("mobile", 0).edit().putBoolean(BUSY, false).apply();
                release();
                // Keep the process alive a moment longer so the package installer
                // can read through UpdateProvider before the service goes away.
                android.os.Handler handler = new android.os.Handler(getMainLooper());
                handler.postDelayed(() -> stopSelfSafely(), failure == null ? 2000 : 200);
            }
        }, "app-update");
        worker.start();
        return START_NOT_STICKY;
    }

    /**
     * Fetch to {@code cacheDir/update.download} and verify before it is allowed
     * to become {@code update.apk}.
     *
     * A half-finished file from a previous run is resumed with a Range request,
     * but only if the server actually answers 206: a 200 means the CDN ignored
     * the header and is about to send the whole thing from byte zero.
     */
    private void download(String url, String digest, long size, long version) throws Exception {
        if (url == null || !url.startsWith("https://")) throw new IOException("更新地址必须为 HTTPS");
        if (size <= 0 || size > MAX_APK) throw new IOException("更新包大小异常");
        if (digest == null || !digest.matches("sha256:[0-9a-fA-F]{64}")) throw new IOException("更新包缺少 SHA-256 校验信息");

        File partial = AppInstaller.partial(this);
        long existing = partial.isFile() ? partial.length() : 0;
        if (existing > size) { partial.delete(); existing = 0; }

        HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
        connection.setConnectTimeout(20000);
        connection.setReadTimeout(30000);
        connection.setRequestProperty("User-Agent", "CrypticNotes-Android");
        if (existing > 0) connection.setRequestProperty("Range", "bytes=" + existing + "-");
        int code = connection.getResponseCode();
        boolean resuming = existing > 0 && code == 206;
        if (code != 200 && !resuming) {
            connection.disconnect();
            throw new IOException("服务器返回 " + code);
        }
        if (existing > 0 && !resuming) existing = 0;

        // Held from before the re-hash: verifying an already-written 150 MB with
        // the screen off is exactly the window this lock exists for.
        acquire();
        MessageDigest sha = MessageDigest.getInstance("SHA-256");
        // A resumed transfer starts mid-stream, so the already-written bytes have
        // to go through the digest again before the new ones are appended.
        if (existing > 0) {
            try (InputStream in = new FileInputStream(partial)) {
                byte[] buffer = new byte[65536]; int read;
                while ((read = in.read(buffer)) != -1) sha.update(buffer, 0, read);
            }
        }
        long received = existing;
        long total = existing + connection.getContentLength();
        try (InputStream in = connection.getInputStream();
             OutputStream out = new FileOutputStream(partial, resuming)) {
            byte[] buffer = new byte[65536]; int read; int last = -1;
            while ((read = in.read(buffer)) != -1) {
                if (cancelled) throw new IOException("已取消");
                received += read;
                if (received > size) throw new IOException("更新包大小不符");
                out.write(buffer, 0, read);
                sha.update(buffer, 0, read);
                int percent = (int) (received * 100 / size);
                if (percent / 2 != last) {
                    last = percent / 2;
                    progress(percent);
                }
            }
        } finally { connection.disconnect(); }
        if (total > 0 && received < total) throw new IOException("下载中断，请重试");
        if (received != size) throw new IOException("更新包大小不符");

        StringBuilder hex = new StringBuilder();
        for (byte b : sha.digest()) hex.append(String.format("%02x", b & 255));
        if (!digest.equalsIgnoreCase("sha256:" + hex)) throw new IOException("下载校验失败，请重试");

        // The bytes are right; the package still has to be ours and still has to
        // be the version that was advertised.
        String reason = AppInstaller.verify(this, partial, version, digest);
        if (reason != null) throw new IOException(reason);
        File apk = AppInstaller.apk(this);
        if (apk.exists() && !apk.delete()) throw new IOException("无法替换旧下载包");
        if (!partial.renameTo(apk)) throw new IOException("无法保存更新包");
    }

    private void acquire() {
        if (lock != null) return;
        PowerManager power = (PowerManager) getSystemService(POWER_SERVICE);
        lock = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "CrypticNotes:update");
        lock.setReferenceCounted(false);
        lock.acquire(20 * 60 * 1000L);
    }

    private void release() {
        if (lock != null && lock.isHeld()) lock.release();
        lock = null;
    }

    private void clearPartial() {
        File partial = AppInstaller.partial(this);
        if (partial.exists()) partial.delete();
    }

    private void progress(int percent) {
        ((NotificationManager) getSystemService(NOTIFICATION_SERVICE))
                .notify(NOTIFICATION, notification("正在后台下载更新 " + percent + "%", percent));
        publish("正在后台下载更新 " + percent + "%，可以离开本页", percent, true);
    }

    private Notification notification(String text, int percent) {
        Notification.Builder builder = new Notification.Builder(this, CHANNEL_PROGRESS)
                .setSmallIcon(android.R.drawable.ic_menu_mapmode)
                .setContentTitle("加页手记地图助手")
                .setContentText(text)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setProgress(100, percent, percent <= 0);
        return builder.build();
    }

    private void stopSelfSafely() {
        try { stopForeground(true); } catch (Exception e) { /* already down */ }
        stopSelf();
    }

    @Override public void onDestroy() {
        cancelled = true;
        current = null;
        release();
        super.onDestroy();
    }
}
