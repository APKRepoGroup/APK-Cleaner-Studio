package com.apkcleaner.studio;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.util.Log;

import com.android.apksig.ApkSigner;
import com.android.apksig.ApkVerifier;
import com.reandroid.apkeditor.Main;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

import local.apkcleaner.dex.DirectDexPatcher;
import local.apkcleaner.xml.BinaryManifestPatcher;

/** Executes the existing JVM tools in-process: no Java executable or Termux is required. */
public final class EmbeddedToolRunner {
    private static final String TAG = "APKCleanerTools";
    private static final Object OUTPUT_LOCK = new Object();
    private static final AtomicBoolean CANCEL_REQUESTED = new AtomicBoolean(false);
    private static final ConcurrentHashMap<Long, Thread> ACTIVE_THREADS = new ConcurrentHashMap<>();
    private static volatile Context appContext;

    /** Retain only recent diagnostics instead of buffering unbounded APKEditor output. */
    private static final class TailOutputStream extends OutputStream {
        private static final int CAPACITY = 64 * 1024;
        private final byte[] bytes = new byte[CAPACITY];
        private int next;
        private int size;
        private boolean truncated;

        @Override public void write(int value) {
            if (size == CAPACITY) truncated = true;
            bytes[next] = (byte) value;
            next = (next + 1) % CAPACITY;
            size = Math.min(CAPACITY, size + 1);
        }

        @Override public void write(byte[] source, int offset, int length) {
            if (source == null) throw new NullPointerException("source");
            if (offset < 0 || length < 0 || offset > source.length - length) {
                throw new IndexOutOfBoundsException();
            }
            if (length == 0) return;
            if (length >= CAPACITY) {
                System.arraycopy(source, offset + length - CAPACITY, bytes, 0, CAPACITY);
                truncated = truncated || size != 0 || length > CAPACITY;
                next = 0;
                size = CAPACITY;
                return;
            }
            if (size + length > CAPACITY) truncated = true;
            int first = Math.min(length, CAPACITY - next);
            System.arraycopy(source, offset, bytes, next, first);
            if (first < length) System.arraycopy(source, offset + first, bytes, 0, length - first);
            next = (next + length) % CAPACITY;
            size = Math.min(CAPACITY, size + length);
        }

        String capturedText() {
            byte[] ordered = new byte[size];
            int start = (next - size + CAPACITY) % CAPACITY;
            int first = Math.min(size, CAPACITY - start);
            System.arraycopy(bytes, start, ordered, 0, first);
            if (first < size) System.arraycopy(bytes, 0, ordered, first, size - first);
            return (truncated ? "[Önceki araç çıktısı kısaltıldı]\n" : "")
                    + new String(ordered, StandardCharsets.UTF_8);
        }
    }

    private EmbeddedToolRunner() {}

    public static final class Result {
        public final int exitCode;
        public final String output;

        Result(int exitCode, String output) {
            this.exitCode = exitCode;
            this.output = output;
        }
    }

    public static void initialize(Context context) {
        appContext = context.getApplicationContext();
    }

    /** Android's package parser is a fallback for manifests the bundled AXML reader cannot inspect. */
    public static String inspectArchivePackage(String apkPath) {
        Context context = appContext;
        if (context == null || apkPath == null || apkPath.isEmpty()) return "";
        try {
            PackageInfo info = context.getPackageManager().getPackageArchiveInfo(apkPath, 0);
            return info != null && info.packageName != null ? info.packageName : "";
        } catch (RuntimeException error) {
            Log.w(TAG, "APK paket adı Android ayrıştırıcısıyla okunamadı", error);
            return "";
        }
    }

    public static Result run(String[] command, String cwd) {
        Thread current = Thread.currentThread();
        // Chaquopy may reuse a worker interrupted by an earlier cancelled job.
        // The new job has already cleared CANCEL_REQUESTED; clear only that stale
        // thread flag so unrelated subsequent tool calls can run normally.
        if (!CANCEL_REQUESTED.get()) Thread.interrupted();
        ACTIVE_THREADS.put(current.getId(), current);
        String[] directArgs = directDexArgs(command);
        if (directArgs != null) {
            ByteArrayOutputStream errors = new ByteArrayOutputStream();
            try {
                if (CANCEL_REQUESTED.get()) throw new InterruptedException("İşlem iptal edildi.");
                String output = DirectDexPatcher.execute(directArgs);
                if (CANCEL_REQUESTED.get()) throw new InterruptedException("İşlem iptal edildi.");
                return new Result(0, output);
            } catch (Throwable error) {
                Log.e(TAG, "Doğrudan DEX aracı başarısız oldu", error);
                error.printStackTrace(new PrintStream(errors));
                return new Result(1, new String(errors.toByteArray(), StandardCharsets.UTF_8));
            } finally {
                ACTIVE_THREADS.remove(current.getId());
            }
        }
        synchronized (OUTPUT_LOCK) {
            PrintStream originalOut = System.out;
            PrintStream originalErr = System.err;
            TailOutputStream capture = new TailOutputStream();
            int exitCode = 0;
            try (PrintStream stream = new PrintStream(capture, true, StandardCharsets.UTF_8.name())) {
                System.setOut(stream);
                System.setErr(stream);
                if (CANCEL_REQUESTED.get()) throw new InterruptedException("İşlem iptal edildi.");
                dispatch(command);
                if (CANCEL_REQUESTED.get()) throw new InterruptedException("İşlem iptal edildi.");
            } catch (Throwable error) {
                exitCode = 1;
                Log.e(TAG, "Gömülü araç başarısız oldu", error);
                error.printStackTrace(new PrintStream(capture));
            } finally {
                System.setOut(originalOut);
                System.setErr(originalErr);
                ACTIVE_THREADS.remove(current.getId());
            }
            return new Result(exitCode, capture.capturedText());
        }
    }

    private static String[] directDexArgs(String[] command) {
        List<String> args = new ArrayList<>(Arrays.asList(command));
        if (!args.isEmpty()) args.remove(0);
        int cpIndex = args.indexOf("-cp");
        if (cpIndex < 0 || args.size() <= cpIndex + 2
                || !"local.apkcleaner.dex.DirectDexPatcher".equals(args.get(cpIndex + 2))) return null;
        return args.subList(cpIndex + 3, args.size()).toArray(new String[0]);
    }

    private static void dispatch(String[] command) throws Exception {
        List<String> args = new ArrayList<>(Arrays.asList(command));
        if (!args.isEmpty()) args.remove(0); // embedded runtime marker
        int jarIndex = args.indexOf("-jar");
        if (jarIndex >= 0 && args.size() > jarIndex + 1) {
            String jarName = new File(args.get(jarIndex + 1)).getName();
            String[] toolArgs = args.subList(jarIndex + 2, args.size()).toArray(new String[0]);
            if (jarName.equalsIgnoreCase("APKEditor.jar")) {
                int code = Main.execute(toolArgs);
                if (code != 0) throw new IllegalStateException("APKEditor çıkış kodu: " + code);
                return;
            }
            throw new IllegalArgumentException("Desteklenmeyen gömülü JAR: " + jarName);
        }

        int cpIndex = args.indexOf("-cp");
        if (cpIndex >= 0 && args.size() > cpIndex + 2) {
            String className = args.get(cpIndex + 2);
            String[] toolArgs = args.subList(cpIndex + 3, args.size()).toArray(new String[0]);
            if (className.equals("local.apkcleaner.dex.DirectDexPatcher")) {
                DirectDexPatcher.main(toolArgs);
                return;
            }
            if (className.equals("local.apkcleaner.xml.BinaryManifestPatcher")) {
                BinaryManifestPatcher.main(toolArgs);
                return;
            }
            throw new IllegalArgumentException("Desteklenmeyen gömülü sınıf: " + className);
        }
        throw new IllegalArgumentException("Gömülü araç komutu tanınmadı.");
    }

    public static void requestCancel() {
        CANCEL_REQUESTED.set(true);
        for (Thread thread : ACTIVE_THREADS.values()) thread.interrupt();
    }

    public static void clearCancellation() {
        CANCEL_REQUESTED.set(false);
    }

    public static void signApk(String inputPath, String outputPath, boolean optimize) throws Exception {
        Context context = appContext;
        if (context == null) throw new IllegalStateException("Android imzalayıcı başlatılmadı.");
        KeyStore store = KeyStore.getInstance("PKCS12");
        char[] password = "apkcleaner".toCharArray();
        try (InputStream input = context.getAssets().open("output-signing.p12")) {
            store.load(input, password);
        }
        String alias = store.aliases().nextElement();
        PrivateKey key = (PrivateKey) store.getKey(alias, password);
        X509Certificate certificate = (X509Certificate) store.getCertificate(alias);
        ApkSigner.SignerConfig signer = new ApkSigner.SignerConfig.Builder(
                "APK Cleaner Studio", key, Collections.singletonList(certificate)).build();
        ApkSigner.Builder builder = new ApkSigner.Builder(Collections.singletonList(signer))
                .setInputApk(new File(inputPath))
                .setOutputApk(new File(outputPath))
                .setV1SigningEnabled(true)
                .setV2SigningEnabled(true)
                .setV3SigningEnabled(true)
                .setV4SigningEnabled(false)
                .setCreatedBy("APK Cleaner Studio Android")
                // Düzenlenen APK artık özgün arşivin hizalama metadatasına sahip
                // olmayabilir. Eski hizalamayı korumaya çalışmak bazı paketlerde
                // imzalamayı düşürüyor, bazı üretici kurucularında da -22 ile
                // reddedilen çıktı üretebiliyordu. APK'yı her zaman yeniden 4 bayt
                // ve native kitaplıkları 16 KiB sayfa sınırına hizala.
                .setAlignmentPreserved(false)
                .setLibraryPageAlignmentBytes(16 * 1024)
                .setAlignFileSize(optimize);
        builder.build().sign();

        try {
            verifyApk(outputPath);
        } catch (IllegalStateException failure) {
            try { new File(outputPath).delete(); } catch (RuntimeException ignored) {}
            throw failure;
        }
    }

    /** Recheck the final file after the Python engine has finished its archive audit. */
    public static void verifyApk(String apkPath) throws Exception {
        ApkVerifier.Result verification = new ApkVerifier.Builder(new File(apkPath)).build().verify();
        if (!verification.isVerified()) {
            StringBuilder message = new StringBuilder("Üretilen APK imzası doğrulanamadı.");
            for (ApkVerifier.IssueWithParams error : verification.getErrors()) {
                message.append(' ').append(error.toString());
            }
            throw new IllegalStateException(message.toString());
        }
    }
}
