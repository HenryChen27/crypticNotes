package com.crypticnotes.mobile;

import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.provider.Settings;

import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.security.MessageDigest;
import java.util.Arrays;

/**
 * The one place an update is checked over and handed to the system installer.
 *
 * It used to live inside {@link AppUpdater}, which only ever ran with a visible
 * Activity. Now the download finishes in a service, so the same three steps --
 * verify, ask for the install permission, start the installer -- have to work
 * from either context without drifting apart. Everything that needs a visible
 * Activity stays with the caller; everything here is context-free.
 */
final class AppInstaller {
    private AppInstaller() { }

    static final String PENDING = "update_pending_install";
    static final String AWAITING = "update_awaiting_permission";
    static final String READY_DIGEST = "update_ready_digest";
    static final String READY_VERSION = "update_ready_version";
    private static final String CHANNEL = "update_ready";
    private static final int NOTIFICATION = 3;

    static File apk(Context context) { return new File(context.getCacheDir(), "update.apk"); }
    static File partial(Context context) { return new File(context.getCacheDir(), "update.download"); }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences("mobile", 0);
    }

    static long version(PackageInfo info) {
        return android.os.Build.VERSION.SDK_INT >= 28 ? info.getLongVersionCode() : info.versionCode;
    }

    static long installedVersion(Context context) {
        try { return version(context.getPackageManager().getPackageInfo(context.getPackageName(), 0)); }
        catch (Exception e) { return 0; }
    }

    /**
     * Is this file the update the manifest promised, and is it still ours?
     * Returns null when it is, or a sentence for the user when it is not.
     *
     * Called twice for the same file -- once when the download finishes, once
     * when the app next starts -- so a truncated or replaced package is caught
     * even if the process that downloaded it is long gone.
     */
    static String verify(Context context, File file, long expectedVersion, String digest) {
        try {
            if (!file.isFile()) return "更新包不存在";
            MessageDigest sha = MessageDigest.getInstance("SHA-256");
            try (InputStream in = new FileInputStream(file)) {
                byte[] buffer = new byte[65536];
                int read;
                while ((read = in.read(buffer)) != -1) sha.update(buffer, 0, read);
            }
            StringBuilder hex = new StringBuilder();
            for (byte b : sha.digest()) hex.append(String.format("%02x", b & 255));
            if (digest == null || !digest.equalsIgnoreCase("sha256:" + hex)) return "更新包校验失败，请重新下载";
            PackageManager manager = context.getPackageManager();
            PackageInfo incoming = manager.getPackageArchiveInfo(file.getAbsolutePath(), PackageManager.GET_SIGNATURES);
            PackageInfo current = manager.getPackageInfo(context.getPackageName(), PackageManager.GET_SIGNATURES);
            if (incoming == null || !current.packageName.equals(incoming.packageName)
                    || !Arrays.equals(current.signatures, incoming.signatures))
                return "更新包签名或应用标识不一致";
            if (version(incoming) != expectedVersion) return "安装包版本与清单不一致";
            return null;
        } catch (Exception e) {
            return "更新包无法读取：" + e.getMessage();
        }
    }

    /**
     * Hand the downloaded package to the system installer.
     *
     * @return false when the app is not yet allowed to install packages; the
     *         caller decides how to ask, because that part needs a screen.
     */
    static boolean install(Context context) {
        if (!context.getPackageManager().canRequestPackageInstalls()) {
            prefs(context).edit().putBoolean(AWAITING, true).apply();
            // Both of these need a visible screen. The overlay permission is what
            // lets a background service do it at all; without it, `startActivity`
            // is dropped without an exception, so leave something to tap instead.
            if (Settings.canDrawOverlays(context) && launch(context, new Intent(
                    Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + context.getPackageName())))) return false;
            ready(context, "请允许本应用安装更新，点按继续");
            return false;
        }
        prefs(context).edit().putBoolean(AWAITING, false).apply();
        // The screen-capture service holds the projection; installing over it
        // while it runs is what the old updater stopped, and it still should.
        context.stopService(new Intent(context, CaptureService.class));
        Intent installer = new Intent(Intent.ACTION_VIEW)
                .setDataAndType(Uri.parse("content://" + context.getPackageName() + ".updates/update.apk"),
                        "application/vnd.android.package-archive")
                // NEW_TASK is not optional here: from an Activity it is harmless,
                // from a Service the call throws without it.
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
        return launch(context, installer);
    }

    private static boolean launch(Context context, Intent intent) {
        try { context.startActivity(intent); return true; }
        catch (Exception e) { return false; }
    }

    /**
     * Retry an install that was waiting on the "install unknown apps" toggle.
     *
     * @return true when the installer was actually started again, so the caller
     *         knows to replace "grant the permission" with "confirm the install".
     */
    static boolean resume(Activity activity) {
        if (!prefs(activity).getBoolean(AWAITING, false)) return false;
        if (!activity.getPackageManager().canRequestPackageInstalls()) return false;
        return install(activity);
    }

    /**
     * Claim the one install request owed for the package now on disk.
     *
     * Clears the flag as it reads it: the notification and the pending record are
     * two edges of the same event, and firing twice would re-open the system
     * installer every time the user came back from cancelling it.
     */
    static boolean takePending(Context context) {
        SharedPreferences prefs = prefs(context);
        if (!prefs.getBoolean(PENDING, false)) return false;
        long version = prefs.getLong(READY_VERSION, 0);
        if (version <= installedVersion(context) || !apk(context).isFile()) {
            prefs.edit().putBoolean(PENDING, false).apply();
            return false;
        }
        prefs.edit().putBoolean(PENDING, false).apply();
        clearReady(context);
        return true;
    }

    /**
     * Settle the state left behind by a download that ran while the app was gone.
     *
     * Runs off the main thread: this re-hashes a file that can be over 150 MB.
     * Never re-arms {@link #PENDING} -- an install request is made once per
     * download, not once per resume, or cancelling the system dialog would pop
     * it again every time the user came back.
     */
    static void reconcile(Context context, java.util.function.Consumer<String> report) {
        SharedPreferences prefs = prefs(context);
        if (prefs.getBoolean(PENDING, false)) {
            String reason = verify(context, apk(context), prefs.getLong(READY_VERSION, 0), prefs.getString(READY_DIGEST, ""));
            if (reason != null) {
                apk(context).delete();
                prefs.edit().putBoolean(PENDING, false).putString(READY_DIGEST, "").putLong(READY_VERSION, 0).apply();
                report.accept("更新包已失效，请重新检查更新");
                return;
            }
        }
        // A service that died mid-transfer leaves `busy` set with nothing behind
        // it. Say so rather than showing a progress line that never moves.
        if (prefs.getBoolean(UpdateService.BUSY, false) && UpdateService.current == null) {
            prefs.edit().putBoolean(UpdateService.BUSY, false).apply();
            partial(context).delete();
            report.accept("上次下载已中断，请重新检查更新");
        }
    }

    /** A tappable "the update is ready" notification; the fallback for a dropped launch. */
    static void ready(Context context, String text) {
        NotificationManager manager = (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
        manager.createNotificationChannel(new NotificationChannel(CHANNEL, "更新已下载",
                NotificationManager.IMPORTANCE_HIGH));
        PendingIntent tap = PendingIntent.getActivity(context, 0,
                new Intent(context, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification notification = new Notification.Builder(context, CHANNEL)
                .setSmallIcon(android.R.drawable.ic_menu_mapmode)
                .setContentTitle("加页手记地图助手")
                .setContentText(text)
                .setStyle(new Notification.BigTextStyle().bigText(text))
                .setContentIntent(tap)
                .setAutoCancel(true)
                .build();
        manager.notify(NOTIFICATION, notification);
    }

    static void clearReady(Context context) {
        ((NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE)).cancel(NOTIFICATION);
    }
}
