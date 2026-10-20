"""Host-side provider tests with small Android API doubles; no APK build."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "android/app/src/main/java/com/apkcleaner/studio"

STUBS = {
    "android/content/ContentProvider.java": '''package android.content;
public abstract class ContentProvider {
 private Context context; public Context getContext(){return context;} public void attach(Context c){context=c;}
 public abstract boolean onCreate(); public abstract String getType(android.net.Uri u);
 public abstract android.database.Cursor query(android.net.Uri u,String[] p,String s,String[] a,String o);
 public abstract android.os.ParcelFileDescriptor openFile(android.net.Uri u,String m) throws java.io.FileNotFoundException;
 public abstract int delete(android.net.Uri u,String s,String[] a);
 public abstract int update(android.net.Uri u,ContentValues v,String s,String[] a);
 public abstract android.net.Uri insert(android.net.Uri u,ContentValues v);
}''',
    "android/content/Context.java": '''package android.content;
public class Context {public java.io.File cache; public android.content.pm.PackageManager pm=new android.content.pm.PackageManager();
 public java.io.File getCacheDir(){return cache;} public android.content.pm.PackageManager getPackageManager(){return pm;}}''',
    "android/content/ContentValues.java": "package android.content; public class ContentValues {}",
    "android/content/pm/ApplicationInfo.java": "package android.content.pm; public class ApplicationInfo {public String sourceDir;}",
    "android/content/pm/PackageManager.java": '''package android.content.pm;
public class PackageManager {public static class NameNotFoundException extends Exception {}
 public ApplicationInfo application; public ApplicationInfo getApplicationInfo(String p,int f) throws NameNotFoundException {
 if(application==null || !p.equals("com.example.app"))throw new NameNotFoundException();return application;}}''',
    "android/database/Cursor.java": "package android.database; public interface Cursor {}",
    "android/database/MatrixCursor.java": '''package android.database;
public class MatrixCursor implements Cursor {public Object[] row;public String[] columns;
 public MatrixCursor(String[] c){columns=c;}public void addRow(Object[] r){row=r;}}''',
    "android/provider/OpenableColumns.java": '''package android.provider;
public interface OpenableColumns {String DISPLAY_NAME="_display_name", SIZE="_size";}''',
    "android/os/ParcelFileDescriptor.java": '''package android.os;
public class ParcelFileDescriptor {public static final int MODE_READ_ONLY=1;public java.io.File file;
 public static ParcelFileDescriptor open(java.io.File f,int m) throws java.io.FileNotFoundException {
 if(!f.isFile()||m!=MODE_READ_ONLY)throw new java.io.FileNotFoundException();
 ParcelFileDescriptor p=new ParcelFileDescriptor();p.file=f;return p;}}''',
    "android/net/Uri.java": '''package android.net;
public class Uri {private final java.util.List<String> segments;
 Uri(java.util.List<String> s){segments=java.util.List.copyOf(s);}
 public java.util.List<String> getPathSegments(){return segments;}
 public String getLastPathSegment(){return segments.isEmpty()?null:segments.get(segments.size()-1);}
 public Builder buildUpon(){Builder b=new Builder();b.parts.addAll(segments);return b;}
 public static class Builder {java.util.List<String> parts=new java.util.ArrayList<>();
 public Builder scheme(String s){return this;}public Builder authority(String s){return this;}
 public Builder appendPath(String s){parts.add(s);return this;}public Uri build(){return new Uri(parts);}}}''',
    "ShareNameFixture.java": '''import java.io.*;import java.nio.file.*;
import android.net.Uri;import android.database.MatrixCursor;import com.apkcleaner.studio.ApkFileProvider;
public class ShareNameFixture {
 static void require(boolean value){if(!value)throw new AssertionError();}
 static void denied(ApkFileProvider p,Uri u) throws Exception {
 require(p.query(u,null,null,null,null)==null);
 try {p.openFile(u,"r");throw new AssertionError();}catch(FileNotFoundException expected){}}
 public static void main(String[] args) throws Exception {
 File cache=new File(args[0]);File root=new File(cache,"native-packages");root.mkdirs();
 File first=new File(root,"processed-uuid-one-Output.apk"),second=new File(root,"processed-uuid-two-Output.apk");
 Files.write(first.toPath(),new byte[]{1,2,3});Files.write(second.toPath(),new byte[]{4,5});
 android.content.Context context=new android.content.Context();context.cache=cache;
 ApkFileProvider p=new ApkFileProvider();p.attach(context);
 String name="Türkçe Uygulama v1.2-processed.apk";
 Uri u=ApkFileProvider.uriFor(first,name,"test.files");
 MatrixCursor cursor=(MatrixCursor)p.query(u,null,null,null,null);
 require(cursor.row[0].equals(name));require(cursor.row[1].equals(3L));require(u.getLastPathSegment().equals(name));
 require(java.util.Arrays.equals(Files.readAllBytes(p.openFile(u,"r").file.toPath()),new byte[]{1,2,3}));
 Uri other=ApkFileProvider.uriFor(second,name,"test.files");
 require(p.openFile(other,"r").file.equals(second));require(!p.openFile(other,"r").file.equals(first));
 require(p.getType(u).equals("application/vnd.android.package-archive"));
 require(p.getType(ApkFileProvider.uriFor(second,"Uygulama.apks","test.files")).equals("application/zip"));
 Uri legacy=ApkFileProvider.uriFor(first,"test.files");
 require(((MatrixCursor)p.query(legacy,null,null,null,null)).row[0].equals(first.getName()));
 try {p.openFile(u,"w");throw new AssertionError();}catch(FileNotFoundException expected){}
 Files.write(new File(cache,"outside.apk").toPath(),new byte[]{9});
 for(String path:new String[]{"../outside.apk","..","nested/../../outside.apk","..\\\\outside.apk"})
 denied(p,new Uri.Builder().appendPath("native-packages").appendPath(path).appendPath(name).build());
 denied(p,u.buildUpon().appendPath("extra").build());
 denied(p,new Uri.Builder().appendPath("wrong-root").appendPath(first.getName()).build());
 denied(p,new Uri.Builder().appendPath("native-packages").build());
 context.pm.application=new android.content.pm.ApplicationInfo();context.pm.application.sourceDir=first.getPath();
 Uri installed=ApkFileProvider.uriForInstalled("com.example.app","Yüklü uygulama.apk","test.files");
 require(((MatrixCursor)p.query(installed,null,null,null,null)).row[0].equals("Yüklü uygulama.apk"));
 require(p.openFile(installed,"r").file.equals(first));
 System.out.println("PASS: display names, identical-name isolation, read-only access, legacy and installed URIs, traversal rejection");
 }}''',
}


class AndroidShareNameTests(unittest.TestCase):
    def test_share_provider_uses_display_name_without_renaming_cached_files(self):
        javac, java = shutil.which("javac"), shutil.which("java")
        if not javac or not java:
            self.skipTest("JDK is required for the host-side provider test")
        with tempfile.TemporaryDirectory(prefix="share-provider-") as directory:
            temp = Path(directory)
            sources = []
            for name, text in STUBS.items():
                path = temp / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
                sources.append(str(path))
            subprocess.run([javac, "-encoding", "UTF-8", "-d", str(temp), *sources, str(NATIVE / "ApkFileProvider.java")],
                           check=True, capture_output=True, timeout=45)
            result = subprocess.run([java, "-Dfile.encoding=UTF-8", "-cp", str(temp), "ShareNameFixture", str(temp / "cache")],
                                    check=True, capture_output=True, text=True, encoding="utf-8", timeout=20)
            self.assertIn("PASS:", result.stdout)

    def test_output_sharing_keeps_the_supplied_name_and_uri_read_grant(self):
        source = (NATIVE / "MainActivity.java").read_text(encoding="utf-8")
        share = source.split("@JavascriptInterface public void shareOutput(", 1)[1].split("@JavascriptInterface", 1)[0]
        self.assertIn('shareFile(downloadNativePackage(url, filename, "processed"), filename)', share)
        self.assertIn('prefix + "-" + UUID.randomUUID()', source)
        self.assertIn('ApkFileProvider.uriFor(file, filename, getPackageName() + ".files")', source)
        self.assertIn("ClipData.newRawUri(filename, uri)", source)
        self.assertIn("Intent.EXTRA_TITLE, filename", source)
        self.assertIn("Intent.FLAG_GRANT_READ_URI_PERMISSION", source)


if __name__ == "__main__":
    unittest.main()
