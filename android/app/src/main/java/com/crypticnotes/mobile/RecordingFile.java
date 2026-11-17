package com.crypticnotes.mobile;

import android.content.ContentValues;
import android.content.Context;
import android.media.MediaMuxer;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.os.ParcelFileDescriptor;
import android.provider.MediaStore;
import java.io.File;
import java.io.IOException;

/**
 * The MP4 a recording is written to: a pending entry in Movies/CrypticNotes on
 * Android 10 and later, a file in the app's own movies folder below that.
 *
 * Shared by the ordinary recording and the replay clip so both land in the same
 * place and neither can leave a half-written video visible in the gallery.
 */
final class RecordingFile {
    final MediaMuxer muxer;
    private final Context context;
    private Uri uri;
    private ParcelFileDescriptor descriptor;
    private File file;

    RecordingFile(Context context,String name) throws IOException {
        this.context=context;
        if(Build.VERSION.SDK_INT>=29) {
            ContentValues values=new ContentValues();
            values.put(MediaStore.Video.Media.DISPLAY_NAME,name);
            values.put(MediaStore.Video.Media.MIME_TYPE,"video/mp4");
            values.put(MediaStore.Video.Media.RELATIVE_PATH,"Movies/CrypticNotes");
            values.put(MediaStore.Video.Media.IS_PENDING,1);
            uri=context.getContentResolver().insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI,values);
            if(uri==null) throw new IOException("无法创建录屏文件");
            try {
                descriptor=context.getContentResolver().openFileDescriptor(uri,"w");
                if(descriptor==null) throw new IOException("无法打开录屏文件");
                muxer=new MediaMuxer(descriptor.getFileDescriptor(),MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);
            } catch(IOException | RuntimeException e) {
                // The constructor is failing, so nobody will be able to call close().
                try { if(descriptor!=null) descriptor.close(); } catch(IOException ignored) {}
                try { context.getContentResolver().delete(uri,null,null); } catch(RuntimeException ignored) {}
                throw e;
            }
        } else {
            File directory=context.getExternalFilesDir(Environment.DIRECTORY_MOVIES);
            if(directory==null) throw new IOException("视频存储不可用");
            file=new File(directory,name);
            muxer=new MediaMuxer(file.toString(),MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);
        }
    }

    /** Where the user will find it, in words for a status line. */
    String location() { return uri!=null?"相册 / Movies/CrypticNotes":file==null?"":file.toString(); }

    /**
     * Call after the muxer has been stopped and released. A valid video is
     * published to the gallery; anything else is removed.
     */
    void close(boolean valid) {
        try { if(descriptor!=null) descriptor.close(); } catch(IOException ignored) {}
        if(uri!=null) {
            if(valid) {
                ContentValues values=new ContentValues();
                values.put(MediaStore.Video.Media.IS_PENDING,0);
                context.getContentResolver().update(uri,values,null,null);
            } else context.getContentResolver().delete(uri,null,null);
        } else if(!valid && file!=null) file.delete();
    }
}
