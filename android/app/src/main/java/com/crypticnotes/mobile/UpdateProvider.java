package com.crypticnotes.mobile;

import android.content.*;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import java.io.*;

/** Exposes only the verified update APK to the system installer, read-only. */
public class UpdateProvider extends ContentProvider {
    public boolean onCreate() { return true; }
    private File file(Uri uri) throws FileNotFoundException {
        if (!"/update.apk".equals(uri.getPath())) throw new FileNotFoundException();
        return new File(getContext().getCacheDir(), "update.apk");
    }
    public String getType(Uri uri) { return "application/vnd.android.package-archive"; }
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (!"r".equals(mode)) throw new FileNotFoundException("Read only");
        return ParcelFileDescriptor.open(file(uri), ParcelFileDescriptor.MODE_READ_ONLY);
    }
    public Cursor query(Uri uri, String[] projection, String selection, String[] args, String sort) {
        try {
            File f = file(uri);
            String[] columns = projection == null ? new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE} : projection;
            MatrixCursor c = new MatrixCursor(columns);
            Object[] values = new Object[columns.length];
            for (int i=0;i<columns.length;i++) values[i] = OpenableColumns.DISPLAY_NAME.equals(columns[i]) ? "update.apk" : OpenableColumns.SIZE.equals(columns[i]) ? f.length() : null;
            c.addRow(values); return c;
        } catch (IOException e) { return null; }
    }
    public Uri insert(Uri uri, ContentValues values) { throw new UnsupportedOperationException(); }
    public int delete(Uri uri, String selection, String[] args) { throw new UnsupportedOperationException(); }
    public int update(Uri uri, ContentValues values, String selection, String[] args) { throw new UnsupportedOperationException(); }
}
