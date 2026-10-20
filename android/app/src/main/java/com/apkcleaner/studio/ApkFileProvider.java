package com.apkcleaner.studio;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;

import java.io.File;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.util.Locale;

/** Read-only, cache-scoped provider for Android's installer and share sheet. */
public final class ApkFileProvider extends ContentProvider {
    public static Uri uriFor(File file, String authority) {
        return new Uri.Builder().scheme("content").authority(authority)
                .appendPath("native-packages").appendPath(file.getName()).build();
    }

    public static Uri uriFor(File file, String displayName, String authority) {
        // The physical UUID keeps simultaneous downloads isolated; receivers
        // see the real output name both in the URI and DISPLAY_NAME metadata.
        return uriFor(file, authority).buildUpon().appendPath(displayName).build();
    }

    public static Uri uriForInstalled(String packageName, String displayName, String authority) {
        return new Uri.Builder().scheme("content").authority(authority)
                .appendPath("installed-package").appendPath(packageName).appendPath(displayName).build();
    }

    private static final class ResolvedFile {
        final File file;
        final String displayName;
        ResolvedFile(File file, String displayName) { this.file = file; this.displayName = displayName; }
    }

    private ResolvedFile resolve(Uri uri) throws FileNotFoundException {
        if (getContext() == null || uri.getPathSegments().isEmpty()) {
            throw new FileNotFoundException("Geçersiz paket adresi.");
        }
        if ("installed-package".equals(uri.getPathSegments().get(0)) && uri.getPathSegments().size() == 3) {
            String packageName = uri.getPathSegments().get(1);
            String displayName = new File(uri.getPathSegments().get(2)).getName();
            try {
                ApplicationInfo info = getContext().getPackageManager().getApplicationInfo(packageName, 0);
                File source = new File(info.sourceDir);
                if (!source.isFile()) throw new FileNotFoundException("Kurulu APK bulunamadı.");
                return new ResolvedFile(source, displayName);
            } catch (PackageManager.NameNotFoundException error) {
                throw new FileNotFoundException("Kurulu uygulama bulunamadı.");
            }
        }
        int segments = uri.getPathSegments().size();
        if ((segments != 2 && segments != 3) || !"native-packages".equals(uri.getPathSegments().get(0))) {
            throw new FileNotFoundException("Geçersiz paket adresi.");
        }
        File root = new File(getContext().getCacheDir(), "native-packages");
        String storedName = uri.getPathSegments().get(1);
        if (!storedName.equals(new File(storedName).getName()) || storedName.indexOf('\\') >= 0) {
            throw new FileNotFoundException("Geçersiz paket adı.");
        }
        File file = new File(root, storedName);
        try {
            if (!file.getCanonicalPath().startsWith(root.getCanonicalPath() + File.separator) || !file.isFile()) {
                throw new FileNotFoundException("Paket bulunamadı.");
            }
        } catch (IOException error) { throw new FileNotFoundException(error.getMessage()); }
        String displayName = segments == 3 ? new File(uri.getLastPathSegment()).getName() : file.getName();
        return new ResolvedFile(file, displayName);
    }

    @Override public boolean onCreate() { return true; }
    @Override public String getType(Uri uri) {
        String name = uri.getLastPathSegment();
        return name != null && name.toLowerCase(Locale.ROOT).endsWith(".apk")
                ? "application/vnd.android.package-archive" : "application/zip";
    }
    @Override public Cursor query(Uri uri, String[] projection, String selection, String[] args, String order) {
        try {
            ResolvedFile resolved = resolve(uri);
            MatrixCursor cursor = new MatrixCursor(new String[] {OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE});
            cursor.addRow(new Object[] {resolved.displayName, resolved.file.length()});
            return cursor;
        } catch (FileNotFoundException error) { return null; }
    }
    @Override public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (!"r".equals(mode)) throw new FileNotFoundException("Salt okunur erişim.");
        return ParcelFileDescriptor.open(resolve(uri).file, ParcelFileDescriptor.MODE_READ_ONLY);
    }
    @Override public int delete(Uri uri, String s, String[] a) { return 0; }
    @Override public int update(Uri uri, ContentValues v, String s, String[] a) { return 0; }
    @Override public Uri insert(Uri uri, ContentValues values) { return null; }
}
