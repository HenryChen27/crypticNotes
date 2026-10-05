package com.crypticnotes.mobile;

import android.content.*;
import android.graphics.SurfaceTexture;
import android.media.*;
import android.media.projection.MediaProjection;
import android.net.Uri;
import android.opengl.*;
import android.os.*;
import android.provider.MediaStore;
import android.view.Surface;
import java.io.*;
import java.nio.*;

/** One projection surface, GPU fan-out to the existing ImageReader and AVC.
 * No second MediaProjection/VirtualDisplay; optional playback audio, never mic.
 * All GL/codec resources are confined to the recording thread.
 */
final class SharedScreenRecorder {
    interface Listener {
        void ready(Surface input);
        void finished(String location, String error);
        default void warning(String text) {}
    }
    private final Context context;
    private final Surface recognition;
    private final int width, height;
    private final Listener listener;
    private final MediaProjection projection;
    private final boolean wantAudio;
    /** Chosen on the settings screen; clamped to the encoder's range further down. */
    private final int wantedQuality, wantedFps;
    private AudioRecord audioRecord;
    private MediaCodec audioCodec;
    private int audioTrack=-1;
    private volatile boolean audioEnabled;
    private boolean audioStarted;
    private long audioFrames, audioOffsetUs;
    private final java.util.ArrayDeque<PendingSample> pendingSamples=new java.util.ArrayDeque<>();
    private int pendingBytes;
    boolean hasAudio() { return audioEnabled; }
    private static class PendingSample {
        final int track; final ByteBuffer bytes; final MediaCodec.BufferInfo info=new MediaCodec.BufferInfo();
        PendingSample(int track,ByteBuffer source,MediaCodec.BufferInfo metadata) {
            this.track=track; bytes=ByteBuffer.allocate(metadata.size); bytes.put(source); bytes.flip();
            info.set(0,metadata.size,metadata.presentationTimeUs,metadata.flags);
        }
    }
    private final Handler main = new Handler(Looper.getMainLooper());
    private final HandlerThread thread = new HandlerThread("shared-screen-recorder");
    private Handler handler;
    private EGLDisplay egl = EGL14.EGL_NO_DISPLAY;
    private EGLContext gl = EGL14.EGL_NO_CONTEXT;
    private EGLSurface preview = EGL14.EGL_NO_SURFACE, video = EGL14.EGL_NO_SURFACE;
    private Surface input, encoderSurface;
    private SurfaceTexture texture;
    private MediaCodec codec;
    private MediaMuxer muxer;
    private ParcelFileDescriptor descriptor;
    private Uri uri;
    private File file;
    private int textureId, program, track = -1, videoWidth, videoHeight, videoFps, videoBitrate;
    private boolean muxing, ended, samples;
    private final java.util.concurrent.atomic.AtomicBoolean previewRequested = new java.util.concurrent.atomic.AtomicBoolean(true);
    private volatile boolean stopRequested;
    void requestPreview() { previewRequested.set(true); }
    private long firstNanos, lastNanos;
    private final float[] transform = new float[16];
    private final FloatBuffer vertices = ByteBuffer.allocateDirect(16*4).order(ByteOrder.nativeOrder())
            .asFloatBuffer().put(new float[]{-1,-1,0,0, 1,-1,1,0, -1,1,0,1, 1,1,1,1});

    SharedScreenRecorder(Context context, Surface recognition, int width, int height, MediaProjection projection,
                         RecordPresets.Settings settings, Listener listener) {
        this.context=context.getApplicationContext(); this.recognition=recognition;
        this.width=width; this.height=height; this.listener=listener;
        this.projection=projection; this.wantAudio=settings.audio;
        this.wantedQuality=settings.quality; this.wantedFps=settings.fps;
    }
    void start() {
        thread.start(); handler=new Handler(thread.getLooper());
        handler.post(() -> {
            try { prepare(); main.post(() -> listener.ready(input)); }
            catch(Exception e) { finish(e); }
        });
    }
    void stop() { stopRequested=true; if(handler!=null) handler.post(() -> finish(null)); }

    private void prepare() throws Exception {
        codec=MediaCodec.createEncoderByType("video/avc");
        MediaCodecInfo.VideoCapabilities caps=codec.getCodecInfo().getCapabilitiesForType("video/avc").getVideoCapabilities();
        chooseVideoFormat(caps);
        MediaFormat format=MediaFormat.createVideoFormat("video/avc",videoWidth,videoHeight);
        format.setInteger(MediaFormat.KEY_COLOR_FORMAT,MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface);
        format.setInteger(MediaFormat.KEY_BIT_RATE,videoBitrate);
        format.setInteger(MediaFormat.KEY_FRAME_RATE,videoFps);
        format.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL,2);
        codec.configure(format,null,null,MediaCodec.CONFIGURE_FLAG_ENCODE);
        encoderSurface=codec.createInputSurface(); codec.start();
        String name="CrypticNotes-"+System.currentTimeMillis()+".mp4";
        if(Build.VERSION.SDK_INT>=29) {
            ContentValues values=new ContentValues();
            values.put(MediaStore.Video.Media.DISPLAY_NAME,name);
            values.put(MediaStore.Video.Media.MIME_TYPE,"video/mp4");
            values.put(MediaStore.Video.Media.RELATIVE_PATH,"Movies/CrypticNotes");
            values.put(MediaStore.Video.Media.IS_PENDING,1);
            uri=context.getContentResolver().insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI,values);
            if(uri==null) throw new IOException("无法创建录屏文件");
            descriptor=context.getContentResolver().openFileDescriptor(uri,"w");
            if(descriptor==null) throw new IOException("无法打开录屏文件");
            muxer=new MediaMuxer(descriptor.getFileDescriptor(),MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);
        } else {
            File directory=context.getExternalFilesDir(Environment.DIRECTORY_MOVIES);
            if(directory==null) throw new IOException("视频存储不可用");
            file=new File(directory,name);
            muxer=new MediaMuxer(file.toString(),MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);
        }
        egl=EGL14.eglGetDisplay(EGL14.EGL_DEFAULT_DISPLAY);
        if(!EGL14.eglInitialize(egl,new int[2],0,new int[2],0)) throw new IOException("无法初始化录屏 GPU");
        EGLConfig[] configs=new EGLConfig[1]; int[] count=new int[1];
        int[] attrs={EGL14.EGL_RED_SIZE,8,EGL14.EGL_GREEN_SIZE,8,EGL14.EGL_BLUE_SIZE,8,
                EGL14.EGL_ALPHA_SIZE,8,EGL14.EGL_RENDERABLE_TYPE,EGL14.EGL_OPENGL_ES2_BIT,
                EGL14.EGL_SURFACE_TYPE,EGL14.EGL_WINDOW_BIT,0x3142,1,EGL14.EGL_NONE};
        if(!EGL14.eglChooseConfig(egl,attrs,0,configs,0,1,count,0) || count[0]==0) throw new IOException("设备不支持共享录屏表面");
        gl=EGL14.eglCreateContext(egl,configs[0],EGL14.EGL_NO_CONTEXT,new int[]{EGL14.EGL_CONTEXT_CLIENT_VERSION,2,EGL14.EGL_NONE},0);
        preview=EGL14.eglCreateWindowSurface(egl,configs[0],recognition,new int[]{EGL14.EGL_NONE},0);
        video=EGL14.eglCreateWindowSurface(egl,configs[0],encoderSurface,new int[]{EGL14.EGL_NONE},0);
        current(preview);
        int[] id=new int[1]; GLES20.glGenTextures(1,id,0); textureId=id[0];
        GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES,textureId);
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES,GLES20.GL_TEXTURE_MIN_FILTER,GLES20.GL_LINEAR);
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES,GLES20.GL_TEXTURE_MAG_FILTER,GLES20.GL_LINEAR);
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES,GLES20.GL_TEXTURE_WRAP_S,GLES20.GL_CLAMP_TO_EDGE);
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES,GLES20.GL_TEXTURE_WRAP_T,GLES20.GL_CLAMP_TO_EDGE);
        int vs=shader(GLES20.GL_VERTEX_SHADER,"attribute vec4 position; attribute vec2 tex; uniform mat4 transform; varying vec2 uv; void main(){gl_Position=position; uv=(transform*vec4(tex,0.,1.)).xy;}");
        int fs=shader(GLES20.GL_FRAGMENT_SHADER,"#extension GL_OES_EGL_image_external : require\nprecision mediump float; uniform samplerExternalOES image; varying vec2 uv; void main(){gl_FragColor=texture2D(image,uv);}");
        program=GLES20.glCreateProgram(); GLES20.glAttachShader(program,vs); GLES20.glAttachShader(program,fs);
        GLES20.glLinkProgram(program); GLES20.glDeleteShader(vs); GLES20.glDeleteShader(fs);
        int[] linked=new int[1]; GLES20.glGetProgramiv(program,GLES20.GL_LINK_STATUS,linked,0);
        if(linked[0]==0) throw new IOException("录屏着色器链接失败");
        texture=new SurfaceTexture(textureId); texture.setDefaultBufferSize(width,height);
        input=new Surface(texture);
        texture.setOnFrameAvailableListener(t -> frame(),handler);
        if(wantAudio) prepareAudio();
    }

    /**
     * Pick a size, bit rate and frame rate this device's encoder will accept.
     *
     * The size rule is unchanged from when it was a literal: never scale up,
     * round down to the codec's alignment, floor at one alignment unit. What is
     * new is what happens when the device says no. It used to be one hard
     * failure; now an unsupported frame rate is clamped to the nearest supported
     * one, and an unsupported size steps down a quality tier before giving up.
     * A mid-range phone that cannot do 1080p60 should still record something.
     */
    private void chooseVideoFormat(MediaCodecInfo.VideoCapabilities caps) throws IOException {
        for(int tier=wantedQuality; tier>=0; tier--) {
            double scale=Math.min(1.,RecordPresets.QUALITY_LONG_SIDE[tier]/(double)Math.max(width,height));
            int w=Math.max(caps.getWidthAlignment(),(int)(width*scale)/caps.getWidthAlignment()*caps.getWidthAlignment());
            int h=Math.max(caps.getHeightAlignment(),(int)(height*scale)/caps.getHeightAlignment()*caps.getHeightAlignment());
            // isSizeSupported first: areSizeAndRateSupported throws on some vendor
            // codecs for a size the device does not know at all.
            if(!caps.isSizeSupported(w,h)) continue;
            int fps=wantedFps;
            if(!caps.areSizeAndRateSupported(w,h,fps)) fps=clampFrameRate(caps,w,h,fps);
            videoWidth=w; videoHeight=h; videoFps=fps; videoBitrate=RecordPresets.QUALITY_BITRATE[tier];
            if(tier!=wantedQuality) warn("设备不支持所选画质，本次已自动降档");
            if(fps!=wantedFps) warn("当前画质不支持 "+wantedFps+" 帧，本次改为 "+fps+" 帧");
            return;
        }
        throw new IOException("设备编码器不支持当前录制尺寸");
    }

    /**
     * Nearest frame rate the encoder accepts at this size.
     *
     * The per-size range is doubles and the global fallback is ints, and asking
     * per-size can fail outright on codecs that only publish the global one --
     * which is why the two are not the same type and are read separately.
     */
    private int clampFrameRate(MediaCodecInfo.VideoCapabilities caps,int w,int h,int fps) {
        double low, high;
        try {
            android.util.Range<Double> range=caps.getSupportedFrameRatesFor(w,h);
            low=range.getLower(); high=range.getUpper();
        } catch(Exception e) {
            android.util.Range<Integer> range=caps.getSupportedFrameRates();
            low=range.getLower(); high=range.getUpper();
        }
        return (int)Math.max(low,Math.min(high,fps));
    }

    private void warn(String text) { main.post(() -> listener.warning(text)); }

    private void prepareAudio() {
        try {
            if(Build.VERSION.SDK_INT<29 || context.checkSelfPermission(android.Manifest.permission.RECORD_AUDIO)
                    !=android.content.pm.PackageManager.PERMISSION_GRANTED) throw new IOException("未获得内部声音权限");
            AudioPlaybackCaptureConfiguration config=new AudioPlaybackCaptureConfiguration.Builder(projection)
                    .addMatchingUsage(AudioAttributes.USAGE_GAME).addMatchingUsage(AudioAttributes.USAGE_MEDIA)
                    .addMatchingUsage(AudioAttributes.USAGE_UNKNOWN).build();
            int min=AudioRecord.getMinBufferSize(48000,AudioFormat.CHANNEL_IN_STEREO,AudioFormat.ENCODING_PCM_16BIT);
            if(min<=0) throw new IOException("设备不支持录音格式");
            audioRecord=new AudioRecord.Builder().setAudioPlaybackCaptureConfig(config)
                    .setAudioFormat(new AudioFormat.Builder().setSampleRate(48000).setChannelMask(AudioFormat.CHANNEL_IN_STEREO)
                            .setEncoding(AudioFormat.ENCODING_PCM_16BIT).build()).setBufferSizeInBytes(Math.max(min*2,19200)).build();
            if(audioRecord.getState()!=AudioRecord.STATE_INITIALIZED) throw new IOException("声音采集初始化失败");
            audioCodec=MediaCodec.createEncoderByType("audio/mp4a-latm");
            MediaFormat format=MediaFormat.createAudioFormat("audio/mp4a-latm",48000,2);
            format.setInteger(MediaFormat.KEY_AAC_PROFILE,MediaCodecInfo.CodecProfileLevel.AACObjectLC);
            format.setInteger(MediaFormat.KEY_BIT_RATE,128000);
            format.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE,8192);
            audioCodec.configure(format,null,null,MediaCodec.CONFIGURE_FLAG_ENCODE); audioCodec.start();
            audioEnabled=true;
        } catch(Exception e) { releaseAudio(); warn("内部声音不可用，本次改为无声录制"); }
    }

    private void startAudio() {
        if(!audioEnabled) return;
        try {
            audioRecord.startRecording(); audioStarted=true;
            audioOffsetUs=Math.max(0,(System.nanoTime()-firstNanos)/1000);
            handler.post(audioPump);
        } catch(Exception e) { releaseAudio(); warn("声音启动失败，本次改为无声录制"); }
    }

    private final Runnable audioPump=new Runnable() {
        @Override public void run() {
            if(ended || stopRequested || !audioStarted) return;
            try {
                for(int n=0;n<8;n++) {
                    int index=audioCodec.dequeueInputBuffer(0);
                    if(index<0) break;
                    ByteBuffer buffer=audioCodec.getInputBuffer(index); buffer.clear();
                    int size=audioRecord.read(buffer,Math.min(buffer.capacity(),8192)/4*4,AudioRecord.READ_NON_BLOCKING);
                    if(size<0) { audioCodec.queueInputBuffer(index,0,0,audioOffsetUs+audioFrames*1000000/48000,0); throw new IOException("声音采集已中断"); }
                    audioCodec.queueInputBuffer(index,0,size,audioOffsetUs+audioFrames*1000000/48000,0);
                    audioFrames+=size/4;
                    if(size==0) break;
                }
                drainAudio(false);
                handler.postDelayed(this,10);
            } catch(Exception e) {
                // Keep the video even when playback permission is revoked.
                audioStarted=false;
                try { audioRecord.stop(); } catch(Exception ignored) {}
                if(audioTrack<0) {
                    releaseAudio();
                    try { maybeStartMuxer(); } catch(Exception muxError) { finish(muxError); return; }
                }
                warn("内部声音已中断，视频继续录制");
            }
        }
    };

    private void maybeStartMuxer() throws IOException {
        if(muxing || track<0 || (audioEnabled && audioTrack<0)) return;
        muxer.start(); muxing=true;
        while(!pendingSamples.isEmpty()) {
            PendingSample sample=pendingSamples.removeFirst();
            muxer.writeSampleData(sample.track,sample.bytes,sample.info);
        }
        pendingBytes=0;
    }
    private void writeSample(int sampleTrack,ByteBuffer bytes,MediaCodec.BufferInfo info) throws IOException {
        if(muxing) muxer.writeSampleData(sampleTrack,bytes,info);
        else {
            if(pendingBytes+info.size>4_000_000) throw new IOException("音视频轨道启动超时");
            pendingSamples.add(new PendingSample(sampleTrack,bytes,info)); pendingBytes+=info.size;
        }
    }
    private void drainAudio(boolean end) throws IOException {
        if(audioCodec==null) return;
        long deadline=System.nanoTime()+3_000_000_000L;
        boolean eosQueued=!end;
        MediaCodec.BufferInfo info=new MediaCodec.BufferInfo();
        while(true) {
            if(!eosQueued) {
                int index=audioCodec.dequeueInputBuffer(0);
                if(index>=0) { audioCodec.queueInputBuffer(index,0,0,audioOffsetUs+audioFrames*1000000/48000,MediaCodec.BUFFER_FLAG_END_OF_STREAM); eosQueued=true; }
            }
            int index=audioCodec.dequeueOutputBuffer(info,end?10000:0);
            if(index==MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                if(audioTrack>=0) throw new IOException("声音格式发生变化");
                audioTrack=muxer.addTrack(audioCodec.getOutputFormat()); maybeStartMuxer();
            } else if(index>=0) {
                try {
                    ByteBuffer buffer=audioCodec.getOutputBuffer(index);
                    if(info.size>0 && (info.flags&MediaCodec.BUFFER_FLAG_CODEC_CONFIG)==0) {
                        buffer.position(info.offset); buffer.limit(info.offset+info.size); writeSample(audioTrack,buffer,info);
                    }
                } finally { audioCodec.releaseOutputBuffer(index,false); }
                if((info.flags&MediaCodec.BUFFER_FLAG_END_OF_STREAM)!=0) return;
            } else if(!end) return;
            if(end && System.nanoTime()>deadline) throw new IOException("声音收尾超时");
        }
    }
    private void releaseAudio() {
        audioEnabled=false; audioStarted=false;
        if(audioRecord!=null) { try { audioRecord.release(); } catch(Exception ignored) {} audioRecord=null; }
        if(audioCodec!=null) {
            try { audioCodec.stop(); } catch(Exception ignored) {}
            try { audioCodec.release(); } catch(Exception ignored) {} audioCodec=null;
        }
    }
    private int shader(int type,String source) throws IOException {
        int shader=GLES20.glCreateShader(type); GLES20.glShaderSource(shader,source); GLES20.glCompileShader(shader);
        int[] status=new int[1]; GLES20.glGetShaderiv(shader,GLES20.GL_COMPILE_STATUS,status,0);
        if(status[0]==0) { GLES20.glDeleteShader(shader); throw new IOException("录屏着色器编译失败"); }
        return shader;
    }
    private void current(EGLSurface surface) throws IOException {
        if(surface==EGL14.EGL_NO_SURFACE || !EGL14.eglMakeCurrent(egl,surface,surface,gl)) throw new IOException("录屏表面已失效");
    }
    private void draw(EGLSurface surface,int w,int h,long timestamp) throws IOException {
        current(surface); GLES20.glViewport(0,0,w,h); GLES20.glUseProgram(program);
        int position=GLES20.glGetAttribLocation(program,"position"),tex=GLES20.glGetAttribLocation(program,"tex");
        vertices.position(0); GLES20.glVertexAttribPointer(position,2,GLES20.GL_FLOAT,false,16,vertices);
        vertices.position(2); GLES20.glVertexAttribPointer(tex,2,GLES20.GL_FLOAT,false,16,vertices);
        GLES20.glEnableVertexAttribArray(position); GLES20.glEnableVertexAttribArray(tex);
        GLES20.glActiveTexture(GLES20.GL_TEXTURE0); GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES,textureId);
        GLES20.glUniform1i(GLES20.glGetUniformLocation(program,"image"),0);
        GLES20.glUniformMatrix4fv(GLES20.glGetUniformLocation(program,"transform"),1,false,transform,0);
        GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP,0,4);
        if(timestamp>=0) EGLExt.eglPresentationTimeANDROID(egl,surface,timestamp);
        if(!EGL14.eglSwapBuffers(egl,surface)) throw new IOException("录屏画面提交失败");
    }
    private void frame() {
        if(ended || stopRequested) return;
        try {
            current(preview); texture.updateTexImage(); texture.getTransformMatrix(transform);
            long now=System.nanoTime();
            // ImageReader is consumed on demand, not at video frame rate. Do
            // not fill its queue while settings/pause stop recognition polling.
            if(previewRequested.getAndSet(false)) draw(preview,width,height,-1);
            if(firstNanos==0) { firstNanos=now; startAudio(); }
            // Must be videoFps, not a literal: encoding at 30 while pacing at 24
            // produces a file that claims 30 and moves at 24.
            if(lastNanos==0 || now-lastNanos>=1_000_000_000L/videoFps) {
                drain(false); draw(video,videoWidth,videoHeight,now-firstNanos); lastNanos=now; drain(false);
            }
        } catch(Exception e) { finish(e); }
    }
    private void drain(boolean end) throws IOException {
        if(end) codec.signalEndOfInputStream();
        long deadline=System.nanoTime()+3_000_000_000L;
        MediaCodec.BufferInfo info=new MediaCodec.BufferInfo();
        while(true) {
            int index=codec.dequeueOutputBuffer(info,end?10000:0);
            if(index==MediaCodec.INFO_TRY_AGAIN_LATER) {
                if(!end) return;
                if(System.nanoTime()>deadline) throw new IOException("录屏收尾超时");
            } else if(index==MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                if(track>=0) throw new IOException("录屏格式发生变化");
                track=muxer.addTrack(codec.getOutputFormat()); maybeStartMuxer();
            } else if(index>=0) {
                try {
                    ByteBuffer buffer=codec.getOutputBuffer(index);
                    if((info.flags&MediaCodec.BUFFER_FLAG_CODEC_CONFIG)==0 && info.size>0) {
                        if(buffer==null) throw new IOException("录屏编码数据无效");
                        buffer.position(info.offset); buffer.limit(info.offset+info.size);
                        writeSample(track,buffer,info); samples=true;
                    }
                } finally { codec.releaseOutputBuffer(index,false); }
                if((info.flags&MediaCodec.BUFFER_FLAG_END_OF_STREAM)!=0) return;
            }
        }
    }
    private void finish(Exception failure) {
        if(ended) return; ended=true;
        handler.removeCallbacks(audioPump);
        if(audioStarted) { try { audioRecord.stop(); } catch(Exception ignored) {} audioStarted=false; }
        try { if(audioEnabled) drainAudio(true); }
        catch(Exception e) { warn("声音收尾异常，尝试保留视频"); }
        if(audioTrack<0) audioEnabled=false;
        try { maybeStartMuxer(); } catch(Exception e) { failure=e; }
        try { if(failure==null && codec!=null) drain(true); }
        catch(Exception e) { failure=e; }
        releaseAudio();
        if(texture!=null) texture.setOnFrameAvailableListener(null);
        try { if(muxer!=null && muxing) muxer.stop(); } catch(Exception e) { failure=e; }
        try { if(muxer!=null) muxer.release(); } catch(Exception ignored) {}
        try { if(codec!=null) { codec.stop(); codec.release(); } } catch(Exception ignored) {}
        if(egl!=EGL14.EGL_NO_DISPLAY) {
            EGL14.eglMakeCurrent(egl,EGL14.EGL_NO_SURFACE,EGL14.EGL_NO_SURFACE,EGL14.EGL_NO_CONTEXT);
            if(preview!=EGL14.EGL_NO_SURFACE) EGL14.eglDestroySurface(egl,preview);
            if(video!=EGL14.EGL_NO_SURFACE) EGL14.eglDestroySurface(egl,video);
            if(gl!=EGL14.EGL_NO_CONTEXT) EGL14.eglDestroyContext(egl,gl);
            EGL14.eglReleaseThread(); EGL14.eglTerminate(egl);
        }
        if(input!=null) input.release();
        if(texture!=null) texture.release();
        if(encoderSurface!=null) encoderSurface.release();
        try { if(descriptor!=null) descriptor.close(); } catch(IOException ignored) {}
        boolean valid=failure==null && samples;
        try {
            if(uri!=null) {
                if(valid) { ContentValues values=new ContentValues(); values.put(MediaStore.Video.Media.IS_PENDING,0); context.getContentResolver().update(uri,values,null,null); }
                else context.getContentResolver().delete(uri,null,null);
            } else if(!valid && file!=null) { file.delete(); }
        } catch(Exception e) { failure=e; valid=false; }
        final String error=valid?null:failure==null?"未录到画面":failure.getMessage();
        final String location=uri!=null?"相册 / Movies/CrypticNotes":file==null?"":file.toString();
        main.post(() -> listener.finished(location,error));
        thread.quitSafely();
    }
}
