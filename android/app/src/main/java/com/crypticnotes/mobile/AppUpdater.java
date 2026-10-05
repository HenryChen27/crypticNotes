package com.crypticnotes.mobile;

import android.app.Activity;
import android.widget.TextView;
import org.json.*;
import java.io.*;
import java.net.*;

/**
 * User-initiated, signed APK update. No game screenshots leave the device.
 *
 * This used to download as well, in a thread whose `finally` deleted the partial
 * file -- so switching away from the settings screen threw the transfer away.
 * The transfer now belongs to {@link UpdateService}, which survives leaving the
 * app; what is left here is the part that genuinely needs a visible screen:
 * asking the release API what the current version is, and reporting back.
 */
final class AppUpdater implements UpdateService.Listener {
    static final String ASSET = "IdentityVMapAssistant-Android-arm64.apk";
    private final Activity activity;
    private final TextView status;
    private final Theme.Spinner spinner;
    private boolean running, pendingManual;
    private java.util.function.Consumer<Boolean> availability = value -> {};
    void onAvailability(java.util.function.Consumer<Boolean> listener) { availability=listener; }
    private void available(boolean value) {
        activity.runOnUiThread(() -> { if(!activity.isDestroyed()) availability.accept(value); });
    }
    AppUpdater(Activity activity, TextView status, Theme.Spinner spinner) { this.activity=activity; this.status=status; this.spinner=spinner; }
    /**
     * Show or hide the turning emblem. The percentage is reported as text: the
     * download is one long opaque transfer, so a bar would mostly sit still.
     */
    private void progress(boolean busy) {
        activity.runOnUiThread(() -> {
            if(activity.isDestroyed()) return;
            spinner.setVisibility(busy ? android.view.View.VISIBLE : android.view.View.GONE);
            if(busy) spinner.start(); else spinner.stop();
        });
    }
    private void message(String text) { activity.runOnUiThread(() -> { if (!activity.isDestroyed()) status.setText(text); }); }
    private static HttpURLConnection connect(String url) throws IOException {
        if (!url.startsWith("https://")) throw new IOException("更新地址必须为 HTTPS");
        HttpURLConnection c=(HttpURLConnection)new URL(url).openConnection();
        c.setConnectTimeout(20000); c.setReadTimeout(30000);
        c.setRequestProperty("User-Agent", "CrypticNotes-Android");
        if (c.getResponseCode()!=200) { int code=c.getResponseCode(); c.disconnect(); throw new IOException("服务器返回 "+code); }
        return c;
    }
    /** Live progress from the download service. Called off the main thread. */
    @Override public void onUpdate(String text, int percent, boolean busy) {
        message(text);
        progress(busy);
    }
    void check() {
        check(false);
    }
    void checkSilently() { check(true); }
    private void check(boolean silent) {
        if (running) { if(!silent) pendingManual=true; return; }
        running=true;
        if(!silent) { message("正在检查安卓更新…"); progress(true); }
        new Thread(() -> {
            boolean handedOff=false;
            try {
                HttpURLConnection c=connect("https://api.github.com/repos/HenryChen27/crypticNotes/releases/latest");
                JSONObject release;
                try(InputStream in=c.getInputStream(); ByteArrayOutputStream out=new ByteArrayOutputStream()) {
                    byte[] b=new byte[8192]; int n;
                    while((n=in.read(b))!=-1) { out.write(b,0,n); if(out.size()>2_000_000) throw new IOException("更新信息过大"); }
                    release=new JSONObject(out.toString("UTF-8"));
                } finally { c.disconnect(); }
                JSONArray assets=release.getJSONArray("assets"); JSONObject asset=null;
                for(int i=0;i<assets.length();i++) if(ASSET.equals(assets.getJSONObject(i).getString("name"))) asset=assets.getJSONObject(i);
                if(asset==null) { if(!silent) message("暂未发布安卓更新包"); return; }
                JSONObject manifestAsset=null;
                for(int i=0;i<assets.length();i++) if("android-update.json".equals(assets.getJSONObject(i).getString("name"))) manifestAsset=assets.getJSONObject(i);
                if(manifestAsset==null) throw new IOException("发布者尚未上传版本清单");
                c=connect(manifestAsset.getString("browser_download_url"));
                JSONObject manifest;
                try(InputStream in=c.getInputStream(); ByteArrayOutputStream out=new ByteArrayOutputStream()) {
                    byte[] b=new byte[4096]; int n;
                    while((n=in.read(b))!=-1) { out.write(b,0,n); if(out.size()>65536) throw new IOException("版本清单过大"); }
                    manifest=new JSONObject(out.toString("UTF-8"));
                } finally { c.disconnect(); }
                long advertised=manifest.getLong("versionCode");
                long installed=AppInstaller.installedVersion(activity);
                if(!activity.getPackageName().equals(manifest.getString("packageName"))) throw new IOException("版本清单应用不一致");
                if(advertised<=installed) { available(false); message("已是最新版本"); return; }
                if(!ASSET.equals(manifest.getString("asset")) || manifest.getLong("size")!=asset.getLong("size")
                        || !asset.optString("digest").equalsIgnoreCase("sha256:"+manifest.getString("sha256")))
                    throw new IOException("发布文件正在更新，请稍后重试");
                String digest=asset.optString("digest");
                if(!digest.matches("sha256:[0-9a-fA-F]{64}")) throw new IOException("更新包缺少 SHA-256 校验信息");
                available(true);
                if(silent) { message("发现新版本，点击检查应用更新安装"); return; }
                String known=activity.getPreferences(0).getString("installed_digest", "");
                if(known.equals(digest+":"+installed)) { message("已是最新版本"); return; }
                long expected=asset.getLong("size");
                if(expected<=0 || expected>400_000_000) throw new IOException("更新包大小异常");
                // The service re-checks every one of these itself; it is handed the
                // numbers rather than the connection so the two cannot disagree.
                UpdateService.start(activity, asset.getString("browser_download_url"), digest, expected, advertised);
                handedOff=true;
                message("正在后台下载更新，可以离开本页面。");
            } catch(Exception e) { if(!silent) message("更新失败："+e.getMessage()+"。可稍后重试。"); }
            finally {
                // The emblem belongs to the service once the transfer is handed
                // over; switching it off here would undo the service's first tick.
                if(!handedOff) progress(false);
                if(!handedOff) activity.runOnUiThread(() -> {
                    running=false;
                    if(pendingManual && !activity.isDestroyed()) { pendingManual=false; check(); }
                });
                else running=false;
            }
        },"app-update-check").start();
    }
    /**
     * Coming back to the screen: finish an install that was waiting on the
     * "install unknown apps" toggle, or one that finished downloading while the
     * user was elsewhere. The package was verified before either flag was set.
     */
    void resume() {
        if (AppInstaller.resume(activity)) { message("请在系统窗口确认更新，完成后重新开启识图。"); return; }
        installPending();
    }
    /** Also used by the screen once a background download has been reconciled. */
    void installPending() {
        if (AppInstaller.takePending(activity)) install();
    }
    private void install() {
        if (AppInstaller.install(activity)) message("请在系统窗口确认更新，完成后重新开启识图。");
        else message("请允许本应用安装更新，返回后继续安装。");
    }
    /** The one line the screen prints progress into. */
    TextView statusView() { return status; }
}
