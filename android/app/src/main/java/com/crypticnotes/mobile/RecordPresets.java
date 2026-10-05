package com.crypticnotes.mobile;

import android.content.Context;

/**
 * The one place that turns a recording choice into encoder numbers.
 *
 * These used to be literals inside {@link SharedScreenRecorder} -- 1280, 24 and
 * 4 Mbps -- with no way to ask for anything else. A phone recording too small to
 * read is the usual complaint, so quality and frame rate became settings; the
 * mapping lives here so the settings screen and the encoder cannot disagree
 * about what a label means.
 *
 * The defaults are deliberately the old fixed behaviour, so an installation that
 * never opens the recording screen records exactly what it recorded before.
 */
final class RecordPresets {
    private RecordPresets() { }

    static final String KEY_QUALITY = "record_quality";
    static final String KEY_FPS = "record_fps";
    static final String KEY_AUDIO = "record_internal_audio";

    /** Stored as names, not indexes, like `difficulty`/`mode`: reordering a table
     *  then cannot silently remap what existing users already chose. */
    static final String[] QUALITY_IDS = {"low", "standard", "high"};
    static final String[] QUALITY_LABELS = {"流畅", "标准", "高清"};
    /** Cap on the longer side, in pixels. Never used to scale a video up. */
    static final int[] QUALITY_LONG_SIDE = {720, 1280, 1920};
    static final int[] QUALITY_BITRATE = {2_000_000, 4_000_000, 8_000_000};

    static final int[] FPS_VALUES = {24, 30, 60};
    static final String[] FPS_LABELS = {"24 帧", "30 帧", "60 帧"};

    static final String DEFAULT_QUALITY_ID = "standard";
    static final int DEFAULT_FPS = 24;

    static int qualityIndex(String id) {
        for (int i = 0; i < QUALITY_IDS.length; i++) if (QUALITY_IDS[i].equals(id)) return i;
        return indexOf(DEFAULT_QUALITY_ID);
    }

    static String qualityId(int index) { return QUALITY_IDS[clamp(index, QUALITY_IDS.length, indexOf(DEFAULT_QUALITY_ID))]; }

    static int fpsIndex(int fps) {
        for (int i = 0; i < FPS_VALUES.length; i++) if (FPS_VALUES[i] == fps) return i;
        return fpsIndex(DEFAULT_FPS);
    }

    static int fpsValue(int index) { return FPS_VALUES[clamp(index, FPS_VALUES.length, fpsIndex(DEFAULT_FPS))]; }

    private static int indexOf(String id) {
        for (int i = 0; i < QUALITY_IDS.length; i++) if (QUALITY_IDS[i].equals(id)) return i;
        return 0;
    }

    /** An out-of-range index means a preference written by a newer build; fall back. */
    private static int clamp(int index, int length, int fallback) {
        return index >= 0 && index < length ? index : fallback;
    }

    private static android.content.SharedPreferences prefs(Context context) {
        return context.getSharedPreferences("mobile", 0);
    }

    static int storedQualityIndex(Context context) {
        return qualityIndex(prefs(context).getString(KEY_QUALITY, DEFAULT_QUALITY_ID));
    }

    static void setQualityIndex(Context context, int index) {
        prefs(context).edit().putString(KEY_QUALITY, qualityId(index)).apply();
    }

    static int storedFpsIndex(Context context) {
        return fpsIndex(prefs(context).getInt(KEY_FPS, DEFAULT_FPS));
    }

    static void setFpsIndex(Context context, int index) {
        prefs(context).edit().putInt(KEY_FPS, fpsValue(index)).apply();
    }

    /** Exactly what the user chose. Positions the switch, and nothing else. */
    static boolean storedInternalAudio(Context context) {
        return prefs(context).getBoolean(KEY_AUDIO, true);
    }

    static void setInternalAudio(Context context, boolean value) {
        prefs(context).edit().putBoolean(KEY_AUDIO, value).apply();
    }

    /**
     * What the recorder can actually use.
     *
     * Playback capture needs Android 10 and the recording permission. Handing the
     * raw preference to the recorder would make it warn "internal sound
     * unavailable" at the start of every single recording for anyone who simply
     * never granted the permission -- a warning that then means nothing on the
     * day it is real. Deciding here keeps that warning for genuine failures.
     */
    static boolean internalAudio(Context context) {
        return storedInternalAudio(context)
                && android.os.Build.VERSION.SDK_INT >= 29
                && context.checkSelfPermission(android.Manifest.permission.RECORD_AUDIO)
                   == android.content.pm.PackageManager.PERMISSION_GRANTED;
    }

    /** One line describing the current choice, for the settings screen. */
    static String describe(int quality, int fps) {
        int index = clamp(quality, QUALITY_IDS.length, indexOf(DEFAULT_QUALITY_ID));
        return "最长边 " + QUALITY_LONG_SIDE[index] + " 像素、" + fps + " 帧、"
                + (QUALITY_BITRATE[index] / 1_000_000)
                + " Mbps，H.264。只影响录屏文件，不影响识图。设备编码器不支持时会自动降档并提示。";
    }

    /** Encoder settings for one recording session, read once when it starts. */
    static final class Settings {
        final boolean audio;
        final int quality, fps;
        Settings(boolean audio, int quality, int fps) {
            this.audio = audio; this.quality = quality; this.fps = fps;
        }
    }

    static Settings snapshot(Context context) {
        return new Settings(internalAudio(context), storedQualityIndex(context), fpsValue(storedFpsIndex(context)));
    }
}
