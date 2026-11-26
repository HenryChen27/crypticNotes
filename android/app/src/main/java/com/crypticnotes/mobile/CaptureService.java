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
    private SharedScreenRecorder recorder;
    private boolean stoppingRecording, recordingReady, pendingCaptureResize, capturedVisible=true;
    /**
     * `recorder` is a replay buffer, not a recording the user started: it runs
     * unannounced for as long as the game is up, so everything that tells the
     * user "you are recording" (pulsing badge, long-press-to-save, the status
     * line) has to leave it alone.
     */
    private boolean replaySession;
    /** Length of the buffer that is running, to notice when the setting has moved on. */
    private int replaySeconds;
    /** The user pressed 屏幕录制 while the replay buffer held the encoder. */
    private boolean pendingRecording;
    /** The buffer stopped with an error; do not restart it in a loop. */
    private boolean replayFailed;
    /** releaseGameCapture() had to stop the buffer first and is owed a second call. */
    private boolean pendingGameRelease;
    private Theme.ChalkButton recordButton, replayButton;
    private android.animation.ObjectAnimator recordingPulse;
    private void updateRecordingPulse() {
        if(badgeEmblem==null) return;
        if(!recordingReady || stoppingRecording || replaySession) {
            if(recordingPulse!=null) recordingPulse.cancel();
            badgeEmblem.setAlpha(1f); return;
        }
        if(recordingPulse==null) {
            recordingPulse=android.animation.ObjectAnimator.ofFloat(badgeEmblem,"alpha",1f,.45f);
            recordingPulse.setDuration(1100);
            recordingPulse.setRepeatCount(android.animation.ValueAnimator.INFINITE);
            recordingPulse.setRepeatMode(android.animation.ValueAnimator.REVERSE);
            recordingPulse.setInterpolator(new android.view.animation.AccelerateDecelerateInterpolator());
        }
        if(!recordingPulse.isStarted()) recordingPulse.start();
    }
    private int capturedWidth, capturedHeight;
    private volatile String lastGateResult="尚未检测",lastMatchResult="尚未匹配",lastPauseReason="";
    private int loadedMapCount;
    private long lastFreshFrameAt;
    void copyRecognitionDiagnostic(){
        long now=SystemClock.elapsedRealtime();
        String protection="未知";
        try{protection=String.valueOf(android.provider.Settings.Secure.getInt(getContentResolver(),"screen_share_protection_on",-1));}catch(Exception ignored){}
        String report="小布偶识图诊断\n版本="+BuildConfig.VERSION_NAME+" ("+BuildConfig.VERSION_CODE+")"
            +"\n设备="+Build.MANUFACTURER+" "+Build.MODEL+", Android "+Build.VERSION.RELEASE+", "+Build.VERSION.INCREMENTAL
            +"\n系统共享防护="+protection+"\n已加载地图="+loadedMapCount
            +"\n界面="+width+"x"+height+", 共享源="+capturedWidth+"x"+capturedHeight
            +"\n有共享="+(projection!=null)+", 可见="+capturedVisible+", 比例符合="+captureFitsScreen()
            +"\n初始化="+initializing+", 就绪="+ready+", 小游戏模式="+gameOnly+", 隐藏叠图="+overlayHidden
            +"\n自动展开检测="+automaticMapProbe()+", 省电="+powerSaving()+", 会话活动="+touchCapture.awake()+", 待机检查次数="+idleProbeChecks+", 正在录屏="+(recorder!=null)
            +"\n忙碌="+busy+", 检测中="+checking+", 排队="+manualRetry+", 状态="+state
            +"\n匹配耗时ms="+(busy?now-busySince:0)+", 检测耗时ms="+(checking?now-checkingSince:0)
            +"\n新帧数="+freshCaptureCount+", 距新帧ms="+(lastFreshFrameAt==0?-1:now-lastFreshFrameAt)
            +"\n暂停原因="+lastPauseReason+"\n展开检测="+lastGateResult+"\n最近匹配="+lastMatchResult;
        ((android.content.ClipboardManager)getSystemService(CLIPBOARD_SERVICE)).setPrimaryClip(android.content.ClipData.newPlainText("识图诊断",report));
        Toast.makeText(this,"诊断已复制，请粘贴发给开发者",Toast.LENGTH_LONG).show();
    }


    private boolean captureFitsScreen() {
        if(capturedWidth<=0 || capturedHeight<=0 || width<=0 || height<=0) return true;
        return Math.abs((double)capturedWidth/capturedHeight/((double)width/height)-1)<.03;
    }

    private Notification captureNotification() {
        PendingIntent action=PendingIntent.getService(this,0,new Intent(this,CaptureService.class).setAction("stop"),
                PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
        Notification.Builder builder=new Notification.Builder(this,"capture").setSmallIcon(android.R.drawable.ic_menu_mapmode)
                .setContentTitle(gameOnly?"加页手记小游戏悬浮窗":pvp&&recorder==null?"禁选辅助":recorder==null?"加页手记正在本机识图":replaySession?"加页手记正在识图（回溯录制已开）":"加页手记正在识图并录屏"+(recorder.hasAudio()?"（内部声音）":"（无声）"))
                .setContentText(gameOnly&&projection==null?"小游戏专用模式，不采集屏幕、不识别地图":"点击停止可结束屏幕采集").setOngoing(true)
                .addAction(new Notification.Action.Builder(null,"停止全部",action).build());
        if(recorder!=null && replaySession) {
            PendingIntent save=PendingIntent.getService(this,2,new Intent(this,CaptureService.class).setAction("save_replay"),
                    PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
            builder.addAction(new Notification.Action.Builder(null,RecordPresets.replayLabel(replaySeconds),save).build());
        } else if(recorder!=null) {
            PendingIntent stopVideo=PendingIntent.getService(this,1,new Intent(this,CaptureService.class).setAction("stop_recording"),
                    PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
            builder.addAction(new Notification.Action.Builder(null,"保存录屏",stopVideo).build());
        }
        return builder.build();
    }

    private void toggleRecording() {
        if(recorder!=null && replaySession) {
            // One encoder, one surface: the buffer lets go first, and the
            // recording starts from its finished() callback.
            pendingRecording=true; stopRecording(); return;
        }
        if(recorder!=null) { stopRecording(); return; }
        startRecorder(false);
    }

    /**
     * Starts the replay buffer when it is switched on and nothing else holds the
     * encoder. Landscape only, like the idle check: portrait is not the game.
     */
    void ensureReplay() {
        if(destroyed || gameOnly || replayFailed || pendingRecording || recorder!=null || stoppingRecording
                || projection==null || display==null || reader==null || width<=height) return;
        if(RecordPresets.storedReplaySeconds(this)>0) startRecorder(true);
    }

    /** The settings screen changed the replay switch. */
    void replaySettingChanged() {
        replayFailed=false;
        int wanted=RecordPresets.storedReplaySeconds(this);
        // Off, or another length: the running buffer is the wrong size either
        // way. Stopping it is enough -- finished() starts the one now wanted.
        if(recorder!=null && replaySession && wanted!=replaySeconds) stopRecording();
        else if(wanted>0) ensureReplay();
        updateRecordingButton();
    }

    private void saveReplay() {
        if(recorder==null || !replaySession || !recordingReady || stoppingRecording) {
            Toast.makeText(this,"回溯录制还没有准备好",Toast.LENGTH_SHORT).show();
            return;
        }
        recorder.saveReplay();
    }

    private void startRecorder(final boolean replay) {
        if(projection==null || display==null || reader==null || stoppingRecording || recorder!=null) return;
        replaySession=replay;
        replaySeconds=replay?RecordPresets.storedReplaySeconds(this):0;
        idleProbe.cancel();display.resize(width,height,density);
        final SharedScreenRecorder[] session=new SharedScreenRecorder[1];
        final ImageReader recordingReader=reader;
        display.setSurface(null); // A Surface can have only one producer.
        recordingReady=false;
        final RecordPresets.Settings settings=RecordPresets.snapshot(this);
        // Internal sound is now the default, so a user who never granted the
        // recording permission starts their first take silently. Ask once, at
        // the end of that take, when the result is in front of them.
        final boolean wantAudioPermission=RecordPresets.storedInternalAudio(this) && !settings.audio
                && Build.VERSION.SDK_INT>=29;
        session[0]=new SharedScreenRecorder(this,reader.getSurface(),width,height,projection,
                settings,replaySeconds,new SharedScreenRecorder.Listener() {
            public void replaySaved(String location,int seconds,String error) {
                if(destroyed) return;
                setStatus(S_IDLE,error==null?"已保存前 "+seconds+" 秒到 "+location:"保存失败："+error);
            }
            public void warning(String text) { if(!destroyed) Toast.makeText(CaptureService.this,text,Toast.LENGTH_LONG).show(); }
            public void ready(Surface input) {
                if(destroyed || recorder!=session[0] || stoppingRecording) { session[0].stop(); return; }
                try {
                    display.setSurface(input);
                    recordingReady=true;
                    updateRecordingButton();
                    if(!replay) {
                        setStatus(S_IDLE,recorder.hasAudio()?"正在录制操作（内部声音）":"正在录制操作（无声）");
                        if(quickSettings!=null) closeQuickSettings();
                    }
                } catch(Exception e) { stopRecording(); }
            }
            public void finished(String location,String error) {
                if(recorder!=session[0]) return;
                if(!destroyed && display!=null && reader!=null) display.setSurface(reader.getSurface());
                recorder=null; stoppingRecording=false;
                recordingReady=false; replaySession=false;
                if(destroyed) recordingReader.close();
                if(!destroyed) {
                    updateRecordingButton();
                    if(!replay) {
                        setStatus(S_IDLE,error==null?"录屏已保存到 "+location:"录屏失败："+error);
                        if(wantAudioPermission) promptAudioPermission();
                    } else if(error!=null) {
                        replayFailed=true;
                        setStatus(S_IDLE,"回溯录制已停止："+error);
                    }
                    if(pendingCaptureResize) { pendingCaptureResize=false; resizeCapture(); }
                    updateCaptureOutput();invalidateSamples(); repoll(WATCH_MS);
                    if(pendingRecording) { pendingRecording=false; startRecorder(false); }
                    else if(pendingGameRelease) { pendingGameRelease=false; releaseGameCapture(); }
                    else ensureReplay();
                }
            }
        });
        recorder=session[0]; recorder.start(); updateRecordingButton();
    }

    private void updateRecordingButton() {
        updateRecordingPulse();
        if(!destroyed) ((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).notify(1,captureNotification());
        if(recordButton!=null) {
            boolean recording=recorder!=null && !replaySession;
            recordButton.setText(stoppingRecording?(replaySession?"请稍候…":"正在保存…"):recording?"停止录制":"屏幕录制");
            ActionIcon.set(recordButton,recording?ActionIcon.STOP:ActionIcon.RECORD,false);
            recordButton.setEnabled(!stoppingRecording);
        }
        if(replayButton!=null) replayButton.setEnabled(recorder!=null && replaySession && recordingReady && !stoppingRecording);
    }

    private void stopRecording() {
        if(recorder==null || stoppingRecording) return;
        stoppingRecording=true;
        recordingReady=false;
        if(display!=null) display.setSurface(null);
        recorder.stop(); updateRecordingButton();
    }

    /**
     * Offer the recording permission once, right after a take that wanted
     * internal sound and could not have it.
     *
     * Only once: an app that interrupts a game after every take to ask the same
     * question is worse than one that stays silent. After that the settings
     * screen's own "声音" row is the way back, and it re-asks every time.
     * The overlay is on screen at this moment, so SYSTEM_ALERT_WINDOW covers
     * starting an activity from this service.
     */
    private void promptAudioPermission() {
        if(getSharedPreferences("mobile",0).getBoolean("record_audio_prompted",false)) return;
        getSharedPreferences("mobile",0).edit().putBoolean("record_audio_prompted",true).apply();
        try {
            startActivity(new Intent(this,AudioPermissionActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        } catch(Exception e) {
            Toast.makeText(this,"录屏是无声的：到「通用设置 → 录屏设置 → 声音」授予录音权限",Toast.LENGTH_LONG).show();
        }
    }
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
    /** Declared here, not with its neighbours, because the runnable below reads it. */
    private int state = S_IDLE;
    private final Runnable hideBadgeMessage = () -> {
        collapseBadge();
        // The emblem is alone again; if a match is still running it has to keep
        // turning, otherwise the bubble folding up looks like a stall.
        setSpinning(state == S_MATCHING);
    };
    /** A hung match must not wedge the loop with `busy` stuck true. */
    private static final long BUSY_TIMEOUT_MS = 5000;
    /** Consecutive negative gate verdicts before the fit is discarded outright. */
    private static final int MISS_LIMIT = 2;
    /**
     * The map viewport in 160x90 sample cells: x 0.4125-0.8625, y 0.1222-0.8667.
     * Same rectangle the geometric evidence mask and the stability check use.
     */
    private static final int SAMPLE_X0 = 66, SAMPLE_X1 = 138, SAMPLE_Y0 = 11, SAMPLE_Y1 = 78;
    /** Default resting place of the floating button, as fractions of the screen. */
    private static final float BADGE_X = .195f, BADGE_Y = .01f;

    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService compute = Executors.newSingleThreadExecutor();
    private final ExecutorService inspect = Executors.newSingleThreadExecutor();
    private MediaProjection projection; private VirtualDisplay display; private ImageReader reader;
    private WindowManager windows; private ImageView overlay; private LinearLayout badge;
    /** Kept so the in-game opacity control can retune the live layer. */
    private WindowManager.LayoutParams overlayParams;
    // `bridge` and `ready` are written on the compute thread and read on the
    // main thread. Volatile keeps that handoff explicit rather than relying on
    // the Handler hop that happens to publish it today.
    private volatile PyObject bridge;
    private volatile boolean destroyed = false, ready = false;
    private boolean initializing = true;
    private String preparationText = "正在准备地图库，首次启动需要稍候";
    private TextView preparationLabel;
    /** Owned by the main thread: set in runMatch, cleared in its callback. */
    private boolean checking = false;
    private long checkingSince = 0;
    private boolean manualRetry = false;
    private static final class PendingMatch {
        final RawFrame frame; final int[] pixels; final int floor, generation, serial;
        PendingMatch(RawFrame frame,int[] pixels,int floor,int generation,int serial){
            this.frame=frame;this.pixels=pixels;this.floor=floor;this.generation=generation;this.serial=serial;
        }
    }
    /**
     * A frame as the Bitmap holds it: RGBA bytes plus the row stride.
     *
     * This is what the PNG round trip used to carry to Python and back out of
     * {@code cv2.imdecode}. PNG is lossless, so the matcher sees the same bytes;
     * what is gone is a full-frame encode on this side and a decode on the other,
     * on every gate heartbeat and every match.
     */
    static final class RawFrame {
        final byte[] bytes; final int width, height, stride;
        long captureStartedAt, nativeFloorMs;
        RawFrame(byte[] bytes,int width,int height,int stride){this.bytes=bytes;this.width=width;this.height=height;this.stride=stride;}
    }
    /** Copies the pixels out; the caller still owns (and recycles) the Bitmap. */
    private static RawFrame rawFrame(Bitmap bitmap){
        ByteBuffer buffer=ByteBuffer.allocate(bitmap.getRowBytes()*bitmap.getHeight());
        bitmap.copyPixelsToBuffer(buffer);
        return new RawFrame(buffer.array(),bitmap.getWidth(),bitmap.getHeight(),bitmap.getRowBytes());
    }
    /** Only for the opt-in diagnostic dump, which wants a viewable file. */
    private static byte[] png(RawFrame frame){
        Bitmap bitmap=Bitmap.createBitmap(frame.width,frame.height,Bitmap.Config.ARGB_8888);
        try{
            bitmap.copyPixelsFromBuffer(ByteBuffer.wrap(RgbaRows.packed(ByteBuffer.wrap(frame.bytes),frame.width,frame.height,frame.stride).array()));
            ByteArrayOutputStream output=new ByteArrayOutputStream();
            return bitmap.compress(Bitmap.CompressFormat.PNG,100,output)?output.toByteArray():null;
        }catch(Exception e){return null;}finally{bitmap.recycle();}
    }
    private PendingMatch pendingLatestMatch;
    private boolean startPendingMatch(){
        PendingMatch next=pendingLatestMatch;pendingLatestMatch=null;
        if(next==null)return false;
        if(destroyed || next.generation!=generation || next.serial!=matchRequests.get()
                || !mapPanelOpen || overlayHidden || MiniGameOverlayService.running)return false;
        android.util.Log.i("CrypticNotes","Latest screenshot started: request="+next.serial);
        setStatus(S_MATCHING,null);
        runMatch(next.frame,next.pixels,next.floor);
        return true;
    }
    private final java.util.concurrent.atomic.AtomicInteger matchRequests = new java.util.concurrent.atomic.AtomicInteger();
    private View manualPrompt;
    private int pendingForceFloor;
    private boolean manualOfferSuppressed;

    private void dismissManualPrompt() {
        if(manualPrompt!=null) { windows.removeView(manualPrompt);manualPrompt=null; }
    }

    private void showManualPrompt(JSONObject offer,int token) {
        if(manualOfferSuppressed || manualPrompt!=null) return;
        final int floor=offer.optInt("floor");
        manualPrompt=new ManualAlignmentPrompt(this,()-> {
            if(destroyed || token!=generation) { dismissManualPrompt();return; }
            matchRequests.incrementAndGet();clearOverlay();pendingForceFloor=floor;manualRetry=true;lastMatch=0;
            repoll(0);
        },()-> { dismissManualPrompt();manualOfferSuppressed=true; });
        WindowManager.LayoutParams p=params(Theme.px(this,200),Theme.px(this,106),true);
        p.x=Math.max(0,Math.min(width-p.width,badgeParams.x-p.width));
        p.y=Math.max(0,Math.min(height-p.height,badgeParams.y));
        windows.addView(manualPrompt,p);
    }
    private boolean timeoutReported = false;
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
    /** Spins the emblem while a match runs. Built on first use, then reused. */
    private android.animation.ObjectAnimator spin;
    /** True while a difficulty change is rebuilding the matcher. */
    private boolean applying = false;
    /** Latest rebuild request; earlier ones report nothing and re-arm nothing. */
    private int applyToken = 0;
    private View tapRegion; private RegionCalibrationView calibration;
    private RectF tapBounds;
    private WindowManager.LayoutParams badgeParams;
    private TextView badgeLabel; private ImageView badgeEmblem;
    /** Collapsed width, expanded width and height of the button, in pixels. */
    private int ballWidth, stripWidth, badgeHeight;
    /** True when the bubble unfolds to the left, because the right has no room. */
    private boolean bubbleLeft;
    private android.animation.ValueAnimator bubbleAnim;
    private Runnable badgeLongPress; private boolean badgeLongPressed = false;
    private long badgeTapAt;
    private float badgeTapX, badgeTapY;
    private boolean badgeSecondTap;
    private final Runnable badgeSingleTap = () -> { badgeTapAt = 0; if (destroyed) return; if (this.pvp && this.pvpScanning) { if (this.pvpEntry == null) showPvpEntry(); } else toggleQuickSettings(); };

    private void retryFromBadge() {
        if(pvp&&!gameOnly&&!MiniGameOverlayService.running){togglePvpScan();return;}
        if(gameOnly&&!MiniGameOverlayService.running){startActivity(new Intent(this,MainActivity.class).putExtra("launch_game",getSharedPreferences("mobile",0).getString("active_game","jellyfish")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_SINGLE_TOP));return;}
        if(MiniGameOverlayService.running){if(MiniGameOverlayService.hidden)startForegroundService(new Intent(this,MiniGameOverlayService.class).setAction("show"));return;}
        badgeText = ""; // Explicit actions must acknowledge every tap.
        if (!ready && !applying) { setStatus(S_IDLE, "正在准备，请稍候"); return; }
        if (quickSettings != null) closeQuickSettings();
        overlayHidden = false;
        clearOverlay(); lastMatch = 0;
        manualRetry = true;
        wakeRecognition();
        android.util.Log.i("CrypticNotes","Manual recognition queued: busy="+busy+", checking="+checking+", token="+generation);
        setStatus(S_MATCHING, "正在重新识别…");
        if (!applying) { ready = true; repoll(0); }
    }
    private float badgeDownX, badgeDownY; private int badgeStartX, badgeStartY;
    private boolean badgeDragged = false;
    private boolean refreshBundledMaps = false;
    /** True while the player has asked for the overlay to stay off. */
    private boolean overlayHidden = false;

    private static final int S_IDLE = 0, S_MATCHING = 1, S_MATCHED = 2, S_FAILED = 3;

    /** Button geometry at scale 1; the player scales the first two via settings. */
    private static final int BADGE_BALL_DP = 44, BADGE_EMBLEM_DP = 26, BADGE_MESSAGE_DP = 220;
    private static final float BADGE_SCALE_MIN = .7f, BADGE_SCALE_MAX = 1.6f, BADGE_SCALE_DEFAULT = 1f;
    /** How long the bubble takes to grow out of the ball, and to fold back. */
    private static final long BUBBLE_MS = 200;
    /**
     * Hold time before the button shuts recognition down.
     *
     * Longer than the platform's 500ms on purpose. The same small target now
     * carries four gestures, and this is the only destructive one, so it has to
     * be unmistakable rather than merely unhurried: a hold long enough to be a
     * decision, not a tap that lingered.
     */
    private static final long BADGE_HOLD_MS = 900;

    private final IdleMapProbe idleProbe=new IdleMapProbe(main);
    private boolean idleProbeScheduled,idleChecking;
    private long idleProbeChecks;
    private boolean automaticMapProbe(){return getSharedPreferences("mobile",0).getBoolean("automatic_map_probe",true);}
    private void scheduleIdleProbe(){
        if(destroyed || pvp || !ready || !recognitionIdle() || !automaticMapProbe() || idleProbeScheduled || idleChecking || idleProbe.active())return;
        idleProbeScheduled=true;
        main.postDelayed(idleProbeTick,powerSaving()?2000:1000);
    }
    private final Runnable idleProbeTick=()->{
        idleProbeScheduled=false;
        if(destroyed || this.pvp || !ready || !recognitionIdle() || !automaticMapProbe()){
            // The mirror stays attached between checks, so switching the
            // automatic check off has to release it explicitly.
            if(!automaticMapProbe())idleProbe.cancel();
            return;
        }
        if(projection==null || display==null || !capturedVisible || width<=height || quickSettings!=null || calibration!=null || overlayHidden){scheduleIdleProbe();return;}
        try{
            if(recorder!=null){
                // Reuse the recording preview; never resize its VirtualDisplay.
                if(!recordingReady || stoppingRecording){scheduleIdleProbe();return;}
                Bitmap frame=grab();
                if(frame==null){scheduleIdleProbe();return;}
                Bitmap small=Bitmap.createScaledBitmap(frame,480,Math.max(1,Math.round(frame.getHeight()*480f/frame.getWidth())),true);
                if(small!=frame)frame.recycle();
                inspectIdleFrame(small);
            }else idleProbe.start(display,width,height,density,this::inspectIdleFrame);
        }catch(Exception error){android.util.Log.w("CrypticNotes","Idle map probe failed",error);idleProbe.cancel();updateCaptureOutput();scheduleIdleProbe();}
    };
    private void inspectIdleFrame(Bitmap frame){
        if(frame==null){scheduleIdleProbe();return;}
        if(destroyed || !recognitionIdle()){frame.recycle();return;}
        idleChecking=true;idleProbeChecks++;
        final int token=generation;
        final float[] excluded=badgeParams==null?null:new float[]{
            Math.max(0,badgeParams.x-6)/(float)width,Math.max(0,badgeParams.y-6)/(float)height,
            Math.min(width,badgeParams.x+badgeParams.width+6)/(float)width,
            Math.min(height,badgeParams.y+badgeHeight+6)/(float)height};
        try{inspect.execute(()->{
            boolean visible=false;
            try{
                RawFrame bytes=encode(frame);
                if(bytes!=null)visible=new JSONObject(bridge.callAttr("inspect",bytes.bytes,excluded,bytes.width,bytes.height,bytes.stride).toString()).optBoolean("visible");
            }catch(Exception error){android.util.Log.w("CrypticNotes","Idle controls inspection failed",error);}
            final boolean opened=visible;
            main.post(()->{
                idleChecking=false;
                if(destroyed)return;
                if(token==generation && recognitionIdle() && opened && automaticMapProbe()){
                    clearOverlay();lastMatch=0;wakeRecognition();
                    android.util.Log.i("CrypticNotes","Map controls detected by the low-resolution mirror; full capture resumed");
                }else scheduleIdleProbe();
            });
        });}catch(RejectedExecutionException error){idleChecking=false;frame.recycle();scheduleIdleProbe();}
    }
    private final TouchCaptureSession touchCapture = new TouchCaptureSession();

    // ---- PVP mode -------------------------------------------------------
    // Nothing is captured until the player double-taps the ball in the lobby.
    // A scan then reads the screen until the ban cards are confirmed (or it
    // gives up), and detaches again; the player can also enter them by hand.
    /** The ban cards are on screen for a couple of seconds; two agreeing frames are needed. */
    private static final int PVP_POLL_MS = 400;
    /** How long a scan waits for the cards before giving up. */
    private static final int PVP_SCAN_MS = 90_000;
    /** After the first confirmed list: time left for a longer list and the map line. */
    private static final int PVP_SETTLE_MS = 2500;
    /** How long the bubble with the result stays unfolded, and the room it needs besides the ball and its text. */
    private static final int PVP_RESULT_MS = 1000, PVP_MESSAGE_DP = 44;
    private PvpBanReader pvpReader;
    private final PvpBanText.Vote pvpVote = new PvpBanText.Vote();
    private PvpBanReader.Reading pvpLastReading;
    private long pvpLastReadingAt, pvpDeadline;
    private boolean pvpScanning, pvpReading, pvpFound;
    private java.util.List<String> pvpBans;
    private String pvpLastRaw;
    /**
     * Debug builds only: read a still frame through the same regions and
     * matcher and log the outcome, so recognition can be checked against
     * saved frames without touching what is on screen.
     *   adb shell am broadcast -a com.crypticnotes.mobile.PVP_TEST -p <package> --es path <file in the app's files dir>
     */
    private BroadcastReceiver pvpTestReceiver;
    private void registerPvpTest() {
        if (!BuildConfig.DEBUG || pvpTestReceiver != null) return;
        pvpTestReceiver = new BroadcastReceiver() { @Override public void onReceive(Context context, Intent intent) {
            final String path = intent.getStringExtra("path");
            if (intent.hasExtra("picker")) {
                // Shows one stage of the overlay for a made-up lobby, to look at it without playing a match:
                // "strip" the read bans awaiting the tick, "demo" a server answer with made-up chances,
                // "rates" the default list (bundled pick rates of the chosen rank), anything else the real request.
                final String stage = intent.getStringExtra("picker");
                main.post(() -> {
                    pvpBans = java.util.Arrays.asList("祭司", "小说家", "“逃脱大师”"); pvpMap = "里奥的回忆";
                    pvpAsked = null; pvpPrediction = null; pvpRequest++;
                    closePvpPicker(); closePvpEntry(); closePvpBars();
                    pvpAwaiting = "strip".equals(stage);
                    if ("strip".equals(stage)) { showPvpHud(); return; }
                    if (!"demo".equals(stage) && !"rates".equals(stage)) { requestPvpPrediction(); return; }
                    try {
                        String[] hunters = PvpRoster.get(CaptureService.this).hunters;
                        PvpClient.Prediction sample = new PvpClient.Prediction();
                        if ("rates".equals(stage)) {
                            // The bundled default list for the chosen rank, as shown when the server says nothing.
                            String chosen = getSharedPreferences("mobile", 0).getString("pvp_rank", "");
                            java.util.Map<String, Double> table = PvpRoster.get(CaptureService.this).pickRates(chosen.isEmpty() ? null : chosen);
                            sample.hunters = PvpRanking.order(hunters, new java.util.ArrayList<>(table.keySet()), new java.util.ArrayList<>(table.values()));
                            sample.defaults = true; sample.offline = "出场率";
                        } else sample.hunters = PvpRanking.order(hunters,
                                java.util.Arrays.asList("红夫人", "宿伞之魂", "歌剧演员", "隐士", "守夜人", "“使徒”", "红蝶", "蜡像师", "“杰克”", "破轮", "雕刻家", "渔女"),
                                java.util.Arrays.asList(.214, .163, .121, .094, .077, .061, .048, .039, .031, .022, .012, .004));
                        pvpAsked = new Object[]{getSharedPreferences("mobile", 0).getString("pvp_rank", ""), pvpMap, pvpBans, 1.0};
                        pvpPrediction = sample;
                        showPvpHud(); showPvpBars(false);
                    } catch (Exception error) { android.util.Log.w("CrypticNotes", "PVP overlay demo failed", error); }
                });
                return;
            }
            inspect.execute(() -> {
                try {
                    Bitmap frame = BitmapFactory.decodeFile(new File(getFilesDir(), path).getPath());
                    if (frame == null) throw new IOException("cannot decode " + path);
                    int w = frame.getWidth(), h = frame.getHeight();
                    int[] banBox = PvpBanText.banRegion(w, h), mapBox = PvpBanText.mapRegion(w, h), lineBox = PvpBanText.gotoRegion(w, h);
                    byte[] ban = pvpBytes(frame, banBox), map = pvpBytes(frame, mapBox), line = pvpBytes(frame, lineBox);
                    boolean cards = PvpBanText.hasPaleLabel(ban), written = PvpBanText.hasWriting(line);
                    frame.recycle();
                    long started = SystemClock.elapsedRealtime();
                    if (pvpReader == null) pvpReader = new PvpBanReader(CaptureService.this);
                    PvpBanReader.Reading reading = pvpReader.read(cards ? ban : null, banBox[2] - banBox[0], banBox[3] - banBox[1], cards ? map : null, mapBox[2] - mapBox[0], mapBox[3] - mapBox[1],
                            written ? line : null, lineBox[2] - lineBox[0], lineBox[3] - lineBox[1]);
                    android.util.Log.i("CrypticNotes", "PVP test " + path + " " + w + "x" + h + ": pale=" + cards + ", line=" + written
                            + ", bans=" + reading.bans + ", map=" + reading.map + ", scores=" + reading.raw + ", ms=" + (SystemClock.elapsedRealtime() - started));
                } catch (Exception error) { android.util.Log.w("CrypticNotes", "PVP test failed: " + path, error); }
            });
        } };
        IntentFilter filter = new IntentFilter("com.crypticnotes.mobile.PVP_TEST");
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(pvpTestReceiver, filter, Context.RECEIVER_EXPORTED);
        else registerReceiver(pvpTestReceiver, filter);
    }
    private static byte[] pvpBytes(Bitmap frame, int[] box) {
        Bitmap region = Bitmap.createBitmap(frame, box[0], box[1], box[2] - box[0], box[3] - box[1]);
        ByteBuffer bytes = ByteBuffer.allocate(region.getWidth() * region.getHeight() * 4);
        region.copyPixelsToBuffer(bytes);
        region.recycle();
        return bytes.array();
    }
    private String pvpMap;
    private final Runnable pvpPoll = new Runnable() { public void run() {
        if (destroyed || !pvpScanning) return;
        if (SystemClock.elapsedRealtime() > pvpDeadline) {
            stopPvpScan(pvpFound ? null : "未识别到");
            return;
        }
        try { pvpTick(); }
        catch (Exception error) { android.util.Log.w("CrypticNotes", "PVP read failed", error); }
        main.postDelayed(this, PVP_POLL_MS);
    } };
    /** Double-tap on the ball: start a scan, or cancel the one running. */
    private void togglePvpScan() {
        badgeText = "";
        if (pvpScanning) { stopPvpScan("已停止"); return; }
        if (projection == null) { setStatus(S_FAILED, "屏幕共享已结束，请回到应用重新开启"); return; }
        if (quickSettings != null) closeQuickSettings();
        pvpVote.reset(); pvpBans = null; pvpMap = null; pvpFound = false; pvpLastReading = null; pvpAwaiting = false;
        // The hunter of the lobby before, never answered: ask again now, while reading the new one.
        final boolean owed = pvpAsked != null && pvpPrediction != null;
        if (!owed) { pvpAsked = null; pvpPrediction = null; pvpRequest++; pvpBarsForced = false; closePvpPicker(); closePvpBars(); }
        pvpReadBans = null; pvpReadMap = null;
        closePvpEntry();
        pvpScanning = true; pvpDeadline = SystemClock.elapsedRealtime() + PVP_SCAN_MS;
        updateCaptureOutput();
        showPvpHud();
        if (owed) {
            pvpHudFolded = false; pvpBarsForced = true; showPvpBars(true);
            // Said in the bubble, then back to the turning emblem of a read in progress.
            setStatus(S_IDLE, "请选择上局的监管者"); state = S_MATCHING;
        } else setStatus(S_MATCHING, "识别中…");
        main.removeCallbacks(pvpPoll); main.postDelayed(pvpPoll, 150);
        android.util.Log.i("CrypticNotes", "PVP scan started");
    }
    private void stopPvpScan(String message) {
        boolean found = pvpFound;
        pvpScanning = false; pvpReading = false; pvpLastReading = null;
        main.removeCallbacks(pvpPoll);
        updateCaptureOutput();
        // With a result the bubble already says it; only stop the emblem turning.
        if (message == null) { state = found ? S_MATCHED : S_IDLE; setSpinning(false); }
        else { badgeText = ""; setStatus(S_IDLE, message); }
        // What was read now waits at the top left for the player's tick; nothing is sent before that.
        // A by-hand window still open from during the read is overtaken by the read succeeding.
        if (found) closePvpEntry();
        showPvpHud();
        android.util.Log.i("CrypticNotes", "PVP scan stopped: found=" + found);
    }
    /** The green tick: these bans and this map are right, ask for the hunters. */
    private void confirmPvp() {
        if (pvpBans == null) return;
        if (pvpScanning) stopPvpScan(null);
        requestPvpPrediction();
    }
    /** The red cross: drop the lobby being confirmed and go back to waiting for a double tap. */
    private void resetPvp() {
        if (pvpScanning) { pvpFound = false; stopPvpScan(null); }
        pvpBans = null; pvpMap = null; pvpAwaiting = false;
        pvpReadBans = null; pvpReadMap = null;
        closePvpEntry(); closePvpHud();
        state = S_IDLE; setSpinning(false);
        main.removeCallbacks(hideBadgeMessage); main.post(hideBadgeMessage);
    }
    private void pvpTick() {
        if (pvpReading || gameOnly || projection == null || reader == null || !capturedVisible || width <= height
                || quickSettings != null || calibration != null) return;
        final int[] banBox = PvpBanText.banRegion(width, height), mapBox = PvpBanText.mapRegion(width, height), lineBox = PvpBanText.gotoRegion(width, height);
        final byte[] ban, map, line;
        if (recorder != null) recorder.requestPreview();
        try (Image image = reader.acquireLatestImage()) {
            if (image == null) {
                // An unchanged screen still shows what the last frame showed.
                if (pvpLastReading != null && SystemClock.elapsedRealtime() - pvpLastReadingAt < 1500) pvpFeed(pvpLastReading);
                return;
            }
            Image.Plane plane = image.getPlanes()[0];
            if (plane.getPixelStride() != 4 || image.getWidth() < banBox[2] || image.getHeight() < mapBox[3]) return;
            ban = pvpRegion(plane, banBox); map = pvpRegion(plane, mapBox); line = pvpRegion(plane, lineBox);
        }
        // The cards are up for two seconds; the map is also written at the top left well before them.
        final boolean cards = PvpBanText.hasPaleLabel(ban), written = PvpBanText.hasWriting(line);
        if (!cards && !written) { pvpLastReading = null; return; }
        pvpReading = true;
        inspect.execute(() -> {
            PvpBanReader.Reading reading = null;
            try {
                if (pvpReader == null) pvpReader = new PvpBanReader(this);
                reading = pvpReader.read(cards ? ban : null, banBox[2] - banBox[0], banBox[3] - banBox[1], cards ? map : null, mapBox[2] - mapBox[0], mapBox[3] - mapBox[1],
                        written ? line : null, lineBox[2] - lineBox[0], lineBox[3] - lineBox[1]);
            } catch (Exception error) {
                android.util.Log.w("CrypticNotes", "PVP name matching failed", error);
            }
            final PvpBanReader.Reading result = reading;
            main.post(() -> {
                pvpReading = false;
                if (destroyed || !pvpScanning || result == null) return;
                pvpLastReading = result; pvpLastReadingAt = SystemClock.elapsedRealtime();
                if (!result.raw.equals(pvpLastRaw)) { pvpLastRaw = result.raw; android.util.Log.i("CrypticNotes", "PVP frame: " + result.raw); }
                pvpFeed(result);
            });
        });
    }
    /** Copies one screen region out of the capture buffer as tight RGBA rows. */
    private static byte[] pvpRegion(Image.Plane plane, int[] box) {
        int w = box[2] - box[0], h = box[3] - box[1], stride = plane.getRowStride();
        ByteBuffer source = plane.getBuffer().duplicate();
        byte[] packed = new byte[w * h * 4];
        for (int y = 0; y < h; y++) { source.position((box[1] + y) * stride + box[0] * 4); source.get(packed, y * w * 4, w * 4); }
        return packed;
    }
    private void pvpFeed(PvpBanReader.Reading reading) {
        long now = SystemClock.elapsedRealtime();
        java.util.List<String> confirmed = pvpVote.feed(reading.bans, reading.map, now);
        boolean changed = confirmed != null || (pvpBans != null && pvpVote.map() != null && !pvpVote.map().equals(pvpMap));
        if (confirmed != null) {
            pvpBans = confirmed;
            // Found: stop soon, but leave a moment for cards still sliding in and for the map line.
            pvpFound = true; pvpAwaiting = true; pvpDeadline = now + PVP_SETTLE_MS;
        }
        if (!changed) return;
        pvpMap = pvpVote.map();
        pvpReadBans = new java.util.ArrayList<>(pvpBans); pvpReadMap = pvpMap;
        publishPvp(pvpBans, pvpMap, "识别");
        showPvpHud();
    }
    /** One place for a result, read or typed: remember it and unfold the ball's bubble with it. */
    private void publishPvp(java.util.List<String> bans, String map, String source) {
        StringBuilder text = new StringBuilder("ban位是：");
        for (int i = 0; i < bans.size(); i++) text.append(i == 0 ? "" : " ").append(PvpBanText.plain(bans.get(i)));
        if (bans.isEmpty()) text.append("留空");
        text.append("  地图是：").append(map == null ? "留空" : map);
        android.util.Log.i("CrypticNotes", "PVP bans (" + source + "): " + text);
        getSharedPreferences("mobile", 0).edit().putString("pvp_last", text.toString()).apply();
        badgeText = "";
        // The portraits at the top left carry the detail; the ball only says it worked.
        setStatus(S_MATCHED, "手动".equals(source) ? "已录入" : "识别成功");
        main.removeCallbacks(hideBadgeMessage);
        main.postDelayed(hideBadgeMessage, PVP_RESULT_MS);
    }
    /** A tap-to-select name; overlay windows take no keyboard, so entry is by picking. */
    private TextView pvpChip(String name, boolean selected) {
        TextView chip = new TextView(this);
        chip.setText(PvpBanText.plain(name)); chip.setTag(name);
        chip.setGravity(Gravity.CENTER); chip.setSingleLine(true);
        chip.setTextSize(android.util.TypedValue.COMPLEX_UNIT_DIP, 12);
        chip.setSelected(selected); paintPvpChip(chip);
        return chip;
    }
    private void paintPvpChip(TextView chip) {
        android.graphics.drawable.GradientDrawable plate = new android.graphics.drawable.GradientDrawable();
        plate.setCornerRadius(Theme.px(this, 6));
        if (chip.isSelected()) plate.setColor(0xffd5dbe2); else plate.setStroke(Theme.px(this, 1), 0x66ffffff);
        chip.setBackground(plate); chip.setTextColor(chip.isSelected() ? Theme.INK : Theme.TEXT);
    }
    /** Lays chips out in rows; `single` makes the group behave like radio buttons. */
    private java.util.List<TextView> pvpChipGrid(LinearLayout panel, String[] names, java.util.Collection<String> selected, int columns, boolean single, Runnable changed) {
        java.util.List<TextView> chips = new java.util.ArrayList<>();
        LinearLayout row = null;
        for (int i = 0; i < names.length; i++) {
            if (i % columns == 0) { row = new LinearLayout(this); panel.addView(row, new LinearLayout.LayoutParams(-1, Theme.px(this, 40))); }
            TextView chip = pvpChip(names[i], selected.contains(names[i]));
            LinearLayout.LayoutParams cell = new LinearLayout.LayoutParams(0, -1, 1);
            int gap = Theme.px(this, 2); cell.setMargins(gap, gap, gap, gap);
            row.addView(chip, cell); chips.add(chip);
            pvpTap(chip, () -> {
                boolean on = !chip.isSelected();
                if (single && on) for (TextView other : chips) if (other.isSelected()) { other.setSelected(false); paintPvpChip(other); }
                chip.setSelected(on); paintPvpChip(chip);
                if (changed != null) changed.run();
            });
        }
        for (int i = names.length; i % columns != 0; i++) row.addView(new View(this), new LinearLayout.LayoutParams(0, -1, 1));
        return chips;
    }
    private void buildPvpPanel(LinearLayout panel, SharedPreferences prefs) {
        panel.removeAllViews();
        panel.addView(label(prefs.getString("pvp_last", "还没有记录禁用角色"), 15, Theme.TEXT, 8));
        Theme.ChalkButton scan = button(pvpScanning ? "停止识别" : "识别禁用角色（也可双击悬浮球）", true);
        panel.addView(scan);
        scan.setOnClickListener(v -> { closeQuickSettings(); togglePvpScan(); });
        Theme.ChalkButton manual = button("手动选择禁用角色和地图", true);
        panel.addView(manual);
        manual.setOnClickListener(v -> { closeQuickSettings(); showPvpEntry(); });
        final PvpRoster roster;
        try { roster = PvpRoster.get(this); }
        catch (Exception error) { panel.addView(label("角色名单读取失败", 13, Theme.MUTED, 8)); return; }
        panel.addView(label("我的段位", 13, Theme.MUTED, 12));
        final java.util.List<TextView> ranks = new java.util.ArrayList<>();
        ranks.addAll(pvpChipGrid(panel, roster.ranks, java.util.Collections.singletonList(prefs.getString("pvp_rank", "")), 4, true, () -> {
            String chosen = "";
            for (TextView chip : ranks) if (chip.isSelected()) chosen = (String) chip.getTag();
            prefs.edit().putString("pvp_rank", chosen).apply();
        }));
    }

    // ---- PVP: what floats over the game --------------------------------
    // One small window at the top left, above the game's own ban cards, whose
    // content follows the flow: a "by hand" button while scanning, then the
    // banned portraits with a tick and a cross, then the hunters as meters.
    // Pictures instead of captions wherever a picture can carry it.
    private View pvpHud, pvpEntry;
    /** The small triangle: the player folded the hunter list away. */
    private boolean pvpHudFolded;
    /** What the screen gave, to tell afterwards whether the player changed it; null when nothing was read. */
    private java.util.List<String> pvpReadBans;
    private String pvpReadMap;
    /** True from the moment bans are read until the player ticks or crosses them. */
    private boolean pvpAwaiting;
    private static final int PVP_ROWS = 5;
    private void closePvpHud() { if (pvpHud != null) { windows.removeView(pvpHud); pvpHud = null; } }
    private void closePvpEntry() { if (pvpEntry != null) { windows.removeView(pvpEntry); pvpEntry = null; } }
    private android.graphics.drawable.GradientDrawable pvpPlate(int fill, int stroke, float radiusDp) {
        android.graphics.drawable.GradientDrawable plate = new android.graphics.drawable.GradientDrawable();
        plate.setCornerRadius(Theme.px(this, radiusDp));
        if (fill != 0) plate.setColor(fill);
        if (stroke != 0) plate.setStroke(Math.max(2, Theme.px(this, 1.5f)), stroke);
        return plate;
    }
    private void showPvpHud() {
        closePvpHud();
        // While the screen is still being read nothing sits on the game's ban cards;
        // the portraits come once the read has settled. (Picking by hand: tap the ball.)
        if (destroyed || !pvp || pvpScanning || !pvpAwaiting || pvpBans == null) return;
        View content;
        try { content = pvpBanStrip(); }
        catch (Exception error) { android.util.Log.w("CrypticNotes", "PVP overlay failed", error); return; }
        WindowManager.LayoutParams p = params(-2, -2, true);
        p.x = Theme.px(this, 28); p.y = Theme.px(this, 4);
        pvpHud = content;
        windows.addView(content, p);
    }
    // The hunter list is a window of its own: it belongs to the lobby already
    // confirmed, and stays up - owed an answer - while the next lobby is read.
    private View pvpBars;
    private WindowManager.LayoutParams pvpBarsParams;
    /** The list was put aside once and is being asked again: it can no longer be folded. */
    private boolean pvpBarsForced;
    /** The player asked to close down while an answer was owed: close once it is given or given up. */
    private boolean pvpStopAfterAnswer;
    private void closePvpBars() {
        if (pvpBars != null) { windows.removeView(pvpBars); pvpBars = null; }
    }
    /** The player closed the list without answering: that lobby is not reported. A read in progress goes on. */
    private void abandonPvpAnswer() {
        pvpAsked = null; pvpPrediction = null; pvpRequest++; pvpBarsForced = false;
        closePvpPicker(); closePvpBars();
        if (pvpStopAfterAnswer) { pvpStopAfterAnswer = false; stopRecognition(); }
    }
    /** The hunter list hangs this far below the top edge of the screen. */
    private static final int PVP_BARS_TOP_DP = 4;
    private void movePvpBars(int dx, int dy) {
        if (pvpBars == null) return;
        WindowManager.LayoutParams p = pvpBarsParams;
        p.x = Math.max(0, Math.min(width - pvpBars.getWidth(), p.x + dx));
        // It lives on the top edge, folded or open: a drag slides it along, never down.
        windows.updateViewLayout(pvpBars, p);
        getSharedPreferences("mobile", 0).edit().putFloat("pvp_bars_x", p.x / (float) width).apply();
    }
    /**
     * Shows the hunter list on the top edge, as far along it as the player
     * left it (by default beside the match timer, left of centre), folded or
     * not. `clearOfRead`: a read
     * is running, so the list starts to the right of the game's ban cards
     * rather than on them; the player may still drag it anywhere.
     */
    private void showPvpBars(boolean clearOfRead) {
        closePvpBars();
        if (destroyed || !pvp || pvpAsked == null || pvpPrediction == null) return;
        View content;
        try { content = pvpHunterBars(); }
        catch (Exception error) { android.util.Log.w("CrypticNotes", "PVP overlay failed", error); return; }
        SharedPreferences prefs = getSharedPreferences("mobile", 0);
        WindowManager.LayoutParams p = params(-2, -2, true);
        p.x = Math.round(prefs.getFloat("pvp_bars_x", .26f) * width); p.y = Theme.px(this, PVP_BARS_TOP_DP);
        int room = Theme.px(this, 250);
        if (clearOfRead) {
            int[] cards = PvpBanText.banRegion(width, height);
            if (p.x < cards[2] && p.x + room > cards[0] && p.y < cards[3]) p.x = cards[2] + Theme.px(this, 6);
        }
        p.x = Math.max(0, Math.min(width - room, p.x)); pvpBars = content; pvpBarsParams = p;
        windows.addView(content, p);
    }
    /** Pressed views dim, so a tap is seen to land; the click itself also ticks. */
    private void pvpTap(final View view, final Runnable action) {
        view.setClickable(true);
        view.setOnTouchListener((v, event) -> {
            int what = event.getActionMasked();
            if (what == MotionEvent.ACTION_DOWN) v.setAlpha(.55f);
            else if (what == MotionEvent.ACTION_UP || what == MotionEvent.ACTION_CANCEL) v.setAlpha(1f);
            return false;
        });
        // These two tick by themselves when clicked.
        view.setOnClickListener(v -> { if (!(v instanceof HeaderClose) && !(v instanceof PvpGlyph)) TouchFeedback.click(v); action.run(); });
    }
    /**
     * What was read: one portrait per ban slot of this rank (unused slots stay
     * empty frames), the map centred under them. Each portrait, and the map,
     * is tapped on its own to correct just that one. Tick to go on, cross to
     * drop it.
     */
    private View pvpBanStrip() throws Exception {
        PvpRoster roster = PvpRoster.get(this);
        LinearLayout strip = new LinearLayout(this); strip.setGravity(Gravity.CENTER_VERTICAL);
        strip.setBackground(pvpPlate(0xb3101a24, 0, 10));
        int inner = Theme.px(this, 5); strip.setPadding(inner, inner, inner, inner);
        LinearLayout read = new LinearLayout(this); read.setOrientation(LinearLayout.VERTICAL); read.setGravity(Gravity.CENTER_HORIZONTAL);
        LinearLayout faces = new LinearLayout(this); faces.setGravity(Gravity.CENTER_VERTICAL);
        String rank = getSharedPreferences("mobile", 0).getString("pvp_rank", "");
        int slots = Math.max(roster.banLimit(rank.isEmpty() ? null : rank), pvpBans.size()), size = Theme.px(this, 72);
        for (int i = 0; i < slots; i++) {
            final int at = i;
            LinearLayout.LayoutParams slot = new LinearLayout.LayoutParams(size, size);
            if (i > 0) slot.leftMargin = Theme.px(this, 4);
            String ban = i < pvpBans.size() ? pvpBans.get(i) : null;
            Bitmap face = ban == null ? null : roster.portrait(ban);
            View view;
            if (face != null) {
                ImageView portrait = new ImageView(this); portrait.setImageBitmap(face);
                view = portrait;
            } else {
                // An unused slot is an empty frame; a name without a bundled portrait is written in one.
                TextView frame = label(ban == null ? "" : PvpBanText.plain(ban), 12, Theme.TEXT, 0);
                frame.setGravity(Gravity.CENTER); frame.setBackground(pvpPlate(0x14ffffff, 0x55ffffff, 8));
                view = frame;
            }
            view.setContentDescription((ban == null ? "空的禁用位" : PvpBanText.plain(ban)) + "，点击修改");
            pvpTap(view, () -> showPvpSlot(at));
            faces.addView(view, slot);
        }
        read.addView(faces, new LinearLayout.LayoutParams(-2, -2));
        TextView map = label(pvpMap == null ? "—" : pvpMap, 13, pvpMap == null ? Theme.MUTED : Theme.TITLE, 0);
        map.setSingleLine(true); map.setGravity(Gravity.CENTER); map.setMinWidth(size); map.setMinHeight(Theme.px(this, 24));
        map.setContentDescription("地图 " + (pvpMap == null ? "留空" : pvpMap) + "，点击修改");
        pvpTap(map, () -> showPvpSlot(-1));
        read.addView(map, new LinearLayout.LayoutParams(-1, -2));
        strip.addView(read, new LinearLayout.LayoutParams(-2, -2));
        // Side by side along the bottom, not stacked: some phones' game modes swallow taps
        // in a band along the top edge of the screen, and a tick up there could not be pressed.
        LinearLayout verdict = new LinearLayout(this);
        PvpGlyph yes = new PvpGlyph(this, PvpGlyph.CHECK, "确认禁用角色和地图"), no = new PvpGlyph(this, PvpGlyph.CROSS, "取消");
        int button = Theme.px(this, 44);
        LinearLayout.LayoutParams second = new LinearLayout.LayoutParams(button, button); second.leftMargin = Theme.px(this, 6);
        verdict.addView(yes, new LinearLayout.LayoutParams(button, button)); verdict.addView(no, second);
        LinearLayout.LayoutParams aside = new LinearLayout.LayoutParams(-2, -2); aside.leftMargin = Theme.px(this, 8); aside.gravity = Gravity.BOTTOM;
        strip.addView(verdict, aside);
        pvpTap(yes, this::confirmPvp);
        pvpTap(no, this::resetPvp);
        return strip;
    }
    /**
     * Corrects one thing on the strip: ban slot `slot`, or the map when it is
     * negative. One tap picks and closes; "left blank" empties just that slot.
     */
    private void showPvpSlot(final int slot) {
        if (destroyed || pvpBans == null) return;
        closePvpEntry();
        final PvpRoster roster;
        try { roster = PvpRoster.get(this); } catch (Exception error) { return; }
        final String blank = "留空";
        final boolean forMap = slot < 0;
        int pad = Theme.px(this, 12);
        final Theme.MistPanel shell = new Theme.MistPanel(this);
        shell.setPadding(0, 0, 0, 0);
        DraggableHeader header = new DraggableHeader(this);
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(pad, 0, pad, 0);
        header.addView(label(forMap ? "地图" : "禁用角色", 15, Theme.TITLE, 0), new LinearLayout.LayoutParams(0, -2, 1));
        HeaderClose dismiss = new HeaderClose(this);
        header.addView(dismiss, new LinearLayout.LayoutParams(Theme.px(this, 40), Theme.px(this, 40)));
        shell.addView(header, new LinearLayout.LayoutParams(-1, Theme.px(this, 44)));
        dismiss.setOnClickListener(v -> closePvpEntry());
        LinearLayout body = new LinearLayout(this); body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(pad, 0, pad, pad);
        if (forMap) {
            String[] mapNames = new String[roster.maps.length + 1];
            mapNames[0] = blank; System.arraycopy(roster.maps, 0, mapNames, 1, roster.maps.length);
            final java.util.List<TextView> chips = new java.util.ArrayList<>();
            chips.addAll(pvpChipGrid(body, mapNames, java.util.Collections.singletonList(pvpMap == null ? blank : pvpMap), 5, true, () -> {
                String map = null;
                for (TextView chip : chips) if (chip.isSelected() && !blank.equals(chip.getTag())) map = (String) chip.getTag();
                pvpMap = map;
                closePvpEntry(); showPvpHud();
            }));
        } else {
            final String current = slot < pvpBans.size() ? pvpBans.get(slot) : null;
            final int columns = 8;
            LinearLayout row = null;
            // Cell 0 is "left blank"; the survivors follow.
            for (int i = 0; i <= roster.survivors.length; i++) {
                final String survivor = i == 0 ? null : roster.survivors[i - 1];
                if (i % columns == 0) { row = new LinearLayout(this); body.addView(row, new LinearLayout.LayoutParams(-1, -2)); }
                LinearLayout cell = new LinearLayout(this); cell.setOrientation(LinearLayout.VERTICAL); cell.setGravity(Gravity.CENTER_HORIZONTAL);
                int inner = Theme.px(this, 4); cell.setPadding(inner, inner, inner, inner);
                int size = Theme.px(this, 42);
                Bitmap face = survivor == null ? null : roster.portrait(survivor);
                if (face != null) {
                    ImageView portrait = new ImageView(this); portrait.setImageBitmap(face);
                    cell.addView(portrait, new LinearLayout.LayoutParams(size, size));
                } else {
                    View frame = new View(this); frame.setBackground(pvpPlate(0x14ffffff, 0x55ffffff, 8));
                    cell.addView(frame, new LinearLayout.LayoutParams(size, size));
                }
                TextView name = label(survivor == null ? blank : PvpBanText.plain(survivor), 10, Theme.TEXT, 0);
                name.setGravity(Gravity.CENTER); name.setSingleLine(true); name.setEllipsize(android.text.TextUtils.TruncateAt.END);
                cell.addView(name, new LinearLayout.LayoutParams(-1, -2));
                cell.setContentDescription(survivor == null ? blank : PvpBanText.plain(survivor));
                row.addView(cell, new LinearLayout.LayoutParams(0, -2, 1));
                pvpMark(cell, survivor == null ? current == null : survivor.equals(current));
                // A survivor already in another slot cannot be banned twice.
                if (survivor != null && !survivor.equals(current) && pvpBans.contains(survivor)) { cell.setAlpha(.3f); continue; }
                pvpTap(cell, () -> {
                    java.util.List<String> bans = new java.util.ArrayList<>(pvpBans);
                    if (survivor == null) { if (slot < bans.size()) bans.remove(slot); }
                    else if (slot < bans.size()) bans.set(slot, survivor);
                    else bans.add(survivor);
                    pvpBans = bans;
                    closePvpEntry(); showPvpHud();
                });
            }
            for (int i = roster.survivors.length + 1; i % columns != 0; i++) row.addView(new View(this), new LinearLayout.LayoutParams(0, 1, 1));
        }
        ScrollView scroll = new ScrollView(this);
        scroll.addView(body, new ScrollView.LayoutParams(-1, -2));
        shell.addView(scroll, new LinearLayout.LayoutParams(-1, forMap ? -2 : 0, forMap ? 0 : 1));
        final WindowManager.LayoutParams p = params(Math.min(width - pad * 2, Theme.px(this, 520)), forMap ? -2 : Math.min(height - pad * 2, Theme.px(this, 330)), true);
        final int tall = forMap ? Theme.px(this, 150) : p.height;
        p.x = (width - p.width) / 2; p.y = (height - tall) / 2;
        header.mover = (dx, dy) -> { p.x = Math.max(0, Math.min(width - p.width, p.x + dx)); p.y = Math.max(0, Math.min(height - tall, p.y + dy)); windows.updateViewLayout(shell, p); };
        pvpEntry = shell;
        windows.addView(shell, p);
        shell.setAlpha(0f);
        shell.animate().alpha(1f).setDuration(150).start();
    }
    /**
     * The hunters as meters, most likely first: the five the server thinks
     * most likely, or - when the server says nothing usable - every hunter's
     * pick rate at the player's rank. Tapping a row frames it and turns the button into
     * "confirm"; with nothing framed the button opens the full picker.
     *
     * Answering is what the list is for, so putting it aside is the easy
     * gesture and dropping it the deliberate one: the gold triangle on the
     * bottom edge folds it to a short plain bar, while the cross is small,
     * quiet, and only there when the list is open. Asked a second time
     * (pvpBarsForced) there is no folding: answer, or give it up.
     * The top edge and the folded bar drag the window.
     */
    private View pvpHunterBars() throws Exception {
        PvpRoster roster = PvpRoster.get(this);
        final PvpClient.Prediction prediction = pvpPrediction;
        java.util.List<PvpRanking.Guess> rows = PvpRanking.leading(prediction.hunters, prediction.defaults ? 0 : PVP_ROWS);
        // Asked a second time (a new read, or closing down): answer or give it up, no putting it aside again.
        final boolean forced = pvpBarsForced;
        final LinearLayout box = new LinearLayout(this); box.setOrientation(LinearLayout.VERTICAL); box.setGravity(Gravity.CENTER_HORIZONTAL);
        box.setBackground(pvpPlate(0xb3101a24, 0, 10));
        final int inner = Theme.px(this, 5), wide = Theme.px(this, 236);
        // Folded: half as long, and thinner.
        final int[] openBar = {wide, Theme.px(this, 30)}, foldedBar = {wide / 2, Theme.px(this, 18)};
        final LinearLayout open = new LinearLayout(this); open.setOrientation(LinearLayout.VERTICAL);
        final Theme.ChalkButton action = button("手动选择", true);
        final View[] chosen = new View[1];
        DraggableHeader top = new DraggableHeader(this); top.setGravity(Gravity.CENTER_VERTICAL);
        top.mover = this::movePvpBars;
        TextView caption = label(prediction.defaults ? "出场率" : "本局监管者", 10, Theme.MUTED, 0);
        caption.setPadding(Theme.px(this, 4), 0, 0, 0);
        top.addView(caption, new LinearLayout.LayoutParams(0, -2, 1));
        // The cross sits at the bottom beside the button, clear of the top edge (see pvpBanStrip)
        // and of this header, where a finger that slides a little starts a drag instead of a tap.
        PvpGlyph close = new PvpGlyph(this, PvpGlyph.CLOSE, "放弃提交");
        pvpTap(close, this::abandonPvpAnswer);
        open.addView(top, new LinearLayout.LayoutParams(wide, Theme.px(this, 24)));
        LinearLayout lines = new LinearLayout(this); lines.setOrientation(LinearLayout.VERTICAL);
        // Drawn against the leader, so a handful of small numbers still differ.
        double full = rows.isEmpty() ? 1 : rows.get(0).probability;
        int rowHeight = Theme.px(this, 40);
        for (final PvpRanking.Guess guess : rows) {
            final LinearLayout row = new LinearLayout(this); row.setGravity(Gravity.CENTER_VERTICAL);
            row.setPadding(Theme.px(this, 4), 0, Theme.px(this, 6), 0);
            ImageView portrait = new ImageView(this);
            Bitmap face = roster.portrait(guess.name);
            if (face != null) portrait.setImageBitmap(face);
            row.addView(portrait, new LinearLayout.LayoutParams(Theme.px(this, 34), Theme.px(this, 34)));
            LinearLayout.LayoutParams meter = new LinearLayout.LayoutParams(0, Theme.px(this, 8), 1);
            meter.leftMargin = Theme.px(this, 8);
            row.addView(new PvpBar(this, (float) (guess.probability / full)), meter);
            TextView share = label(PvpRanking.percent(guess.probability), 13, Theme.TITLE, 0);
            share.setGravity(Gravity.RIGHT); share.setSingleLine(true);
            row.addView(share, new LinearLayout.LayoutParams(Theme.px(this, 42), -2));
            row.setTag(guess.name);
            row.setContentDescription(PvpBanText.plain(guess.name) + " " + PvpRanking.percent(guess.probability));
            pvpTap(row, () -> {
                View before = chosen[0];
                if (before != null) before.setBackground(null);
                chosen[0] = before == row ? null : row;
                if (chosen[0] != null) row.setBackground(pvpPlate(0x26dcb96c, 0xffdcb96c, 6));
                action.setText(chosen[0] == null ? "手动选择" : "确认");
            });
            lines.addView(row, new LinearLayout.LayoutParams(wide, rowHeight));
        }
        if (rows.size() > PVP_ROWS) {
            ScrollView scroll = new ScrollView(this); scroll.setVerticalScrollBarEnabled(false);
            scroll.addView(lines, new ScrollView.LayoutParams(wide, -2));
            open.addView(scroll, new LinearLayout.LayoutParams(wide, rowHeight * PVP_ROWS));
        } else open.addView(lines, new LinearLayout.LayoutParams(wide, -2));
        LinearLayout.LayoutParams below = new LinearLayout.LayoutParams(wide, Theme.px(this, 46));
        below.topMargin = rows.isEmpty() ? 0 : Theme.px(this, 2);
        LinearLayout foot = new LinearLayout(this); foot.setGravity(Gravity.CENTER_VERTICAL);
        foot.addView(action, new LinearLayout.LayoutParams(0, -1, 1));
        foot.addView(close, new LinearLayout.LayoutParams(Theme.px(this, 44), -1));
        open.addView(foot, below);
        action.setOnClickListener(v -> { if (chosen[0] != null) reportPvpHunter((String) chosen[0].getTag()); else showPvpPicker(); });
        box.addView(open, new LinearLayout.LayoutParams(wide, -2));
        final PvpGlyph fold = new PvpGlyph(this, PvpGlyph.UP, "收起或展开");
        if (!forced) box.addView(fold, new LinearLayout.LayoutParams(openBar[0], openBar[1]));
        final Runnable dress = () -> {
            boolean folded = pvpHudFolded && !forced;
            fold.kind(folded ? PvpGlyph.DOWN : PvpGlyph.UP);
            // Folded it is a plain small bar, nothing calling for attention; open, the way to fold is the gold one.
            fold.tint(folded ? Theme.TEXT : 0xffdcb96c);
            open.setVisibility(folded ? View.GONE : View.VISIBLE);
            box.setPadding(folded ? 0 : inner, folded ? 0 : inner, folded ? 0 : inner, forced ? inner : 0);
            int[] bar = folded ? foldedBar : openBar;
            fold.setLayoutParams(new LinearLayout.LayoutParams(bar[0], bar[1]));
        };
        dress.run();
        // The bar is both the fold switch (a tap) and a handle (a drag).
        fold.setOnTouchListener(new View.OnTouchListener() {
            private float downX, downY; private int startX; private boolean dragging;
            @Override public boolean onTouch(View v, MotionEvent event) {
                switch (event.getActionMasked()) {
                    case MotionEvent.ACTION_DOWN:
                        downX = event.getRawX(); downY = event.getRawY(); dragging = false;
                        startX = pvpBarsParams == null ? 0 : pvpBarsParams.x;
                        return true;
                    case MotionEvent.ACTION_MOVE:
                        if (!dragging && Math.hypot(event.getRawX() - downX, event.getRawY() - downY) > ViewConfiguration.get(CaptureService.this).getScaledTouchSlop()) dragging = true;
                        // Measured from where the finger went down, so slow drags lose nothing to rounding.
                        if (dragging && pvpBarsParams != null) movePvpBars(startX + Math.round(event.getRawX() - downX) - pvpBarsParams.x, 0);
                        return true;
                    case MotionEvent.ACTION_UP:
                        if (!dragging) { TouchFeedback.click(v); pvpHudFolded = !pvpHudFolded; dress.run(); }
                        return true;
                    default:
                        return true;
                }
            }
        });
        return box;
    }
    private void pvpMark(View cell, boolean on) {
        cell.setSelected(on);
        cell.setBackground(on ? pvpPlate(0x33ffffff, 0xccffffff, 6) : null);
    }
    /**
     * The banned survivors and the map, picked by hand: replaces whatever was
     * read and goes straight on. Both may be left blank - a hunter need not
     * use every slot, and the map line is not always readable.
     */
    private void showPvpEntry() {
        if (destroyed) return;
        closePvpEntry();
        if (quickSettings != null) closeQuickSettings();
        final PvpRoster roster;
        try { roster = PvpRoster.get(this); } catch (Exception error) { return; }
        final String blank = "留空";
        int pad = Theme.px(this, 12);
        final boolean duringRead = pvpScanning;
        int boxW = Math.min(width - pad * 2, Theme.px(this, 520)), boxH = Math.min(height - pad * 2, Theme.px(this, 350));
        int boxX = (width - boxW) / 2, boxY = (height - boxH) / 2;
        if (duringRead) {
            // Right of the ban cards and above the map line, so the read can still succeed behind it.
            int left = Math.round(height * 1.22f), room = width - pad - left, floor = Math.round(height * .78f);
            if (room >= Theme.px(this, 300)) { boxX = left; boxW = room; boxY = pad / 2; boxH = Math.min(boxH, floor - boxY); }
        }
        final Theme.MistPanel shell = new Theme.MistPanel(this);
        shell.setPadding(0, 0, 0, 0);
        DraggableHeader header = new DraggableHeader(this);
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(pad, 0, pad, 0);
        header.addView(label("禁用角色 · 地图", 15, Theme.TITLE, 0), new LinearLayout.LayoutParams(0, -2, 1));
        HeaderClose dismiss = new HeaderClose(this);
        header.addView(dismiss, new LinearLayout.LayoutParams(Theme.px(this, 40), Theme.px(this, 40)));
        shell.addView(header, new LinearLayout.LayoutParams(-1, Theme.px(this, 44)));
        // Opened in place of the read: the cross gives the lobby up, back to waiting.
        dismiss.setOnClickListener(v -> { if (duringRead) resetPvp(); else closePvpEntry(); });

        LinearLayout body = new LinearLayout(this); body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(pad, 0, pad, 0);
        final java.util.List<View> faces = new java.util.ArrayList<>();
        final View[] none = new View[1];
        final int columns = boxW < Theme.px(this, 420) ? 6 : 8, most = roster.mostBans;
        LinearLayout row = null;
        // Cell 0 is "left blank"; the survivors follow.
        for (int i = 0; i <= roster.survivors.length; i++) {
            final String survivor = i == 0 ? null : roster.survivors[i - 1];
            if (i % columns == 0) { row = new LinearLayout(this); body.addView(row, new LinearLayout.LayoutParams(-1, -2)); }
            final LinearLayout cell = new LinearLayout(this); cell.setOrientation(LinearLayout.VERTICAL); cell.setGravity(Gravity.CENTER_HORIZONTAL);
            int inner = Theme.px(this, 4); cell.setPadding(inner, inner, inner, inner);
            int size = Theme.px(this, 42);
            Bitmap face = survivor == null ? null : roster.portrait(survivor);
            if (face != null) {
                ImageView portrait = new ImageView(this); portrait.setImageBitmap(face);
                cell.addView(portrait, new LinearLayout.LayoutParams(size, size));
            } else {
                View frame = new View(this); frame.setBackground(pvpPlate(0x14ffffff, 0x55ffffff, 8));
                cell.addView(frame, new LinearLayout.LayoutParams(size, size));
            }
            TextView name = label(survivor == null ? blank : PvpBanText.plain(survivor), 10, Theme.TEXT, 0);
            name.setGravity(Gravity.CENTER); name.setSingleLine(true); name.setEllipsize(android.text.TextUtils.TruncateAt.END);
            cell.addView(name, new LinearLayout.LayoutParams(-1, -2));
            cell.setContentDescription(survivor == null ? blank : PvpBanText.plain(survivor));
            row.addView(cell, new LinearLayout.LayoutParams(0, -2, 1));
            if (survivor == null) {
                none[0] = cell;
                pvpTap(cell, () -> { for (View other : faces) pvpMark(other, false); pvpMark(cell, true); });
                continue;
            }
            cell.setTag(survivor); faces.add(cell);
            pvpMark(cell, pvpBans != null && pvpBans.contains(survivor));
            pvpTap(cell, () -> {
                int marked = 0;
                for (View other : faces) if (other.isSelected()) marked++;
                if (!cell.isSelected() && marked >= most) { Toast.makeText(this, "最多禁用 " + most + " 名求生者", Toast.LENGTH_SHORT).show(); return; }
                pvpMark(cell, !cell.isSelected());
                marked += cell.isSelected() ? 1 : -1;
                pvpMark(none[0], marked == 0);
            });
        }
        for (int i = roster.survivors.length + 1; i % columns != 0; i++) row.addView(new View(this), new LinearLayout.LayoutParams(0, 1, 1));
        pvpMark(none[0], pvpBans == null || pvpBans.isEmpty());
        body.addView(label("地图", 12, Theme.MUTED, 8));
        String[] mapNames = new String[roster.maps.length + 1];
        mapNames[0] = blank; System.arraycopy(roster.maps, 0, mapNames, 1, roster.maps.length);
        final java.util.List<TextView> maps = pvpChipGrid(body, mapNames, java.util.Collections.singletonList(pvpMap == null ? blank : pvpMap), 5, true, null);
        ScrollView scroll = new ScrollView(this);
        scroll.addView(body, new ScrollView.LayoutParams(-1, -2));
        shell.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        Theme.ChalkButton save = button("确认", true);
        LinearLayout.LayoutParams saveParams = new LinearLayout.LayoutParams(-1, Theme.px(this, 46));
        saveParams.setMargins(pad, Theme.px(this, 8), pad, pad);
        shell.addView(save, saveParams);
        save.setOnClickListener(v -> {
            java.util.List<String> bans = new java.util.ArrayList<>();
            for (View cell : faces) if (cell.isSelected()) bans.add((String) cell.getTag());
            String map = null;
            for (TextView chip : maps) if (chip.isSelected() && !blank.equals(chip.getTag())) map = (String) chip.getTag();
            // What the player picked replaces whatever a running scan had.
            if (pvpScanning) { pvpFound = false; stopPvpScan(null); }
            pvpBans = bans; pvpMap = map;
            closePvpEntry();
            publishPvp(bans, map, "手动");
            requestPvpPrediction();
        });

        final WindowManager.LayoutParams p = params(boxW, boxH, true);
        p.x = boxX; p.y = boxY;
        header.mover = (dx, dy) -> { p.x = Math.max(0, Math.min(width - p.width, p.x + dx)); p.y = Math.max(0, Math.min(height - p.height, p.y + dy)); windows.updateViewLayout(shell, p); };
        pvpEntry = shell;
        windows.addView(shell, p);
        shell.setAlpha(0f);
        shell.animate().alpha(1f).setDuration(150).start();
    }
    /** The player's answer, from a framed row or from the full picker: send it and close this lobby. */
    @SuppressWarnings("unchecked")
    private void reportPvpHunter(final String hunter) {
        if (pvpAsked == null) return;
        final PvpClient.Prediction prediction = pvpPrediction;
        final String rank = (String) pvpAsked[0], map = (String) pvpAsked[1];
        final java.util.List<String> bans = (java.util.List<String>) pvpAsked[2];
        final double recognized = (Double) pvpAsked[3];
        pvpAsked = null; pvpPrediction = null;
        final boolean thenStop = pvpStopAfterAnswer;
        pvpStopAfterAnswer = false; pvpBarsForced = false;
        closePvpPicker(); closePvpBars();
        badgeText = ""; setStatus(S_MATCHED, "已记录");
        if (pvpScanning) state = S_MATCHING;
        compute.execute(() -> {
            try {
                boolean sent = PvpClient.report(this, prediction, rank.isEmpty() ? null : rank, map, bans, recognized, hunter);
                android.util.Log.i("CrypticNotes", "PVP report: " + PvpBanText.plain(hunter) + (sent ? " sent" : " kept for later"));
            } catch (Exception error) { android.util.Log.w("CrypticNotes", "PVP report failed", error); }
            // Closing down waited for this answer; it is on its way (or queued) now.
            if (thenStop) main.post(() -> { if (!destroyed) stopRecognition(); });
        });
    }

    // ---- PVP: ask the server, show the hunters, send back which one it was ----
    /** {rank, map, bans} of the lobby the server was last asked about; null before the first one. */
    private Object[] pvpAsked;
    private PvpClient.Prediction pvpPrediction;
    private int pvpRequest;
    private View pvpPicker;
    @SuppressWarnings("unchecked")
    private void requestPvpPrediction() {
        if (pvpBans == null) return;
        final String rank = getSharedPreferences("mobile", 0).getString("pvp_rank", "");
        final String map = pvpMap;
        final java.util.List<String> bans = new java.util.ArrayList<>(pvpBans);
        final int ticket = ++pvpRequest;
        // How much of this the screen gave, against the ban slots of this rank plus the map.
        int slots = 3;
        try { slots = PvpRoster.get(this).banLimit(rank.isEmpty() ? null : rank); } catch (Exception ignored) {}
        final double recognized = PvpBanText.recognized(pvpReadBans, pvpReadMap, bans, map, slots);
        pvpAsked = new Object[]{rank, map, bans, recognized}; pvpPrediction = null;
        pvpAwaiting = false; pvpBarsForced = false; pvpStopAfterAnswer = false;
        closePvpPicker(); closePvpBars(); showPvpHud();
        compute.execute(() -> {
            PvpClient.Prediction prediction;
            try { prediction = PvpClient.predict(this, rank.isEmpty() ? null : rank, map, bans, recognized); }
            catch (Exception error) { android.util.Log.w("CrypticNotes", "PVP prediction failed", error); return; }
            main.post(() -> {
                if (destroyed || ticket != pvpRequest) return;
                pvpPrediction = prediction;
                android.util.Log.i("CrypticNotes", "PVP prediction: " + (prediction.offline != null ? prediction.offline : "server, first=" + prediction.hunters.get(0).name) + ", recognized=" + recognized);
                showPvpBars(pvpScanning);
            });
        });
    }
    private void closePvpPicker() { if (pvpPicker != null) { windows.removeView(pvpPicker); pvpPicker = null; } }
    /**
     * Every hunter, most likely first, for when the one actually met is not
     * among the meters. Same frame as the in-game panel: a mist panel with a
     * draggable header and a cross that goes back to the meters.
     */
    @SuppressWarnings("unchecked")
    private void showPvpPicker() {
        if (destroyed || pvpPrediction == null || pvpAsked == null) return;
        closePvpPicker();
        if (quickSettings != null) closeQuickSettings();
        final PvpRoster roster;
        try { roster = PvpRoster.get(this); } catch (Exception error) { return; }
        final PvpClient.Prediction prediction = pvpPrediction;
        final String rank = (String) pvpAsked[0], map = (String) pvpAsked[1];
        final java.util.List<String> bans = (java.util.List<String>) pvpAsked[2];
        int pad = Theme.px(this, 14);
        Theme.MistPanel shell = new Theme.MistPanel(this);
        shell.setPadding(0, 0, 0, 0);
        DraggableHeader header = new DraggableHeader(this);
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(pad, 0, pad, 0);
        header.addView(label("本局监管者是谁？", 16, Theme.TITLE, 0), new LinearLayout.LayoutParams(0, -2, 1));
        HeaderClose dismiss = new HeaderClose(this);
        header.addView(dismiss, new LinearLayout.LayoutParams(Theme.px(this, 34), Theme.px(this, 34)));
        shell.addView(header, new LinearLayout.LayoutParams(-1, Theme.px(this, 44)));
        dismiss.setOnClickListener(v -> closePvpPicker());

        StringBuilder about = new StringBuilder(rank.isEmpty() ? "未选段位" : rank);
        if (map != null) about.append(" · ").append(map);
        about.append(" · 禁用");
        for (String ban : bans) about.append(' ').append(PvpBanText.plain(ban));
        if (prediction.offline != null) about.append("\n").append(prediction.offline);
        TextView summary = label(about.toString(), 12, Theme.MUTED, 0);
        summary.setPadding(pad, 0, pad, Theme.px(this, 6));
        shell.addView(summary);

        final int columns = 6;
        LinearLayout grid = new LinearLayout(this); grid.setOrientation(LinearLayout.VERTICAL);
        grid.setPadding(pad - Theme.px(this, 3), 0, pad - Theme.px(this, 3), 0);
        final Theme.ChalkButton confirm = button("先点选一位监管者", true);
        confirm.setEnabled(false); confirm.setAlpha(.5f);
        final View[] chosen = new View[1];
        LinearLayout row = null;
        // Picking by hand: in the order the hunters came out in, where the player expects each one.
        final java.util.List<PvpRanking.Guess> listed = PvpRanking.byRoster(roster.hunters, prediction.hunters);
        for (int i = 0; i < listed.size(); i++) {
            final PvpRanking.Guess guess = listed.get(i);
            if (i % columns == 0) { row = new LinearLayout(this); grid.addView(row, new LinearLayout.LayoutParams(-1, -2)); }
            LinearLayout cell = new LinearLayout(this); cell.setOrientation(LinearLayout.VERTICAL); cell.setGravity(Gravity.CENTER_HORIZONTAL);
            int inner = Theme.px(this, 4); cell.setPadding(inner, inner, inner, inner);
            ImageView portrait = new ImageView(this);
            Bitmap face = roster.portrait(guess.name);
            if (face != null) portrait.setImageBitmap(face);
            cell.addView(portrait, new LinearLayout.LayoutParams(Theme.px(this, 44), Theme.px(this, 44)));
            TextView name = label(PvpBanText.plain(guess.name), 11, Theme.TEXT, 0);
            name.setGravity(Gravity.CENTER); name.setSingleLine(true); name.setEllipsize(android.text.TextUtils.TruncateAt.END);
            cell.addView(name, new LinearLayout.LayoutParams(-1, -2));
            String percent = PvpRanking.percent(guess.probability);
            if (!percent.isEmpty()) {
                TextView chance = label(percent, 10, Theme.MUTED, 0);
                chance.setGravity(Gravity.CENTER);
                cell.addView(chance, new LinearLayout.LayoutParams(-1, -2));
            }
            cell.setTag(guess.name);
            cell.setContentDescription(PvpBanText.plain(guess.name) + (percent.isEmpty() ? "" : " " + percent));
            pvpTap(cell, () -> {
                if (chosen[0] != null) chosen[0].setBackground(null);
                android.graphics.drawable.GradientDrawable mark = new android.graphics.drawable.GradientDrawable();
                mark.setCornerRadius(Theme.px(this, 6)); mark.setColor(0x33ffffff); mark.setStroke(Theme.px(this, 1), 0xccffffff);
                cell.setBackground(mark); chosen[0] = cell;
                confirm.setText("确定：" + PvpBanText.plain(guess.name)); confirm.setEnabled(true); confirm.setAlpha(1f);
            });
            LinearLayout.LayoutParams slot = new LinearLayout.LayoutParams(0, -2, 1);
            row.addView(cell, slot);
        }
        for (int i = prediction.hunters.size(); i % columns != 0; i++) row.addView(new View(this), new LinearLayout.LayoutParams(0, 1, 1));
        ScrollView scroll = new ScrollView(this);
        scroll.addView(grid, new ScrollView.LayoutParams(-1, -2));
        shell.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        LinearLayout.LayoutParams confirmParams = new LinearLayout.LayoutParams(-1, Theme.px(this, 44));
        confirmParams.setMargins(pad, Theme.px(this, 8), pad, pad);
        shell.addView(confirm, confirmParams);
        confirm.setOnClickListener(v -> {
            if (chosen[0] == null) return;
            reportPvpHunter((String) chosen[0].getTag());
        });

        WindowManager.LayoutParams p = params(Math.min(width - pad * 2, Theme.px(this, 430)), Math.min(height - pad * 2, Theme.px(this, 330)), true);
        p.x = (width - p.width) / 2; p.y = (height - p.height) / 2;
        header.mover = (dx, dy) -> { p.x = Math.max(0, Math.min(width - p.width, p.x + dx)); p.y = Math.max(0, Math.min(height - p.height, p.y + dy)); windows.updateViewLayout(shell, p); };
        pvpPicker = shell;
        windows.addView(shell, p);
        shell.setAlpha(0f);
        shell.animate().alpha(1f).setDuration(150).start();
    }

    private boolean recognitionIdle(){return !gameOnly && !pvpScanning && !MiniGameOverlayService.running && !touchCapture.awake();}
    private void updateCaptureOutput(){
        if(display==null || reader==null || recorder!=null || stoppingRecording)return;
        // While idle the low-resolution mirror, once attached, is left alone:
        // every surface change makes SurfaceFlinger rebuild the virtual display
        // and costs the game a frame (see IdleMapProbe).
        if(recognitionIdle()){ if(!idleProbe.attached())display.setSurface(null); }
        else { idleProbe.cancel();display.resize(width,height,density);display.setSurface(reader.getSurface()); }
    }
    private void wakeRecognition(){
        int latestRequest=matchRequests.incrementAndGet();
        android.util.Log.i("CrypticNotes","Latest recognition requested: request="+latestRequest+", busy="+busy+", checking="+checking);
        main.removeCallbacks(idleProbeTick);idleProbeScheduled=false;idleProbe.cancel();
        touchCapture.wake(SystemClock.elapsedRealtime());
        memoryEpoch++;mapPanelOpen=false;
        // Never re-use the last session's image while a fresh frame is pending.
        if(reader!=null)try(Image stale=reader.acquireLatestImage()){}catch(Exception ignored){}
        if(cleanCaptureFrame!=null){cleanCaptureFrame.recycle();cleanCaptureFrame=null;}
        cleanCaptureReader=null;cleanCaptureSignature=null;
        latestViewport.clear();
        reusableGatePixels=null;lastAttemptPixels=null;actualGateAt=0;lastGateAt=0;
        updateCaptureOutput();
        repoll(60);
        android.util.Log.i("CrypticNotes","Touch capture awake");
    }
    private void sleepRecognition(){
        touchCapture.sleep();mapPanelOpen=false;manualRetry=false;forceNextMatch=false;
        if(cleanCaptureFrame!=null){cleanCaptureFrame.recycle();cleanCaptureFrame=null;}
        cleanCaptureReader=null;cleanCaptureSignature=null;latestViewport.clear();
        main.removeCallbacks(poll);pollScheduled=false;
        updateCaptureOutput();setSpinning(false);
        android.util.Log.i("CrypticNotes","Recognition asleep; waiting for low-power map controls probe or manual action");
        scheduleIdleProbe();
    }
    void onTapRelayChanged(){main.post(()->{if(!destroyed)refreshTapRegion();});}
    private boolean pollScheduled = false;
    private final Runnable poll = new Runnable() { public void run() {
        pollScheduled = false;
        try { sample(); }
        catch (Exception error) {
            android.util.Log.e("CrypticNotes", "Capture loop failed", error);
            setStatus(S_FAILED, "采集异常，正在重试");
        } finally {
            // Async callbacks normally choose the next delay. Keep a fallback
            // heartbeat even when an inspection never calls back or throws.
            if (!destroyed && !pollScheduled) repoll(500);
        }
    } };

    @Override public IBinder onBind(Intent i) { return null; }

    /**
     * The running instance, so the home screen can hand it display-only changes.
     *
     * Capture lives in this process, so the activity can reach it directly
     * instead of going through an Intent; both sides already do all their work
     * on the main thread, which is what makes that safe.
     */
    @android.annotation.SuppressLint("StaticFieldLeak")   // a Service, not a context to leak
    static CaptureService current;
    boolean gameOnly;
    /** PVP mode: no map matching; the ranked lobby is read for the hunter's bans. */
    boolean pvp;
    private MediaProjection.Callback projectionCallback;
    void releaseGameCapture(){
        // The replay buffer is ours to stop; a recording the user started is not.
        if(gameOnly && recorder!=null && replaySession){pendingGameRelease=true;stopRecording();return;}
        if(!gameOnly||projection==null||recorder!=null)return;
        if(display!=null){display.release();display=null;}
        if(reader!=null){reader.close();reader=null;}
        if(projectionCallback!=null)projection.unregisterCallback(projectionCallback);
        projection.stop();projection=null;
        if(Build.VERSION.SDK_INT>=34)startForeground(1,captureNotification(),android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
    }
    boolean hasProjection(){return projection!=null;}
    /** The ball shows the game icon while a mini-game is hidden; redraw when that changes. */
    void refreshBadge(){if(badgeEmblem!=null)badgeEmblem.invalidate();}
    void openGame(String id){
        if(!new MatchingModuleStore(this,"games").installed()||!new MiniGameStore(this,id).installed())return;
        if(MiniGameOverlayService.current!=null&&!id.equals(MiniGameOverlayService.activeGameId)){MiniGameOverlayService.current.switchTo(id);return;}
        gameOnly=true;generation++;clearOverlay();setSpinning(false);updateCaptureOutput();refreshTapRegion();
        // Mini-game mode does not look at the screen; the replay buffer must not either.
        if(replaySession)stopRecording();
        getSharedPreferences("mobile",0).edit().putString("active_game",id).putString("last_module","games").apply();
        startForegroundService(new Intent(this,MiniGameOverlayService.class).setAction("show"));
        if(ready)repoll(0);
    }

    @Override public void onCreate() {
        super.onCreate();
        current = this;
        windows = (WindowManager) getSystemService(WINDOW_SERVICE);
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        nm.createNotificationChannel(new NotificationChannel("capture", "地图识别", NotificationManager.IMPORTANCE_LOW));
    }

    @Override public int onStartCommand(Intent intent, int flags, int id) {
        if (intent == null || "stop".equals(intent.getAction())) { stopSelf(); return START_NOT_STICKY; }
        if("stop_recording".equals(intent.getAction())) { stopRecording(); return START_NOT_STICKY; }
        if("save_replay".equals(intent.getAction())) { saveReplay(); return START_NOT_STICKY; }
        boolean requestedGameOnly=intent.getBooleanExtra("gameOnly",false);
        String launchGame=intent.getStringExtra("launchGame");
        if("games_only".equals(intent.getAction())&&projection==null){
            gameOnly=true;
            if(Build.VERSION.SDK_INT>=34)startForeground(1,captureNotification(),android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
            else startForeground(1,captureNotification());
            if(!new MatchingModuleStore(this,"games").installed()){stopSelf();return START_NOT_STICKY;}
            if(badge==null){DisplayMetrics m=new DisplayMetrics();windows.getDefaultDisplay().getRealMetrics(m);width=m.widthPixels;height=m.heightPixels;density=m.densityDpi;setupOverlay();}
            initializing=false;ready=true;setStatus(S_IDLE,"小游戏模式");
            if(launchGame!=null)openGame(launchGame);repoll(1500);return START_NOT_STICKY;
        }
        if (projection != null) {if(launchGame!=null)openGame(launchGame);return START_NOT_STICKY;}
        gameOnly=requestedGameOnly;pvp=!gameOnly&&intent.getBooleanExtra("pvp",false);
        if(Build.VERSION.SDK_INT>=29)startForeground(1,captureNotification(),android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION);
        else startForeground(1, captureNotification());
        try {
            if(pvp&&!new MatchingModuleStore(this,"pvp").installed()){stopSelf();return START_NOT_STICKY;}
            if(!pvp&&!new MatchingModuleStore(this,gameOnly?"games":"notes").installed()){stopSelf();return START_NOT_STICKY;}
            Intent permission = intent.getParcelableExtra("projection");
            projection = ((MediaProjectionManager) getSystemService(MEDIA_PROJECTION_SERVICE))
                    .getMediaProjection(intent.getIntExtra("result", -1), permission);
            projection.registerCallback(projectionCallback=new MediaProjection.Callback() {
                @Override public void onStop() { stopSelf(); }
                @Override public void onCapturedContentVisibilityChanged(boolean visible) {
                    capturedVisible=visible;
                    android.util.Log.i("CrypticNotes","Shared content visibility: "+visible);
                    if(!visible){lastPauseReason="共享应用不可见";clearOverlay();if(!gameOnly&&!pvp)sleepRecognition();setStatus(S_IDLE,"共享应用不可见，请切回所选游戏");}
                }
                @Override public void onCapturedContentResize(int w,int h) {
                    boolean changed=capturedWidth!=w || capturedHeight!=h;
                    capturedWidth=w; capturedHeight=h;
                    android.util.Log.i("CrypticNotes","Captured content resized: "+w+"x"+h);
                    if(changed && display!=null) resizeCapture();
                    if(!captureFitsScreen()) clearOverlay();
                }
            }, main);
            // The home screen sends its slider position; with no extra (service
            // restarted by the system) fall back to what was last chosen.
            applyOpacity(intent.getIntExtra("opacity",
                    getSharedPreferences("mobile", 0).getInt("opacity", 30)));
            if(badge==null)setupOverlay(); resizeCapture();
            if(gameOnly){initializing=false;ready=true;setStatus(S_IDLE,"小游戏模式 · 画面检测已启用");if(launchGame!=null)openGame(launchGame);repoll(0);return START_NOT_STICKY;}
            if(pvp){initializing=false;ready=true;registerPvpTest();setStatus(S_IDLE,"双击开始识别");return START_NOT_STICKY;}
            android.util.Log.i("CrypticNotes", "Overlay attached; initialization started");
            setStatus(S_IDLE, preparationText);
            String difficulty = intent.getStringExtra("difficulty"), mode = intent.getStringExtra("mode");
            String requestedScene=intent.getStringExtra("scene");
            if(requestedScene!=null)getSharedPreferences("mobile",0).edit().putString("scene",requestedScene).apply();
            scene=MapLibraryChoice.sceneOf(getSharedPreferences("mobile",0));
            final String provider=MapLibraryChoice.providerOf(getSharedPreferences("mobile",0));
            final String startScene=scene;
            if(provider.equals("lianghapi"))getSharedPreferences("mobile", 0).edit().putString("difficulty", difficulty).putString("mode", mode).apply();
            compute.execute(() -> {
                try {
                    if(!new MatchingModuleStore(this,provider).installed())throw new IOException("请先在地图设置下载所选地图库");
                    preparationStatus("正在加载识图引擎…");
                    MatchingModuleStore.python(this);
                    bridge = Python.getInstance().getModule("mobile_bridge");
                    preparationStatus("正在准备地图特征…");
                    int mapCount=bridge.callAttr("initialize", getFilesDir().toString(), difficulty, mode, provider, startScene).toInt();
                    loadedMapCount=mapCount;
                    android.util.Log.i("CrypticNotes","Recognition library loaded: maps="+mapCount+", difficulty="+difficulty+", mode="+mode);
                    if(mapCount==0)throw new IOException("当前难度或模式未加载到地图，请检查地图库下载是否完成");
                    main.post(() -> {
                        if (destroyed) return;
                        initializing = false;
                        android.util.Log.i("CrypticNotes", "Initialization complete; applying=" + applying);
                        ready = !applying;
                        if (preparationLabel != null) preparationLabel.setVisibility(View.GONE);
                        setStatus(S_IDLE, applying ? "正在应用设置…" : "等待地图");
                        if (ready) {
                            sleepRecognition();
                            setStatus(S_IDLE,"等待地图");
                        }
                    });
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
        overlayParams = params(-1, -1, false);
        overlayParams.alpha = opacity;
        windows.addView(overlay, overlayParams);

        badge = new LinearLayout(this);
        badge.setOrientation(LinearLayout.HORIZONTAL);
        badge.setBackground(new Theme.ChalkDrawable(this, Theme.Chalk.DEEP, .7f, "rounded", true, true));
        badge.setGravity(Gravity.CENTER);

        badgeLabel = new TextView(this);
        badgeLabel.setTextColor(Theme.TEXT);
        badgeLabel.setTypeface(Theme.typeface(this));
        badgeLabel.setMaxLines(1);
        badgeLabel.setEllipsize(android.text.TextUtils.TruncateAt.END);
        badgeLabel.setGravity(Gravity.CENTER);

        // The emblem is on screen in every state, so the button is one object
        // that speaks rather than a circle that turns into a strip and back.
        badge.setClipChildren(false);badge.setClipToPadding(false);
        badgeEmblem = new GameBadgeView(this);
        badgeEmblem.setImageResource(R.drawable.floating_emblem);
        badgeEmblem.setScaleType(ImageView.ScaleType.FIT_CENTER);
        badgeEmblem.setContentDescription("地图助手");
        badge.addView(badgeEmblem, new LinearLayout.LayoutParams(
                Theme.px(this, BADGE_EMBLEM_DP), Theme.px(this, BADGE_EMBLEM_DP)));
        badge.addView(badgeLabel, new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

        badgeParams = params(-2, -2, true);
        windows.addView(badge, badgeParams);
        badge.setOnTouchListener(this::onBadgeTouch);
        layoutBadge();
    }

    /** Tap the ball to open the panel, tap it again to close. */
    private void toggleQuickSettings() {
        if (quickSettings != null) closeQuickSettings(); else showQuickSettings();
    }

    private void preparationStatus(String text) {
        main.post(() -> {
            if (destroyed || !initializing) return;
            preparationText = text;
            if (preparationLabel != null) preparationLabel.setText(text);
            setStatus(S_IDLE, text);
        });
    }

    /**
     * Re-read the display preferences and apply them to the live windows.
     *
     * The home screen writes the same keys the in-game panel does, and the
     * service may well be running behind it; without this the new opacity or
     * button size only appeared after a restart.
     */
    void applyDisplayPreferences() {
        if (destroyed) return;
        applyOpacity(getSharedPreferences("mobile", 0).getInt("opacity", Math.round(opacity * 100)));
        layoutBadge();
        refreshTapRegion();
    }

    /**
     * Drag the button by its body, tap for the settings panel, double-tap to
     * re-recognise, hold to stop.
     *
     * A touch listener swallows the click listeners, so every gesture is
     * resolved here rather than via setOnClickListener.
     *
     * The single tap has to wait out {@link ViewConfiguration#getDoubleTapTimeout}
     * before it fires, which is the price of having a second gesture on the same
     * small target; the panel therefore opens a beat after the tap. A tap that
     * turns out to be half of a double tap is cancelled on the second press, and
     * one that turns into a drag never fires at all.
     */
    private boolean onBadgeTouch(View view, MotionEvent event) {
        float dx = event.getRawX() - badgeDownX, dy = event.getRawY() - badgeDownY;
        switch (event.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                android.util.Log.d("CrypticNotes", "Badge touch; initializing=" + initializing + "; ready=" + ready);
                badgeSecondTap = badgeTapAt != 0
                        && event.getEventTime() - badgeTapAt <= ViewConfiguration.getDoubleTapTimeout()
                        && Math.hypot(event.getRawX()-badgeTapX, event.getRawY()-badgeTapY)
                            <= ViewConfiguration.get(this).getScaledDoubleTapSlop();
                main.removeCallbacks(badgeSingleTap);
                badgeTapAt = 0;
                badgeDownX = event.getRawX();
                badgeDownY = event.getRawY();
                // Anchor on the ball, not on the window: with a bubble up the
                // window starts at the far end of the strip, and dragging from
                // there would drop the button a strip's width away from the
                // finger the moment the bubble folds.
                SharedPreferences dragPrefs = getSharedPreferences("mobile", 0);
                badgeStartX = ballX(dragPrefs);
                badgeStartY = badgeY(dragPrefs);
                badgeDragged = false;
                badgeLongPressed = false;
                badgeLongPress = () -> { badgeLongPressed = true; TouchFeedback.click(badge); handleBadgeHold(); };
                main.postDelayed(badgeLongPress, BADGE_HOLD_MS);
                return true;
            case MotionEvent.ACTION_MOVE:
                if (!badgeDragged
                        && Math.hypot(dx, dy) < ViewConfiguration.get(this).getScaledTouchSlop()) {
                    return true;
                }
                badgeDragged = true;
                main.removeCallbacks(badgeLongPress);
                // Collapse first: the stored position is the ball's, and a
                // bubble hanging off it would be dragged by its far end. It has
                // to be the instant fold -- an animated one re-anchors the
                // window on every frame and would fight the finger.
                main.removeCallbacks(hideBadgeMessage);
                collapseBadgeNow();
                moveBadge(badgeStartX + Math.round(dx), badgeStartY + Math.round(dy));
                return true;
            case MotionEvent.ACTION_UP:
                main.removeCallbacks(badgeLongPress);
                if (badgeDragged) {
                    saveBadgePosition();
                }
                else if (!badgeLongPressed) {
                    TouchFeedback.click(badge);
                    if (badgeSecondTap) retryFromBadge();
                    else {
                        badgeTapAt = event.getEventTime();
                        badgeTapX = event.getRawX(); badgeTapY = event.getRawY();
                        main.postDelayed(badgeSingleTap, ViewConfiguration.getDoubleTapTimeout());
                    }
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

    /** Move the button anywhere on screen; does not persist. */
    private void moveBadge(int x, int y) {
        if (badge == null || width <= 0) return;
        int limit = width - badgeParams.width;
        badgeParams.x = Math.max(0, Math.min(x, Math.max(0, limit)));
        // Measure the button itself: the window is WRAP_CONTENT high, so
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

    /** Keep the overlay off until the player asks for it back. */
    private void setOverlayHidden(boolean hidden) {
        overlayHidden = hidden;
        if (hidden) clearOverlay();
        else { lastMatch = 0; invalidateSamples(); }
        setStatus(S_IDLE, hidden ? "叠图已隐藏" : "叠图已恢复");
        repoll(100);
    }

    /**
     * Put the button back where the player left it.
     *
     * It is no longer confined to the left: it stays visible while capturing
     * and is painted out of the captured copy instead, with the covered
     * rectangle handed to the gate so an obscured control is not scored. That
     * is what replaced hiding it on every frame, which is what used to strobe.
     */
    private void layoutBadge() {
        if (badge == null || width <= 0) return;
        measureBadge();
        if (bubbleAnim != null) { bubbleAnim.cancel(); bubbleAnim = null; }
        SharedPreferences prefs = getSharedPreferences("mobile", 0);
        int ballX = ballX(prefs);
        bubbleLeft = ballX + stripWidth > width;
        rebuildBadgeRow();
        badgeLabel.setText(badgeText);
        badgeLabel.setVisibility(badgeMessage ? View.VISIBLE : View.GONE);
        badgeLabel.setAlpha(1f);
        badge.setBackground(badgeSurface(badgeMessage));
        badge.setContentDescription("地图助手：单击设置，双击重新识别，拖动移动，长按关闭");
        badgeParams.height = badgeHeight;
        badgeParams.width = badgeMessage ? stripWidth : ballWidth;
        badgeParams.x = clampX(ballX, badgeParams.width);
        badgeParams.y = badgeY(prefs);
        try { windows.updateViewLayout(badge, badgeParams); } catch (Exception ignored) {}
    }

    /** Sizes for the current scale and screen; no window is touched here. */
    private void measureBadge() {
        SharedPreferences prefs = getSharedPreferences("mobile", 0);
        // Size is the player's call: the button sits over the map they are
        // reading, and how much of it they can spare is a matter of device and
        // eyesight, not of anything the app can measure.
        float scale = Math.max(BADGE_SCALE_MIN,
                Math.min(BADGE_SCALE_MAX, prefs.getFloat("badge_scale", BADGE_SCALE_DEFAULT)));
        int emblem = Theme.px(this, Math.round(BADGE_EMBLEM_DP * scale));
        badgeEmblem.setLayoutParams(new LinearLayout.LayoutParams(emblem, emblem));
        int pad = Theme.px(this, Math.max(8, Math.round(8 * scale)));
        badge.setPadding(pad, pad, pad, pad);
        badgeLabel.setTextSize(android.util.TypedValue.COMPLEX_UNIT_DIP, Math.max(12f, 12f * scale));
        badgeHeight = Theme.px(this, Math.round(BADGE_BALL_DP * scale));
        ballWidth = badgeHeight;
        // The bubble grows with the type and stops at the screen edge, so a
        // message stays whole at the larger sizes instead of being cut off.
        stripWidth = Math.min(width - Theme.px(this, 24),
                Math.round(Theme.px(this, BADGE_MESSAGE_DP) * scale));
        // PVP messages run from two characters to a sentence: the bubble takes the width of its text.
        if (pvp) stripWidth = Math.min(width - Theme.px(this, 24), ballWidth
                + Math.round(badgeLabel.getPaint().measureText(badgeText == null ? "" : badgeText)) + Theme.px(this, Math.round(PVP_MESSAGE_DP * scale)));
    }

    private int ballX(SharedPreferences prefs) {
        return Math.max(0, Math.min(Math.round(prefs.getFloat("badge_x", BADGE_X) * width),
                Math.max(0, width - ballWidth)));
    }

    private int badgeY(SharedPreferences prefs) {
        return Math.max(0, Math.min(height - Theme.px(this, 60),
                Math.round(prefs.getFloat("badge_y", BADGE_Y) * height)));
    }

    private Theme.ChalkDrawable badgeSurface(boolean message) {
        // A message is a flat strip faded at both ends; the resting button is
        // the emblem in a circle.
        return new Theme.ChalkDrawable(this, Theme.Chalk.DEEP, .7f,
                message ? "band" : "circle", true, true);
    }

    /**
     * Order the two children so the emblem stays on the ball's outer edge.
     *
     * Growing right the emblem leads; growing left it trails, which leaves it
     * exactly where the collapsed button was and lets the bubble unfold away
     * from it instead of appearing on top of it.
     */
    private void rebuildBadgeRow() {
        ViewGroup.LayoutParams emblemParams = badgeEmblem.getLayoutParams();
        LinearLayout.LayoutParams labelParams = new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1f);
        badge.removeAllViews();
        if (bubbleLeft) {
            badge.addView(badgeLabel, labelParams);
            badge.addView(badgeEmblem, emblemParams);
        } else {
            badge.addView(badgeEmblem, emblemParams);
            badge.addView(badgeLabel, labelParams);
        }
    }

    private int clampX(int ballX, int windowWidth) {
        return Math.max(0, Math.min(bubbleLeft ? ballX + ballWidth - windowWidth : ballX,
                Math.max(0, width - windowWidth)));
    }

    /**
     * Unfold the message bubble out of the ball, or fold it back.
     *
     * The window itself is what grows, so the strip looks like it is being
     * pulled out of the button rather than switched on beside it; the label
     * fades in over the same 200ms.
     */
    private void bubble(boolean expand) {
        if (badge == null || width <= 0) return;
        measureBadge();
        if (bubbleAnim != null) { bubbleAnim.cancel(); bubbleAnim = null; }
        SharedPreferences prefs = getSharedPreferences("mobile", 0);
        final int anchor = ballX(prefs);
        bubbleLeft = anchor + stripWidth > width;
        rebuildBadgeRow();
        badgeLabel.setText(badgeText);
        badgeParams.height = badgeHeight;
        badgeParams.y = badgeY(prefs);
        final int from = badgeParams.width > 0 ? badgeParams.width : ballWidth;
        final int to = expand ? stripWidth : ballWidth;
        if (expand) {
            badgeLabel.setVisibility(View.VISIBLE);
            badgeLabel.setAlpha(0f);
            badge.setBackground(badgeSurface(true));
        } else {
            badgeLabel.setAlpha(1f);
        }
        if (from == to) {
            badgeParams.width = to;
            badgeParams.x = clampX(anchor, to);
            if (!expand) { badgeLabel.setVisibility(View.GONE); badge.setBackground(badgeSurface(false)); }
            try { windows.updateViewLayout(badge, badgeParams); } catch (Exception ignored) {}
            return;
        }
        final float alpha0 = badgeLabel.getAlpha(), alpha1 = expand ? 1f : 0f;
        bubbleAnim = android.animation.ValueAnimator.ofFloat(0f, 1f);
        bubbleAnim.setDuration(BUBBLE_MS);
        bubbleAnim.setInterpolator(new android.view.animation.DecelerateInterpolator());
        bubbleAnim.addUpdateListener(animation -> {
            float t = (float) animation.getAnimatedValue();
            badgeParams.width = Math.round(from + (to - from) * t);
            badgeParams.x = clampX(anchor, badgeParams.width);
            badgeLabel.setAlpha(alpha0 + (alpha1 - alpha0) * t);
            try { windows.updateViewLayout(badge, badgeParams); } catch (Exception ignored) {}
        });
        bubbleAnim.addListener(new android.animation.AnimatorListenerAdapter() {
            @Override public void onAnimationEnd(android.animation.Animator animation) {
                // Swapped at the ends, not at the start: the surface must keep
                // the shape the window currently has.
                if (expand) { badgeLabel.setAlpha(1f); }
                else { badgeLabel.setAlpha(1f); badgeLabel.setVisibility(View.GONE);
                       badge.setBackground(badgeSurface(false)); }
            }
        });
        bubbleAnim.start();
    }

    private void resizeCapture() {
        idleProbe.close();
        if(recorder!=null) { pendingCaptureResize=true; stopRecording(); return; }
        clearOverlay();
        DisplayMetrics metrics = new DisplayMetrics();
        windows.getDefaultDisplay().getRealMetrics(metrics);
        width = metrics.widthPixels; height = metrics.heightPixels; density = metrics.densityDpi;
        if(cleanCaptureFrame!=null){cleanCaptureFrame.recycle();cleanCaptureFrame=null;}
        cleanCaptureReader=null;cleanCaptureSignature=null;
        ImageReader previous = reader;
        reader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2);
        if (display == null)
            display = projection.createVirtualDisplay("CrypticNotes", width, height, density,
                    DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR, recognitionIdle()?null:reader.getSurface(), null, main);
        else {
            // Detach before resizing: the old portrait buffer must not remain
            // attached while the projection switches to a landscape source.
            display.setSurface(null);
            display.resize(width, height, density);
            display.setSurface(recognitionIdle()?null:reader.getSurface());
        }
        android.util.Log.i("CrypticNotes","Capture surface configured: "+width+"x"+height+", source="+capturedWidth+"x"+capturedHeight);
        if(previous!=null)previous.close();
        layoutBadge();
        refreshTapRegion();
        updateCaptureOutput();
        ensureReplay();
    }

    // ---- overlay lifetime --------------------------------------------------

    private void showOverlay(boolean visible) {
        if (overlay == null) return;
        if (visible && overlayHidden) return;
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
    private final FrameReuse.Latest latestViewport = new FrameReuse.Latest();
    private int[] sampleViewport() {
        if(recorder!=null) recorder.requestPreview();
        try (Image image = reader.acquireLatestImage()) {
            if (image == null) return latestViewport.forReader(reader);
            freshCaptureCount++;lastFreshFrameAt=SystemClock.elapsedRealtime();
            Image.Plane plane = image.getPlanes()[0];
            if (plane.getPixelStride() != 4) {
                Bitmap fallback = grab();
                if (fallback == null) return null;
                int[] pixels = signature(fallback);
                fallback.recycle();
                latestViewport.remember(reader,pixels);
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
                int row = FrameReuse.sampleCoordinate(y,h,90) * rowStride;
                for (int x = 0; x < 160; x++) {
                    int offset = row + FrameReuse.sampleCoordinate(x,w,160) * 4;
                    if (offset < 0 || offset + 4 > capacity) continue;
                    // RGBA_8888 in memory reads little-endian as 0xAABBGGRR.
                    // Flip to ARGB so Color.red/green/blue stay truthful.
                    int v = buffer.getInt(offset);
                    pixels[y * 160 + x] = (v & 0xff00ff00) | ((v & 0xff) << 16) | ((v >> 16) & 0xff);
                }
            }
            latestViewport.remember(reader,pixels);
            return pixels;
        } catch (Exception e) {
            return null;
        }
    }

    /** Same pixel centers as the direct ImageReader sampler. Never mix grids. */
    private static int[] signature(Bitmap bitmap) {
        int w=bitmap.getWidth(),h=bitmap.getHeight();
        int[] pixels=new int[160*90],row=new int[w];
        for(int y=0;y<90;y++){
            bitmap.getPixels(row,0,w,0,FrameReuse.sampleCoordinate(y,h,90),w,1);
            for(int x=0;x<160;x++)pixels[y*160+x]=row[FrameReuse.sampleCoordinate(x,w,160)];
        }
        return pixels;
    }

    private void clearOverlay() {
        pendingLatestMatch=null;
        reusableGatePixels=null;lastAttemptPixels=null;
        dismissManualPrompt();pendingForceFloor=0;manualOfferSuppressed=false;
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
        if(recognitionIdle()){scheduleIdleProbe();return;}
        main.removeCallbacks(poll);
        pollScheduled = true;
        main.postDelayed(poll, powerSaving() && delayMs>=WATCH_MS ? delayMs*2 : delayMs);
    }

    private void setStatus(int newState, String text) {
        state = newState;
        if(badgeEmblem instanceof GameBadgeView)((GameBadgeView)badgeEmblem).setLoading(initializing||applying);
        setSpinning(newState == S_MATCHING);
        // Work in progress is shown by the turning emblem, not by words: the
        // bubble is kept for outcomes the player has to read. Fold any bubble
        // still up from the previous state so the emblem is what is visible.
        if (newState == S_MATCHING) {
            main.removeCallbacks(hideBadgeMessage);
            collapseBadge();
            return;
        }
        if (text == null || text.equals(badgeText)) return;
        badgeText = text;
        String glyph = newState == S_MATCHED ? "check" : newState == S_FAILED ? "question"
                : text.contains("直接叠图") || text.contains("楼层") ? "floor" : null;
        if (glyph == null) badgeLabel.setCompoundDrawables(null, null, null, null);
        else LineIcon.set(badgeLabel, glyph, Theme.TEXT, 14);
        if (badgeMessage && !pvp) badgeLabel.setText(text);
        else { badgeMessage = true; bubble(true); }
        main.removeCallbacks(hideBadgeMessage);
        main.postDelayed(hideBadgeMessage, 1800);
    }

    /** Fold the bubble away, if one is up. */
    private void collapseBadge() {
        if (!badgeMessage) return;
        badgeMessage = false;
        bubble(false);
    }

    /** Fold it away in this frame, for callers that are about to move the ball. */
    private void collapseBadgeNow() {
        if (!badgeMessage) return;
        badgeMessage = false;
        if (bubbleAnim != null) { bubbleAnim.cancel(); bubbleAnim = null; }
        layoutBadge();
    }

    /**
     * Turn the emblem while recognition is running.
     *
     * Motion carries the "busy" signal without a word to translate or a strip
     * covering the map, and it stops the moment there is a result to read.
     */
    private void setSpinning(boolean on) {
        if (badgeEmblem == null) return;
        if(badgeEmblem instanceof GameBadgeView && ((GameBadgeView)badgeEmblem).loading())on=false;
        if (!on) {
            if (spin != null) spin.cancel();
            badgeEmblem.setRotation(0f);
            return;
        }
        if (spin == null) {
            spin = android.animation.ObjectAnimator.ofFloat(badgeEmblem, "rotation", 0f, 360f);
            spin.setDuration(1500);
            spin.setRepeatCount(android.animation.ValueAnimator.INFINITE);
            // One steady turn after another: stopping and starting within a
            // revolution read as the app stuttering, not as work in progress.
            spin.setInterpolator(new android.view.animation.LinearInterpolator());
        }
        if (!spin.isStarted()) spin.start();
    }

    private void handleBadgeHold() {
        if(stoppingRecording && !replaySession) {
            Toast.makeText(this,"录屏正在保存，请稍候",Toast.LENGTH_SHORT).show();
            return;
        }
        if(recorder!=null && !replaySession) {
            stopRecording();
            Toast.makeText(this,"正在保存录屏；保存后再次长按可关闭识别",Toast.LENGTH_SHORT).show();
            return;
        }
        if(gameOnly||MiniGameOverlayService.running){
            closeQuickSettings();
            MiniGameOverlayService game=MiniGameOverlayService.current;
            if(game!=null){
                game.closeSession();
                Toast.makeText(this,"正在保存并关闭小游戏及悬浮球",Toast.LENGTH_SHORT).show();
            }else stopSelf();
            return;
        }
        if (pvp && pvpAsked != null && pvpPrediction != null && !pvpStopAfterAnswer) {
            // A lobby is still owed its hunter: ask once more, then close whichever way it is settled.
            // (A second long press while it is up closes without it.)
            pvpStopAfterAnswer = true; pvpBarsForced = true; pvpHudFolded = false;
            showPvpBars(pvpScanning);
            badgeText = ""; setStatus(S_IDLE, "请选择上局的监管者");
            if (pvpScanning) state = S_MATCHING;
            return;
        }
        stopRecognition();
    }

    /**
     * End the session after recording has finished, button included.
     *
     * This stops the service rather than only hiding the view. A hidden button
     * over a service that still captures the screen would be the worst of both
     * -- no way to see it, no way to stop it.
     */
    private void stopRecognition() {
        if (quickSettings != null) { windows.removeView(quickSettings); quickSettings = null; }
        clearOverlay();
        setSpinning(false);
        if (badge != null) badge.setVisibility(View.GONE);
        Toast.makeText(this, "已关闭识别", Toast.LENGTH_SHORT).show();
        stopSelf();
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
        if(destroyed)return;
        if(gameOnly){if(projection!=null&&MiniGameOverlayService.running)watchMiniGameScene();repoll(1500);return;}
        if(pvp || !ready || recognitionIdle())return;
        if(touchCapture.openingExpired(SystemClock.elapsedRealtime()) && !checking){
            clearOverlay();sleepRecognition();setStatus(S_IDLE,"未检测到地图，点击地图区域可重试");return;
        }
        if(MiniGameOverlayService.running){clearOverlay();setSpinning(false);watchMiniGameScene();repoll(500);return;}
        gameSceneDetector.reset();
        long nowWatch = SystemClock.elapsedRealtime();
        boolean overdue = (checking && nowWatch-checkingSince > BUSY_TIMEOUT_MS)
                || (busy && nowWatch-busySince > BUSY_TIMEOUT_MS);
        if (overdue && !timeoutReported) {
            timeoutReported = true;
            android.util.Log.w("CrypticNotes", "Recognition stalled: checking="+checking+", busy="+busy);
            setStatus(S_FAILED, "识别耗时过长；持续无响应请返回应用停止后重新开启");
        }
        if (!overdue) timeoutReported = false;
        if(recorder!=null && !recordingReady) { repoll(100); return; }
        if(!capturedVisible) { lastPauseReason="共享应用不可见";clearOverlay();setStatus(S_IDLE,"共享应用不可见，请切回所选游戏");repoll(500);return; }
        if(!captureFitsScreen()) { lastPauseReason="共享源与屏幕比例不符";clearOverlay(); setStatus(S_IDLE,"请全屏打开所选游戏，或重新选择共享整个屏幕"); repoll(500); return; }
        if (calibration != null || quickSettings != null) { repoll(500); return; }
        lastPauseReason="";
        // Nothing to keep in step while the player has the overlay switched off;
        // matching would only burn a cycle per settle and be thrown away.
        if (overlayHidden) { repoll(WATCH_MS); return; }
        if (checking) { repoll(100); return; }
        if (manualRetry) {
            manualRetry = false;
            forceNextMatch = true;
            gateOnly = false;
            blink();
            return;
        }
        if(manualPrompt!=null) {
            if(SystemClock.elapsedRealtime()-lastGateAt>=800) { gateOnly=true;capture(); }
            else repoll(WATCH_MS);
            return;
        }
        if ((overlayLayer != null || busy) && SystemClock.elapsedRealtime() - lastGateAt >= 800) {
            // Map controls lie outside the map layer: inspect them without
            // removing either window. Never feed this composited frame to matching.
            gateOnly = true;
            capture(); return;
        }
        // A match that never returned would otherwise hold `busy` forever and
        // freeze the overlay with nothing on screen to explain it.

        if(busy){repoll(WATCH_MS);return;}
        if(overlayLayer==null){
            if(!throttled() && SystemClock.elapsedRealtime()-lastGateAt>=800){gateOnly=false;blink();}
            else repoll(WATCH_MS);
            return;
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
        boolean wasVisible=overlay!=null&&overlay.getVisibility()==View.VISIBLE;
        invalidateSamples();
        showOverlay(false);
        // Only a visible overlay can have contaminated the queued frame.
        // Draining a static single-app stream otherwise discards its only frame.
        if(wasVisible)try (Image stale = reader.acquireLatestImage()) {} catch (Exception ignored) {}
        main.postDelayed(() -> { if(recorder!=null) recorder.requestPreview(); },60);
        main.postDelayed(this::capture, HIDE_MILLIS);
    }

    private void capture() {
        if(recognitionIdle())return;
        if(gameOnly||pvp||!new MatchingModuleStore(this).installed())return;
        if (destroyed) return;
        if(MiniGameOverlayService.running){clearOverlay();setSpinning(false);repoll(500);return;}
        if (checking) { repoll(100); return; }
        if(recorder!=null && !recordingReady) { repoll(100); return; }
        if(!capturedVisible) { lastPauseReason="共享应用不可见";clearOverlay();setStatus(S_IDLE,"共享应用不可见，请切回所选游戏");repoll(500);return; }
        if(!captureFitsScreen()) { clearOverlay(); repoll(500); return; }
        if (calibration != null || quickSettings != null) { repoll(500); return; }
        lastPauseReason="";
        if (((KeyguardManager) getSystemService(KEYGUARD_SERVICE)).isKeyguardLocked()) {
            clearOverlay();
            setStatus(S_IDLE, "屏幕已锁定");
            sleepRecognition();
            return;
        }
        if (width <= height) {
            clearOverlay();
            setStatus(S_IDLE, "请横屏打开游戏");
            sleepRecognition();
            return;
        }
        // blink() guaranteed the layer is down, so this grab is a clean frame.
        // Nothing here may put it back up before the grab happens.
        final long captureStartedAt = SystemClock.elapsedRealtime();
        Bitmap bitmap = grab();
        if (bitmap == null) { badge.setVisibility(View.VISIBLE); repoll(200); return; }

        final int sourceWidth=bitmap.getWidth(),sourceHeight=bitmap.getHeight();
        final int[] framePixels = signature(bitmap);
        latestViewport.remember(reader,framePixels);
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
        long reuseNow=lastGateAt;
        boolean gateUnchanged=verifyOnly && reuseNow-actualGateAt<4000 && FrameReuse.same(reusableGatePixels,framePixels,true);
        boolean repeatMatch=!verifyOnly && !forceNextMatch && pendingForceFloor==0 && reuseNow-lastAttemptAt<(powerSaving()?6000:2000) && FrameReuse.same(lastAttemptPixels,framePixels,false);
        if(gateUnchanged || repeatMatch){
            bitmap.recycle();
            if(badge!=null)badge.setVisibility(View.VISIBLE);
            repoll(WATCH_MS);return;
        }
        final int captureSerial=matchRequests.get();
        final boolean explicitAttempt=forceNextMatch;
        forceNextMatch=false;
        final int token = generation;
        checking = true;
        checkingSince = SystemClock.elapsedRealtime();
        try {
            inspect.execute(() -> {
                int viewedFloor=0;
                long floorReadStarted=SystemClock.elapsedRealtime();
                if(!verifyOnly){
                    try {
                        RawFrame header=encodeFloorHeader(bitmap);
                        if(header!=null)viewedFloor=bridge.callAttr("read_floor_header",header.bytes,sourceWidth,sourceHeight,header.width,header.height,header.stride).toInt();
                    }catch(Exception error){android.util.Log.w("CrypticNotes","Floor header reading failed",error);}
                }
                long nativeFloorMs=SystemClock.elapsedRealtime()-floorReadStarted;
                if(captureSerial!=matchRequests.get()){
                    bitmap.recycle();main.post(()->{checking=false;if(!destroyed)repoll(0);});return;
                }
                final int detectedFloor=viewedFloor;
                RawFrame frame = encode(bitmap);      // takes ownership, off the main thread
                boolean ok = false, visible = false;
                if (frame != null) {
                    frame.captureStartedAt=captureStartedAt;
                    frame.nativeFloorMs=nativeFloorMs;
                    try {
                        String inspection=bridge.callAttr("inspect", frame.bytes, excluded, frame.width, frame.height, frame.stride).toString();
                        lastGateResult=inspection;
                        visible = new JSONObject(inspection).getBoolean("visible");
                        if(explicitAttempt)android.util.Log.i("CrypticNotes","Manual screenshot inspection: "+inspection+", source="+sourceWidth+"x"+sourceHeight);
                        if(new File(getFilesDir(),"recognition-diagnostic.flag").isFile()){
                            android.util.Log.i("CrypticNotes","Capture inspection: "+inspection+", excluded="+java.util.Arrays.toString(excluded)+", freshFrames="+freshCaptureCount);
                            File diagnostic=new File(getCacheDir(),"recognition-frame.png");
                            byte[] encoded=diagnostic.exists()?null:png(frame);
                            if(encoded!=null)try(FileOutputStream saved=new FileOutputStream(diagnostic)){saved.write(encoded);}
                            try(FileOutputStream saved=new FileOutputStream(new File(getCacheDir(),"recognition-inspection.json"))){saved.write((inspection+"\n"+java.util.Arrays.toString(excluded)).getBytes(java.nio.charset.StandardCharsets.UTF_8));}
                        }
                        ok = true;
                    } catch (Exception ignored) {
                    }
                }
                final RawFrame bytes = frame;
                final boolean passed = visible, ran = ok;
                main.post(() -> {
                    checking = false;
                    // Measure heartbeat spacing from completion. Measuring
                    // from submission starves matching when inspection is slow.
                    lastGateAt = SystemClock.elapsedRealtime();
                    if (!destroyed && calibration == null && quickSettings == null) badge.setVisibility(View.VISIBLE);
                    if (destroyed || captureSerial!=matchRequests.get() || token != generation || MiniGameOverlayService.running) { repoll(manualRetry?0:POLL_IDLE_MS); return; }
                    if (!ran) {
                        clearOverlay();
                        setStatus(S_FAILED, "画面检测失败");
                        repoll(1000);
                        return;
                    }
                    if (!passed) {
                        boolean closed=touchCapture.closed(false,SystemClock.elapsedRealtime());
                        mapPanelOpen = false;
                        clearOverlay();
                        lastMatch = 0;
                        if(explicitAttempt){
                            String message="共享画面未确认地图展开，请检查共享范围或系统屏幕共享防护";
                            setStatus(S_FAILED,message);Toast.makeText(this,message,Toast.LENGTH_LONG).show();
                        }else setStatus(S_IDLE,"等待地图");
                        if(closed)sleepRecognition();else repoll(WATCH_MS);
                        return;
                    }
                    touchCapture.closed(true,SystemClock.elapsedRealtime());
                    reusableGatePixels=framePixels;
                    actualGateAt=SystemClock.elapsedRealtime();
                    missStreak = 0;
                    if (!mapPanelOpen) {
                        mapPanelOpen = true;
                        memoryEpoch++;
                    }
                    controlPixels = framePixels;
                    if (verifyOnly) {
                        if(busy && matchPixels!=null && difference(matchPixels,framePixels)>=REALIGN_LIMIT){
                            clearOverlay();manualRetry=true;lastMatch=0;wakeRecognition();
                            android.util.Log.i("CrypticNotes","Viewport superseded running recognition");
                            repoll(0);return;
                        }
                        // Watch samples handle motion. A heartbeat only checks
                        // visibility and must not realign against our own overlay.
                        repoll(WATCH_MS);
                        return;
                    }
                    if (overlayLayer != null) { clearOverlay(); lastMatch = 0; }
                    if (busy) {
                        if(explicitAttempt){
                            pendingLatestMatch=new PendingMatch(bytes,framePixels,detectedFloor,generation,captureSerial);
                            android.util.Log.i("CrypticNotes","Latest screenshot ready: request="+captureSerial);
                        }
                        repoll(WATCH_MS);return;
                    }
                    if (throttled() && !explicitAttempt) { repoll(WATCH_MS); return; }
                    // No wording for work in progress: the turning emblem says it.
                    setStatus(S_MATCHING, null);
                    runMatch(bytes, framePixels, detectedFloor);
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
    private static RawFrame encodeFloorHeader(Bitmap bitmap){
        // Half the height: 厄运之女 keeps its 1/2 pair in the top quarter, but
        // 磷光症 stacks −1…−4 down to about 45% of the screen.
        int w=bitmap.getWidth(),left=(int)(.55*w),right=(int)(.94*w);
        Bitmap header=Bitmap.createBitmap(bitmap,left,0,right-left,Math.max(1,bitmap.getHeight()/2));
        try{
            return rawFrame(header);
        }catch(Exception e){return null;}finally{if(header!=bitmap)header.recycle();}
    }

    /** Downscale to the matching width and hand the pixels over; releases the Bitmap. */
    private static RawFrame encode(Bitmap bitmap) {
        try {
            Bitmap source = bitmap;
            if (bitmap.getWidth() > 1440) {
                source = Bitmap.createScaledBitmap(bitmap, 1440,
                        Math.round(bitmap.getHeight() * 1440f / bitmap.getWidth()), true);
            }
            RawFrame frame = rawFrame(source);
            if (source != bitmap) source.recycle();
            return frame;
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
    private int[] reusableGatePixels,lastAttemptPixels;
    private long actualGateAt,lastAttemptAt;
    private boolean forceNextMatch;
    private boolean powerSaving(){return getSharedPreferences("mobile",0).getBoolean("power_saving",false);}
    private boolean mapPanelOpen = false;
    private volatile int memoryEpoch = 0;

    private void runMatch(RawFrame frame, int[] framePixels, int viewedFloor) {
        busy = true;
        busySince = SystemClock.elapsedRealtime();
        lastMatch = busySince;
        matchPixels = framePixels;
        lastAttemptPixels=framePixels;
        lastAttemptAt=busySince;
        final int token = generation;
        final int requestEpoch = memoryEpoch;
        final int requestSerial = matchRequests.get();
        android.util.Log.i("CrypticNotes","Recognition started: token="+token+", frame="+frame.width+"x"+frame.height+", capture="+width+"x"+height+", viewedFloor="+viewedFloor);
        final int forceFloor=pendingForceFloor;
        pendingForceFloor=0; // Consent is consumed by exactly this request.
        compute.execute(() -> {
            final long computeStartedAt=SystemClock.elapsedRealtime();
            Bitmap layer = null;
            JSONObject offer=null;
            boolean commitOnDisplay=false;
            String label = "识别失败，请重试";
            try {
                File file = new File(getCacheDir(), "overlay.rgba");
                // gated=True: capture() already confirmed the panel is open on
                // this exact frame, so the adapter need not re-run the gate.
                // The overlay comes back as premultiplied RGBA, the layout the
                // Bitmap uses in memory, instead of a PNG to decode.
                JSONObject result = new JSONObject(
                        bridge.callAttr("match", frame.bytes, file.toString(), true, false, token, forceFloor, viewedFloor, matchRequests, requestSerial,
                                frame.width, frame.height, frame.stride, "raw").toString());
                if (requestSerial != matchRequests.get() || result.optBoolean("cancelled")) {
                    android.util.Log.i("CrypticNotes", "Recognition superseded: request="+requestSerial);
                    main.post(() -> { busy=false; if(!startPendingMatch() && !destroyed)repoll(0); });
                    return;
                }
                JSONObject timings=result.optJSONObject("timings");
                if(timings==null)timings=new JSONObject();
                timings.put("native_floor_ms",frame.nativeFloorMs);
                timings.put("capture_to_match_ms",computeStartedAt-frame.captureStartedAt);
                android.util.Log.i("CrypticNotes","Recognition result: request="+requestSerial+", token="+token
                        +", ok="+result.optBoolean("ok")+", map="+result.optString("map_id")
                        +", floor="+result.optInt("floor")+", forced="+(forceFloor!=0)+", timings="+timings);
                offer=result.optJSONObject("manual_offer");
                boolean ok = result.getBoolean("ok");
                lastMatchResult="ok="+ok+", "+result.optString("message")+", map="+result.optString("map_id")+", floor="+result.optInt("floor")+", ms="+timings;
                if (ok) {
                    commitOnDisplay=result.optBoolean("commit_on_display");
                    if (!commitOnDisplay && !destroyed && requestEpoch == memoryEpoch && requestSerial == matchRequests.get()) {
                        boolean committed=bridge.callAttr("commit_match", token).toBoolean();
                        if(committed) android.util.Log.i("CrypticNotes", "Recognition memory committed: token="+token+", epoch="+requestEpoch+", map="+result.optString("map_id")+", floor="+result.optInt("floor"));
                    }
                    layer = readLayer(file, result.optInt("layer_width"), result.optInt("layer_height"));
                }
                if (offer != null) android.util.Log.i("CrypticNotes", "Cross-floor consent offered: "+offer);
                String message = result.optString("message");
                label = ok ? describe(result, message) : message;
                if (!ok) android.util.Log.i("CrypticNotes", "Recognition declined: token="+token+", result="+result);
            } catch (Exception error) {
                lastMatchResult="异常："+error.getClass().getSimpleName()+": "+error.getMessage();
                android.util.Log.e("CrypticNotes", "Recognition failed: token="+token,error);
            }
            final Bitmap decoded = layer;
            final boolean rememberDisplayed=commitOnDisplay;
            final String text = label;
            final JSONObject proposedOffer=offer;
            main.post(() -> {
                busy = false;
                if(startPendingMatch()){
                    if(decoded!=null)decoded.recycle();
                    return;
                }
                // Every completion ends the busy animation, even when a stale
                // request or a changed viewport suppresses presentation.
                // Closing only suppresses presentation. Reopening supersedes
                // the previous identity proposal before it can update memory.
                if (destroyed || requestSerial != matchRequests.get() || token != generation || !mapPanelOpen || MiniGameOverlayService.running) {
                    android.util.Log.i("CrypticNotes","Recognition presentation skipped: token="+token+", generation="+generation+", mapOpen="+mapPanelOpen+", destroyed="+destroyed);
                    if (decoded != null) decoded.recycle();
                    repoll(manualRetry ? 0 : WATCH_MS);
                    return;
                }
                if(state==S_MATCHING)setStatus(S_IDLE,null);
                if (decoded == null) {
                    if(proposedOffer!=null) {
                        setStatus(S_IDLE,null);collapseBadge();showManualPrompt(proposedOffer,token);
                        repoll(WATCH_MS);return;
                    }
                    android.util.Log.w("CrypticNotes","No overlay bitmap: token="+token+", offer="+(proposedOffer!=null)+", text="+text);
                    if (overlayLayer == null) setStatus(S_FAILED, text);
                    repoll(WATCH_MS);
                    return;
                }
                // Python took the better part of a second. If the viewport has
                // moved on since, this fit is aligned to a frame the player
                // already left; showing it would be a misaligned flash.
                Bitmap currentFrame=grab();
                int[] now=currentFrame!=null?signature(currentFrame):latestViewport.forReader(reader);
                if(currentFrame!=null)currentFrame.recycle();
                if (matchPixels == null || now == null
                        || difference(matchPixels, now) >= REALIGN_LIMIT) {
                    android.util.Log.i("CrypticNotes","Recognition viewport changed: token="+token+", previous="+(matchPixels!=null)+", current="+(now!=null));
                    decoded.recycle();
                    lastMatch = 0;
                    invalidateSamples();
                    repoll(WATCH_MS);
                    return;
                }
                replaceLayer(decoded);
                if(overlayAttached && !overlayHidden){
                    long elapsed=SystemClock.elapsedRealtime()-frame.captureStartedAt;
                    lastMatchResult+=", 取帧至挂上叠图="+elapsed+" ms";
                    android.util.Log.i("CrypticNotes","Overlay displayed: token="+token+", bitmap="+decoded.getWidth()+"x"+decoded.getHeight()+", capture_to_overlay_ms="+elapsed);
                    if(rememberDisplayed && requestEpoch==memoryEpoch)compute.execute(()->bridge.callAttr("commit_match",token));
                }
                setStatus(S_MATCHED, text);
                repoll(WATCH_MS);
            });
        });
    }

    /** Premultiplied RGBA written by the adapter -> the overlay Bitmap, with no codec in between. */
    private static Bitmap readLayer(File file, int width, int height) {
        if (width <= 0 || height <= 0) return BitmapFactory.decodeFile(file.toString());
        byte[] bytes;
        try (FileInputStream in = new FileInputStream(file)) {
            bytes = new byte[width * height * 4];
            int read = 0;
            while (read < bytes.length) {
                int n = in.read(bytes, read, bytes.length - read);
                if (n < 0) break;
                read += n;
            }
            if (read != bytes.length) return null;
        } catch (IOException e) { return null; }
        Bitmap layer = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
        layer.copyPixelsFromBuffer(ByteBuffer.wrap(bytes));
        return layer;
    }

    /**
     * "南-三缺一门 · 1F · 请核对路口" -- one short line.
     *
     * The strip is one line high, so a second line was never drawn; and the
     * caveat that the fit is provisional is carried by the message itself, which
     * the adapter keeps to a few characters.
     */
    private String describe(JSONObject result, String message) {
        String name = result.optString("name");
        if (name.isEmpty()) name = result.optString("map_id");
        StringBuilder label = new StringBuilder(name);
        if (result.has("floor") && !result.isNull("floor")) {
            int floor = result.optInt("floor");
            // 磷光症 is all basements, named 负一/二/三层 in the game.
            String text = scene.equals("linguang") && floor < 0 ? "负" + (-floor) + "层"
                    : floor == 1 ? "1F" : floor == 2 ? "2F" : floor == -1 ? "地下室" : floor + "F";
            label.append(" · ").append(text);
        }
        if (!message.isEmpty()) label.append(" · ").append(message);
        return label.toString();
    }

    private final GameSceneDetector gameSceneDetector=new GameSceneDetector();
    private final CaptureOverlayMask sceneOverlayMask=new CaptureOverlayMask();
    private String sceneWatchStatus="";
    private long sceneWatchLoggedAt;
    private void traceSceneWatch(String status){
        long now=SystemClock.elapsedRealtime();
        if(!status.equals(sceneWatchStatus)||now-sceneWatchLoggedAt>=15000){
            sceneWatchStatus=status;sceneWatchLoggedAt=now;
            android.util.Log.i("CrypticNotes","Mini-game scene watch: "+status);
        }
    }
    private long gameSceneSampleAt;
    private int sceneWidth,sceneHeight;
    private void watchMiniGameScene(){
        if(projection==null||reader==null||!getSharedPreferences("mobile",0).getBoolean("gameSceneEnabled",true)){gameSceneDetector.reset();return;}
        if(MiniGameOverlayService.hidden||quickSettings!=null){
            traceSceneWatch("paused: hidden or settings open");gameSceneDetector.reset();sceneOverlayMask.reset();return;
        }
        long now=SystemClock.elapsedRealtime();if(now-gameSceneSampleAt<1500)return;gameSceneSampleAt=now;
        if(width!=sceneWidth||height!=sceneHeight){gameSceneDetector.reset();sceneOverlayMask.reset();sceneWidth=width;sceneHeight=height;}
        int[] pixels=sampleViewport();if(pixels==null){traceSceneWatch("waiting for captured frame");return;}
        boolean[] excluded=new boolean[14400];
        MiniGameOverlayService game=MiniGameOverlayService.current;if(game==null)return;
        if(game.interacting()){traceSceneWatch("paused: window moving");gameSceneDetector.reset();return;}
        android.graphics.Rect area=game.visibleBounds();
        // Single-app projection excludes overlay windows, even while the selected
        // app is marked occluded. Compare actual pixels before masking our bounds.
        boolean includeOverlay=sceneOverlayMask.includesOverlay(pixels,game.sceneOverlaySignature(width,height));
        if(includeOverlay){
            gameSceneDetector.reset();
            traceSceneWatch("disabled: capture includes mini-game window (whole-screen sharing)");
            return;
        }
        for(int y=0;y<90;y++)for(int x=0;x<160;x++){
            int sx=x*width/160,sy=y*height/90;
            boolean overGame=sx>=area.left-8&&sx<area.right+8&&sy>=area.top-8&&sy<area.bottom+8;
            boolean overBadge=badgeParams!=null&&sx>=badgeParams.x-8&&sx<badgeParams.x+badgeParams.width+8&&sy>=badgeParams.y-8&&sy<badgeParams.y+badgeParams.height+8;
            excluded[y*160+x]=includeOverlay&&(overGame||overBadge);
        }
        if(gameSceneDetector.feed(pixels,excluded)){
            traceSceneWatch("major change detected; auto-hide");
            startForegroundService(new Intent(this,MiniGameOverlayService.class).setAction("auto-hide"));
            Toast.makeText(this,"游戏画面明显变化，小游戏已收起；5秒内恢复可继续",Toast.LENGTH_SHORT).show();
        }else traceSceneWatch((includeOverlay?"overlay pixels masked; ":"capture excludes overlay; ")+gameSceneDetector.status());
    }

    private Bitmap cleanCaptureFrame;
    private ImageReader cleanCaptureReader;
    private int[] cleanCaptureSignature;
    private long freshCaptureCount;
    private Bitmap grab() {
        if(recorder!=null) recorder.requestPreview();
        try (Image image = reader.acquireLatestImage()) {
            if (image == null) {
                if(cleanCaptureFrame!=null&&cleanCaptureReader==reader&&FrameReuse.same(cleanCaptureSignature,latestViewport.forReader(reader),false))
                    return cleanCaptureFrame.copy(Bitmap.Config.ARGB_8888,true);
                return null;
            }
            freshCaptureCount++;lastFreshFrameAt=SystemClock.elapsedRealtime();
            Image.Plane plane = image.getPlanes()[0];
            ByteBuffer bytes = plane.getBuffer();
            bytes.rewind();
            // Pack the valid rows straight into a tight Bitmap: one copy instead
            // of a padded full-screen Bitmap plus a cropped duplicate.
            Bitmap full = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
            full.copyPixelsFromBuffer(RgbaRows.packed(bytes, width, height, plane.getRowStride()));
            int[] sampled=signature(full);
            latestViewport.remember(reader,sampled);
            if(overlay==null||overlay.getVisibility()!=View.VISIBLE){
                if(cleanCaptureFrame!=null)cleanCaptureFrame.recycle();
                cleanCaptureFrame=full.copy(Bitmap.Config.ARGB_8888,false);
                cleanCaptureReader=reader;cleanCaptureSignature=sampled;
            }
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
        if(tapRegion!=null){windows.removeView(tapRegion);tapRegion=null;}
        if(automaticMapProbe())scheduleIdleProbe();
        else{main.removeCallbacks(idleProbeTick);idleProbeScheduled=false;idleProbe.cancel();}
    }

    /**
     * The in-game panel. Everything a match needs, on one screen.
     *
     * Deliberately compact: a phone held sideways has no height to spare, so
     * the panel is sized to fit without scrolling and the three actions share a
     * single row. The dismiss control is a cross in the corner rather than a
     * button at the bottom, which is what freed the height for that.
     */
    private void showQuickSettings() {
        if (destroyed || quickSettings != null || calibration != null) return;
        clearOverlay();
        // The button stays on screen: tapping it again is the other way out.
        if (tapRegion != null) { windows.removeView(tapRegion); tapRegion = null; }
        SharedPreferences prefs = getSharedPreferences("mobile", 0);
        Theme.MistPanel shell = new Theme.MistPanel(this);
        int pad = Theme.px(this, 14);
        shell.setPadding(0,0,0,0);
        DraggableHeader header = new DraggableHeader(this);
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(pad, 0, pad, 0);
        final String homeModule=pvp?"pvp":"notes";
        DarkTab settingsTab=new DarkTab(this,pvp?"禁选辅助":"加页手记");settingsTab.select(true);
        DarkTab gamesTab=new DarkTab(this,"小游戏");
        settingsTab.setUpdate(pvp?ModuleUpdates.flag(this,"pvp"):ModuleUpdates.flag(this,"notes")||ModuleUpdates.flag(this,"zhanshi")||ModuleUpdates.flag(this,"lianghapi"));
        gamesTab.setUpdate(ModuleUpdates.flag(this,"games")||MiniGameUpdates.available(this));
        final boolean gamesOnlyMenu=gameOnly||MiniGameOverlayService.running;
        header.addView(settingsTab,new LinearLayout.LayoutParams(0,Theme.px(this,40),1));
        settingsTab.setVisibility(gamesOnlyMenu?View.GONE:View.VISIBLE);
        LinearLayout.LayoutParams tabParams=new LinearLayout.LayoutParams(0,Theme.px(this,40),1);tabParams.setMargins(Theme.px(this,6),0,Theme.px(this,6),0);
        header.addView(gamesTab,tabParams);
        HeaderClose dismiss = new HeaderClose(this);
        TextView general=new TextView(this);ActionIcon.set(general,ActionIcon.GEAR,false);header.addView(general,new LinearLayout.LayoutParams(Theme.px(this,34),Theme.px(this,34)));general.setOnClickListener(v->{closeQuickSettings();startActivity(new Intent(this,MainActivity.class).putExtra("open_module","settings").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_SINGLE_TOP));});
        header.addView(dismiss, new LinearLayout.LayoutParams(Theme.px(this, 34), Theme.px(this, 34)));
        shell.addView(header, new LinearLayout.LayoutParams(-1, Theme.px(this, 44)));

        Theme.MistPanel panel = new Theme.MistPanel(this);
        panel.setPadding(pad, 0, pad, pad);
        ScrollView scroll = new ScrollView(this);
        scroll.addView(panel, new ScrollView.LayoutParams(-1, -2));
        FrameLayout pages=new FrameLayout(this);
        pages.addView(scroll,new FrameLayout.LayoutParams(-1,-1));
        LinearLayout gamePage=new LinearLayout(this);gamePage.setOrientation(1);gamePage.setPadding(pad,Theme.px(this,14),pad,pad);
        if(new MatchingModuleStore(this,"games").installed())for(String gameId:GameCatalog.ids(this)){
            MiniGameStore store=new MiniGameStore(this,gameId);
            LinearLayout row=new LinearLayout(this);row.setGravity(Gravity.CENTER_VERTICAL);
            GameIcons.addTo(row,gameId);row.addView(label(store.title(),16,Theme.TITLE,0),new LinearLayout.LayoutParams(0,-2,1));
            Theme.ChalkButton launch=button(MiniGameOverlayService.running&&gameId.equals(MiniGameOverlayService.activeGameId)?"回到游戏":"打开",true);row.addView(launch);
            launch.setOnClickListener(v->{
                if(!store.installed()){Toast.makeText(this,"请在应用内下载该小游戏",Toast.LENGTH_SHORT).show();return;}
                closeQuickSettings();startActivity(new Intent(this,MainActivity.class).putExtra("launch_game",gameId).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_SINGLE_TOP));
            });gamePage.addView(row);
        }
        if(gamePage.getChildCount()==0)gamePage.addView(label("暂无小游戏",14,Theme.MUTED,0));
        pages.addView(gamePage,new FrameLayout.LayoutParams(-1,-1));gamePage.setVisibility(View.GONE);
        settingsTab.setOnClickListener(v->{scroll.setVisibility(View.VISIBLE);gamePage.setVisibility(View.GONE);settingsTab.select(true);gamesTab.select(false);prefs.edit().putString("last_module",homeModule).apply();});
        gamesTab.select(false);
        gamesTab.setOnClickListener(v->{scroll.setVisibility(View.GONE);gamePage.setVisibility(View.VISIBLE);settingsTab.select(false);gamesTab.select(true);prefs.edit().putString("last_module","games").apply();});
        if(gamesOnlyMenu||prefs.getString("last_module","notes").equals("games")){scroll.setVisibility(View.GONE);gamePage.setVisibility(View.VISIBLE);settingsTab.select(false);gamesTab.select(true);}
        if(new MatchingModuleStore(this,"games").installed())MiniGameUpdates.check(this,()->{if(!destroyed&&quickSettings==shell)gamesTab.setUpdate(ModuleUpdates.flag(this,"games")||MiniGameUpdates.available(this));});
        shell.addView(pages,new LinearLayout.LayoutParams(-1,0,1));
        dismiss.setOnClickListener(v -> closeQuickSettings());

        preparationLabel = label(preparationText, 13, Theme.MUTED, 6);
        preparationLabel.setVisibility(initializing ? View.VISIBLE : View.GONE);
        panel.addView(preparationLabel);

        String modeValue = prefs.getString("mode", "solo");

        MapLibraryChoice libraryChoice=new MapLibraryChoice(this);libraryChoice.detachProvider();panel.addView(libraryChoice);
        Theme.ChalkChoice difficulty = new Theme.ChalkChoice(this, new String[]{"困难", "噩梦"});
        libraryChoice.refreshDifficulty(difficulty);
        LinearLayout difficultyRow=new LinearLayout(this);difficultyRow.setGravity(Gravity.CENTER_VERTICAL);
        difficultyRow.addView(label("难度",14,Theme.MUTED,0),new LinearLayout.LayoutParams(Theme.px(this,56),-2));
        difficultyRow.addView(difficulty,new LinearLayout.LayoutParams(Theme.px(this,170),Theme.px(this,42)));panel.addView(difficultyRow);panel.addView(libraryChoice.detachRoute());

        TextView routeLabel = label("参考路线", 14, Theme.MUTED, 6);

        Theme.ChalkChoice party = new Theme.ChalkChoice(this, new String[]{"单人", "多人"});
        party.setIndex(modeValue.equals("duo") ? 1 : 0);
        LinearLayout routeRow=new LinearLayout(this);routeRow.setGravity(Gravity.CENTER_VERTICAL);
        routeRow.addView(routeLabel,new LinearLayout.LayoutParams(Theme.px(this,82),-2));
        routeRow.addView(party,new LinearLayout.LayoutParams(Theme.px(this,144),Theme.px(this,42)));panel.addView(routeRow);
        party.setVisibility(difficulty.getIndex() == 1 ? View.VISIBLE : View.GONE);
        routeRow.setVisibility(party.getVisibility());

        // The two choices above cost a matcher rebuild, so what is actually in
        // force needs a line of its own -- without it, closing the panel looks
        // like the change was dropped.
        TextView applied = label("当前：" + difficultyLabel(libraryChoice.selected(difficulty), modeValue), 13, Theme.MUTED, 6);
        panel.addView(applied);
        Theme.ChalkChoice.Listener apply = i -> {
            boolean nightmare = libraryChoice.selected(difficulty).equals("nightmare");
            difficultyRow.setVisibility(View.VISIBLE);
            party.setVisibility(libraryChoice.hasParty()&&nightmare ? View.VISIBLE : View.GONE);
            routeRow.setVisibility(party.getVisibility());
            applyRecognition(libraryChoice.selected(difficulty),
                    libraryChoice.mode(party.getIndex() == 0 ? "solo" : "duo"), applied);
        };
        difficulty.setListener(apply);
        party.setListener(apply);
        libraryChoice.changed=()->{libraryChoice.refreshDifficulty(difficulty);apply.onChanged(0);};
        difficultyRow.setVisibility(View.VISIBLE);
        if(!libraryChoice.hasParty()||!libraryChoice.selected(difficulty).equals("nightmare")){party.setVisibility(View.GONE);routeRow.setVisibility(View.GONE);}
        LinearLayout actions = new LinearLayout(this);
        LinearLayout.LayoutParams actionParams = new LinearLayout.LayoutParams(0, Theme.px(this, 42), 1f);
        actionParams.topMargin = Theme.px(this, 10);
        actionParams.rightMargin = Theme.px(this, 6);
        Theme.ChalkButton retry = button("重新识别", true);
        actions.addView(retry, actionParams);
        retry.setOnClickListener(v -> retryFromBadge());
        LinearLayout.LayoutParams middleParams = new LinearLayout.LayoutParams(0, Theme.px(this, 42), 1f);
        middleParams.topMargin = Theme.px(this, 10);
        Theme.ChalkButton hideLayer = button(overlayHidden ? "显示叠图" : "隐藏叠图", false);
        actions.addView(hideLayer, middleParams);
        hideLayer.setOnClickListener(v -> {
            setOverlayHidden(!overlayHidden);
            hideLayer.setText(overlayHidden ? "显示叠图" : "隐藏叠图");
        });
        actions.setPadding(0,0,0,Theme.px(this,8));
        int actionIndex=panel.indexOfChild(routeRow)+1;
        panel.addView(actions,actionIndex,new LinearLayout.LayoutParams(-1,-2));
        if(pvp){
            buildPvpPanel(panel,prefs);
        }else if(gameOnly||!new MatchingModuleStore(this).installed()){
            panel.removeAllViews();panel.addView(label(gameOnly?"当前为小游戏专用悬浮窗，不进行地图识别":"请先下载加页手记模块",14,Theme.MUTED,8));
            Theme.ChalkButton maps=button("前往加页手记",true);panel.addView(maps);maps.setOnClickListener(v->{closeQuickSettings();startActivity(new Intent(this,MainActivity.class).putExtra("open_module","notes").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_SINGLE_TOP));});
        }
        recordButton=button("屏幕录制",true);updateRecordingButton();recordButton.setOnClickListener(v->{if(projection==null){Toast.makeText(this,"录屏需要先在应用内开启屏幕共享",Toast.LENGTH_SHORT).show();return;}toggleRecording();});
        LinearLayout.LayoutParams recordParams=new LinearLayout.LayoutParams(-1,Theme.px(this,46));recordParams.setMargins(pad,Theme.px(this,10),pad,pad);
        if(!gameOnly && RecordPresets.storedReplaySeconds(this)>0){
            // Side by side: the panel has a fixed height, a second row would squeeze the settings above.
            replayButton=button(RecordPresets.replayLabel(RecordPresets.storedReplaySeconds(this)),true);
            replayButton.setOnClickListener(v->{saveReplay();closeQuickSettings();});
            LinearLayout recordRow=new LinearLayout(this);recordRow.setOrientation(LinearLayout.HORIZONTAL);
            recordRow.addView(replayButton,new LinearLayout.LayoutParams(0,-1,1));
            LinearLayout.LayoutParams beside=new LinearLayout.LayoutParams(0,-1,1);beside.leftMargin=Theme.px(this,8);
            recordRow.addView(recordButton,beside);
            shell.addView(recordRow,recordParams);
            updateRecordingButton();
        }else{replayButton=null;shell.addView(recordButton,recordParams);}

        quickSettings = shell;
        WindowManager.LayoutParams p = params(Math.min(width - pad * 2, Theme.px(this, 320)),
                Math.min(height - pad * 2, Theme.px(this, 380)), true);
        p.x = (width - p.width) / 2;
        // Park it on the side the button is not: the ball has to stay tappable
        // to be a second way out of here.
        boolean ballBelow = badgeParams.y + ballWidth / 2 > height / 2;
        p.y = ballBelow ? Theme.px(this, 12) : Math.max(Theme.px(this, 12), height - p.height - Theme.px(this, 12));
        header.mover=(dx,dy)->{p.x=Math.max(0,Math.min(width-p.width,p.x+dx));p.y=Math.max(0,Math.min(height-p.height,p.y+dy));windows.updateViewLayout(shell,p);};
        windows.addView(shell, p);
        shell.setAlpha(0f); shell.setTranslationY(Theme.px(this, 6));
        shell.animate().alpha(1f).translationY(0f).setDuration(150)
                .setInterpolator(new android.view.animation.DecelerateInterpolator()).start();
    }

    /**
     * Retune the live overlay. Shared with the home screen through the same
     * preference key, so whichever control was touched last is the one that
     * takes effect on the next start.
     */
    private void applyOpacity(int percent) {
        opacity = Math.max(.05f, Math.min(.70f, percent / 100f));
        if (overlayParams != null) {
            overlayParams.alpha = opacity;
            try { windows.updateViewLayout(overlay, overlayParams); } catch (Exception ignored) {}
        }
        getSharedPreferences("mobile", 0).edit().putInt("opacity", percent).apply();
    }

    /**
     * Persist a difficulty or route change and rebuild the matcher.
     *
     * Rebuilding is what makes the change take effect and it costs about a
     * second, so it runs on the worker while the panel stays open. Doing it only
     * from the "重新识别" button -- as it was -- meant picking a difficulty and
     * closing the panel changed nothing at all.
     */
    private void applyRecognition(String difficulty, String mode, TextView applied) {
        if(gameOnly||bridge==null){applied.setText("小游戏模式不进行地图识别");return;}
        scene=MapLibraryChoice.sceneOf(getSharedPreferences("mobile",0));
        final String provider=MapLibraryChoice.providerOf(getSharedPreferences("mobile",0));
        final String applyScene=scene;
        getSharedPreferences("mobile",0).edit().putString("difficulty",difficulty).apply();
        if(provider.equals("lianghapi"))getSharedPreferences("mobile", 0).edit().putString("mode", mode).apply();
        final int token = ++applyToken;
        clearOverlay();setSpinning(false);
        applying = true;
        ready = false;
        applied.setText("正在应用…");
        compute.execute(() -> {
            String error = null;
            try {
                if(!new MatchingModuleStore(this,provider).installed())throw new IOException("请在地图设置下载"+MapLibraryChoice.title(provider)+"地图库");
                loadedMapCount=bridge.callAttr("initialize", getFilesDir().toString(), difficulty, mode, provider, applyScene).toInt();
            } catch (Exception e) {
                error = e.getMessage();
            }
            final String failure = error;
            main.post(() -> {
                // A later change owns the panel now; it will report for itself.
                if (destroyed || token != applyToken) return;
                applying = false;
                ready = failure == null;
                lastMatch = 0;
                applied.setText(failure == null
                        ? "已应用：" + difficultyLabel(difficulty, mode)
                        : "设置失败："+failure);
                repoll(100);
            });
        });
    }

    /** Which game map the matcher was built for; see MapLibraryChoice. */
    private volatile String scene="curse";

    private String difficultyLabel(String difficulty, String mode) {
        if(MapLibraryChoice.providerOf(getSharedPreferences("mobile",0)).equals("original"))return "小布偶 · "+MapLibraryChoice.levelName(difficulty);
        if(scene.equals("linguang")) return "磷光症 · "+(!"full".equals(mode)?("nightmare".equals(difficulty)?"凉哈皮 · 噩梦":"凉哈皮 · 困难"):"nightmare".equals(difficulty)?"展十 · 噩梦 · 十四棺":"展十 · 困难 · 十六棺");
        return (difficulty.equals("nightmare") ? "噩梦" : "困难")
                + " · " + (mode.equals("full") ? "展十全棺" : mode.equals("speed") ? "展十速刷" : mode.equals("duo") ? "多人路线" : "单人路线");
    }

    /** Panel text, slightly larger than the home screen's but kept compact. */
    private TextView label(String value, float sizeDp, int color, float topMarginDp) {
        TextView view = Theme.muted(this, value);
        view.setTextSize(android.util.TypedValue.COMPLEX_UNIT_DIP, sizeDp);
        view.setTextColor(color);
        if (topMarginDp > 0) {
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
            params.topMargin = Theme.px(this, topMarginDp);
            view.setLayoutParams(params);
        }
        return view;
    }

    private Theme.ChalkButton button(String text, boolean primary) {
        Theme.ChalkButton view = new Theme.ChalkButton(this, text, primary);
        view.setMinHeight(Theme.px(this, 42));
        return view;
    }

    private void closeQuickSettings() {
        if (quickSettings != null) { windows.removeView(quickSettings); quickSettings = null; }
        preparationLabel = null;
        badge.setVisibility(View.VISIBLE); refreshTapRegion();
        if (!applying) repoll(200);
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

    @Override public void onConfigurationChanged(Configuration c) {
        super.onConfigurationChanged(c);
        if (quickSettings != null) closeQuickSettings();
        if (calibration != null) finishCalibration();
        if (projection != null) resizeCapture();
        else if(badge!=null){DisplayMetrics m=new DisplayMetrics();windows.getDefaultDisplay().getRealMetrics(m);width=m.widthPixels;height=m.heightPixels;layoutBadge();}
    }

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
        idleProbe.close();
        if(cleanCaptureFrame!=null){cleanCaptureFrame.recycle();cleanCaptureFrame=null;}
        stopRecording();
        if (current == this) current = null;
        generation++;
        main.removeCallbacksAndMessages(null);
        dismissManualPrompt();
        if (spin != null) spin.cancel();
        if (recordingPulse != null) recordingPulse.cancel();
        if (bubbleAnim != null) bubbleAnim.cancel();
        if (display != null) display.release();
        if (reader != null && recorder == null) reader.close();
        if (projection != null) projection.stop();
        if (overlay != null) windows.removeView(overlay);
        if (badge != null) windows.removeView(badge);
        if (tapRegion != null) windows.removeView(tapRegion);
        if (calibration != null) windows.removeView(calibration);
        if (quickSettings != null) windows.removeView(quickSettings);
        if (pvpPicker != null) windows.removeView(pvpPicker);
        if (pvpHud != null) windows.removeView(pvpHud);
        closePvpBars();
        if (pvpEntry != null) windows.removeView(pvpEntry);
        if (pvpTestReceiver != null) unregisterReceiver(pvpTestReceiver);
        compute.shutdownNow();
        inspect.shutdownNow();
        super.onDestroy();
    }
}
