package com.crypticnotes.mobile;

import android.app.Activity;
import android.content.Intent;
import android.content.pm.*;
import android.net.Uri;
import android.provider.Settings;
import android.widget.TextView;
import org.json.*;
import java.io.*;
import java.net.*;
import java.security.MessageDigest;
import java.util.Arrays;

/** User-initiated, signed APK update. No game screenshots leave the device. */
final class AppUpdater {
    static final String ASSET = "IdentityVMapAssistant-Android-arm64.apk";
    private final Activity activity;
    private final TextView status;
    private boolean running, awaitingPermission;
    private static long version(PackageInfo info) { return android.os.Build.VERSION.SDK_INT >= 28 ? info.getLongVersionCode() : info.versionCode; }
    AppUpdater(Activity activity, TextView status) { this.activity=activity; this.status=status; }
    private void message(String text) { activity.runOnUiThread(() -> { if (!activity.isDestroyed()) status.setText(text); }); }
    private static HttpURLConnection connect(String url) throws IOException {
        if (!url.startsWith("https://")) throw new IOException("更新地址必须为 HTTPS");
        HttpURLConnection c=(HttpURLConnection)new URL(url).openConnection();
        c.setConnectTimeout(20000); c.setReadTimeout(30000);
        c.setRequestProperty("User-Agent", "CrypticNotes-Android");
        if (c.getResponseCode()!=200) { int code=c.getResponseCode(); c.disconnect(); throw new IOException("服务器返回 "+code); }
        return c;
    }
    void check() {
        if (running) return;
        running=true; message("正在检查安卓更新…");
        new Thread(() -> {
            File temp=new File(activity.getCacheDir(), "update.download");
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
                if(asset==null) { message("暂未发布安卓更新包"); return; }
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
                long installed=version(activity.getPackageManager().getPackageInfo(activity.getPackageName(),0));
                if(!activity.getPackageName().equals(manifest.getString("packageName"))) throw new IOException("版本清单应用不一致");
                if(advertised<=installed) { message("已是最新版本"); return; }
                if(!ASSET.equals(manifest.getString("asset")) || manifest.getLong("size")!=asset.getLong("size")
                        || !asset.optString("digest").equalsIgnoreCase("sha256:"+manifest.getString("sha256")))
                    throw new IOException("发布文件正在更新，请稍后重试");
                String digest=asset.optString("digest");
                if(!digest.matches("sha256:[0-9a-fA-F]{64}")) throw new IOException("更新包缺少 SHA-256 校验信息");
                String known=activity.getPreferences(0).getString("installed_digest", "");
                long version=version(activity.getPackageManager().getPackageInfo(activity.getPackageName(),0));
                if(known.equals(digest+":"+version)) { message("已是最新版本"); return; }
                long expected=asset.getLong("size");
                if(expected<=0 || expected>400_000_000) throw new IOException("更新包大小异常");
                message("正在下载更新，请保持此页面打开…");
                MessageDigest sha=MessageDigest.getInstance("SHA-256");
                c=connect(asset.getString("browser_download_url")); long received=0; int last=-1;
                try(InputStream in=c.getInputStream(); OutputStream out=new FileOutputStream(temp)) {
                    byte[] b=new byte[65536]; int n;
                    while((n=in.read(b))!=-1) {
                        received+=n; if(received>expected) throw new IOException("更新包大小不符");
                        out.write(b,0,n); sha.update(b,0,n);
                        int percent=(int)(received*100/expected);
                        if(percent/5!=last) { last=percent/5; message("下载更新 "+percent+"%"); }
                    }
                } finally { c.disconnect(); }
                StringBuilder hex=new StringBuilder(); for(byte b:sha.digest()) hex.append(String.format("%02x", b&255));
                if(received!=expected || !digest.equalsIgnoreCase("sha256:"+hex)) throw new IOException("下载校验失败，请重试");
                PackageManager pm=activity.getPackageManager();
                PackageInfo incoming=pm.getPackageArchiveInfo(temp.toString(), PackageManager.GET_SIGNATURES);
                PackageInfo current=pm.getPackageInfo(activity.getPackageName(), PackageManager.GET_SIGNATURES);
                if(incoming==null || !current.packageName.equals(incoming.packageName)
                        || !Arrays.equals(current.signatures,incoming.signatures)) throw new IOException("更新包签名或应用标识不一致");
                if(version(incoming)!=advertised) throw new IOException("安装包版本与清单不一致");
                if(version(incoming)<=version) {
                    activity.getPreferences(0).edit().putString("installed_digest",digest+":"+version).apply();
                    message("已是最新版本"); return;
                }
                File apk=new File(activity.getCacheDir(),"update.apk");
                if(apk.exists() && !apk.delete()) throw new IOException("无法替换旧下载包");
                if(!temp.renameTo(apk)) throw new IOException("无法保存更新包");
                activity.runOnUiThread(() -> { if(!activity.isDestroyed()) install(); });
            } catch(Exception e) { message("更新失败："+e.getMessage()+"。可稍后重试。"); }
            finally { temp.delete(); activity.runOnUiThread(() -> running=false); }
        },"app-update").start();
    }
    void resume() { if(awaitingPermission && activity.getPackageManager().canRequestPackageInstalls()) { awaitingPermission=false; install(); } }
    private void install() {
        try {
            if(!activity.getPackageManager().canRequestPackageInstalls()) {
                awaitingPermission=true;
                message("请允许本应用安装更新，返回后继续安装。");
                activity.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,Uri.parse("package:"+activity.getPackageName()))); return;
            }
            activity.stopService(new Intent(activity,CaptureService.class));
            activity.startActivity(new Intent(Intent.ACTION_VIEW)
                    .setDataAndType(Uri.parse("content://"+activity.getPackageName()+".updates/update.apk"),"application/vnd.android.package-archive")
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION));
            message("请在系统窗口确认更新，完成后重新开启识图。");
        } catch(Exception e) { message("无法打开安装界面："+e.getMessage()); }
    }
}
