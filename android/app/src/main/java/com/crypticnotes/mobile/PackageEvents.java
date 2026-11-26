package com.crypticnotes.mobile;

import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONArray;
import org.json.JSONObject;

final class PackageEvents {
    private static final ExecutorService worker = Executors.newSingleThreadExecutor();
    private static final String ENDPOINT = "https://pvp.smgfxyjq.cfd/package-events";

    private static boolean enabled() {
        return !BuildConfig.DEBUG && !BuildConfig.LOCAL_REVIEW && BuildConfig.GRAY_PVP_URL.isEmpty();
    }

    private static SharedPreferences store(Context context) {
        return context.getSharedPreferences("package_receipts", Context.MODE_PRIVATE);
    }

    private static JSONArray pending(SharedPreferences prefs) throws Exception {
        return new JSONArray(prefs.getString("pending", "[]"));
    }

    private static void append(SharedPreferences prefs, SharedPreferences.Editor edit, String component, String version, String action) throws Exception {
        long now = System.currentTimeMillis() / 1000;
        JSONArray events = pending(prefs);
        while (events.length() > 0 && (events.length() >= 256 || events.getJSONObject(0).getLong("time") < now - 30L * 86400)) events.remove(0);
        events.put(new JSONObject().put("id", UUID.randomUUID().toString()).put("time", now).put("platform", "android")
                .put("component", component).put("version", version).put("action", action));
        edit.putString("pending", events.toString());
    }

    static synchronized void installed(Context context, String component, String previous, String checksum, String version) {
        if (!enabled() || checksum.equals(previous)) return;
        try {
            SharedPreferences prefs = store(context);
            SharedPreferences.Editor edit = prefs.edit();
            append(prefs, edit, component, version.isEmpty() ? checksum.substring(0, 12) : version, previous.isEmpty() ? "install" : "update");
            if (edit.commit()) schedule(context);
        } catch (Exception ignored) {}
    }

    static synchronized void launched(Context context) {
        if (!enabled()) return;
        try {
            SharedPreferences prefs = store(context);
            int current = BuildConfig.VERSION_CODE, previous = prefs.getInt("build", -1);
            if (previous != current) {
                String action = null;
                if (previous >= 0) {
                    if (current > previous) action = "update";
                } else {
                    String seen = context.getSharedPreferences("mobile", 0).getString("seen_update_news", "");
                    String suffix = seen.substring(seen.lastIndexOf(':') + 1);
                    if (suffix.matches("[0-9]{1,9}")) {
                        if (current > Long.parseLong(suffix)) action = "update";
                    } else {
                        PackageInfo info = context.getPackageManager().getPackageInfo(context.getPackageName(), 0);
                        action = info.lastUpdateTime > info.firstInstallTime ? "update" : "install";
                    }
                }
                SharedPreferences.Editor edit = prefs.edit().putInt("build", current);
                if (action != null) append(prefs, edit, "app", BuildConfig.VERSION_NAME, action);
                edit.commit();
            }
            schedule(context);
        } catch (Exception ignored) {}
    }

    private static void schedule(Context context) {
        SharedPreferences prefs = store(context);
        worker.execute(() -> {
            try {
                while (true) {
                    JSONObject item;
                    synchronized (PackageEvents.class) { item = pending(prefs).optJSONObject(0); }
                    if (item == null) return;
                    HttpURLConnection connection = (HttpURLConnection) new URL(ENDPOINT).openConnection();
                    int status;
                    try {
                        connection.setConnectTimeout(5000); connection.setReadTimeout(5000);
                        connection.setInstanceFollowRedirects(false); connection.setRequestMethod("POST");
                        connection.setRequestProperty("Content-Type", "application/json"); connection.setDoOutput(true);
                        byte[] data = item.toString().getBytes(StandardCharsets.UTF_8);
                        connection.setFixedLengthStreamingMode(data.length);
                        try (OutputStream output = connection.getOutputStream()) { output.write(data); }
                        status = connection.getResponseCode();
                    } finally { connection.disconnect(); }
                    if (status != 204 && status != 400 && status != 413 && status != 415 && status != 422) return;
                    synchronized (PackageEvents.class) {
                        JSONArray events = pending(prefs);
                        if (events.length() > 0 && events.getJSONObject(0).getString("id").equals(item.getString("id"))) {
                            events.remove(0);
                            if (!prefs.edit().putString("pending", events.toString()).commit()) return;
                        }
                    }
                }
            } catch (Exception ignored) {}
        });
    }
}
