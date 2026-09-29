package com.apkcleaner.studio;

import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageInstaller;
import android.content.pm.PackageManager;
import android.os.Build;
import android.widget.Toast;

import com.android.apksig.ApkVerifier;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.security.MessageDigest;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Enumeration;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

import org.json.JSONArray;
import org.json.JSONObject;

/** Installs original, unmodified split APKs through one Android install session. */
public final class OriginalSplitInstaller {
    private static final int MAX_MODULES = 200;
    private static final long MAX_EXPANDED_BYTES = 3L * 1024L * 1024L * 1024L;
    private static final String[] DENSITIES = {"ldpi", "mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"};
    private static final int[] DENSITY_DPI = {120, 160, 240, 320, 480, 640};
    private static final Pattern LANGUAGE = Pattern.compile("(?:^|_)(?:config_)?([a-z]{2})(?:_r[a-z]{2})?$");

    private OriginalSplitInstaller() {}

    private static final class Module {
        String name;
        long size;
        String kind;
        String value;
        boolean baseCandidate;
        boolean autoSelected;
    }

    private static final class Inspection {
        final List<Module> modules = new ArrayList<>();
        String packageName;
        String versionName;
        String signer;
        String baseName;
        String blockedReason;
        long version = -1;
        boolean installed;
    }

    static String inspect(Context context, File bundle) throws Exception {
        Inspection inspection = scan(context, bundle);
        JSONArray modules = new JSONArray();
        for (Module module : inspection.modules) {
            modules.put(new JSONObject().put("name", module.name).put("size", module.size)
                    .put("kind", module.kind).put("value", module.value == null ? "" : module.value)
                    .put("required", module.name.equals(inspection.baseName))
                    .put("auto", module.autoSelected));
        }
        return new JSONObject().put("status", "plan_ready")
                .put("package", inspection.packageName)
                .put("version", inspection.versionName == null || inspection.versionName.isEmpty()
                        ? String.valueOf(inspection.version) : inspection.versionName)
                .put("version_code", inspection.version)
                .put("installed", inspection.installed)
                .put("signature_status", !inspection.installed ? "Yeni kurulum"
                        : inspection.blockedReason != null && inspection.blockedReason.contains("imzası")
                        ? "İmza uyuşmuyor" : "İmza uyumlu")
                .put("blocked_reason", inspection.blockedReason == null ? "" : inspection.blockedReason)
                .put("modules", modules).toString();
    }

    static String install(Context context, File bundle, String selectedJson) throws Exception {
        Inspection inspection = scan(context, bundle);
        if (inspection.blockedReason != null) throw new IOException(inspection.blockedReason);
        JSONArray requested = new JSONArray(selectedJson);
        Set<String> selected = new HashSet<>();
        for (int index = 0; index < requested.length(); index++) {
            String name = requested.getString(index);
            if (!selected.add(name)) throw new IOException("Aynı split bileşeni birden çok kez seçildi.");
        }
        if (!selected.contains(inspection.baseName)) {
            throw new IOException("Kurulum için temel APK bileşeni seçili olmalı.");
        }
        List<Module> modules = new ArrayList<>();
        long totalBytes = 0;
        for (Module module : inspection.modules) {
            if (!selected.contains(module.name)) continue;
            if ("alternative".equals(module.kind)) {
                throw new IOException("Alternatif temel APK bileşenleri aynı oturumda kurulamaz.");
            }
            modules.add(module);
            totalBytes += module.size;
        }
        if (selected.size() != modules.size()) throw new IOException("Paket içinde bulunmayan bir split bileşeni seçildi.");
        // Stage the base first. PackageInstaller performs the final package/split validation.
        modules.sort((left, right) -> Boolean.compare(!left.name.equals(inspection.baseName),
                !right.name.equals(inspection.baseName)));
        PackageInstaller installer = context.getPackageManager().getPackageInstaller();
        PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(
                PackageInstaller.SessionParams.MODE_FULL_INSTALL);
        params.setAppPackageName(inspection.packageName);
        params.setSize(totalBytes);
        if (Build.VERSION.SDK_INT >= 31) {
            params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_REQUIRED);
        }
        if (Build.VERSION.SDK_INT >= 33) {
            params.setPackageSource(PackageInstaller.PACKAGE_SOURCE_LOCAL_FILE);
        }
        int sessionId = installer.createSession(params);
        boolean committed = false;
        try (ZipFile zip = new ZipFile(bundle); PackageInstaller.Session session = installer.openSession(sessionId)) {
            for (int index = 0; index < modules.size(); index++) {
                Module module = modules.get(index);
                ZipEntry entry = zip.getEntry(module.name);
                if (entry == null || entry.getSize() != module.size) {
                    throw new IOException("Split paketi kurulum hazırlığı sırasında değişti.");
                }
                try (InputStream input = zip.getInputStream(entry);
                     OutputStream output = session.openWrite("module-" + index + ".apk", 0, module.size)) {
                    copy(input, output, module.size);
                    session.fsync(output);
                }
            }
            Intent callback = new Intent(context, ResultReceiver.class)
                    .setAction("com.apkcleaner.studio.ORIGINAL_SPLIT_INSTALL_RESULT")
                    .putExtra("package", inspection.packageName)
                    .putExtra("session", sessionId);
            int flags = PendingIntent.FLAG_UPDATE_CURRENT;
            if (Build.VERSION.SDK_INT >= 31) flags |= PendingIntent.FLAG_MUTABLE;
            PendingIntent pending = PendingIntent.getBroadcast(context, sessionId, callback, flags);
            InstallHistoryStore.submitted(context, sessionId, inspection.packageName, modules.size());
            session.commit(pending.getIntentSender());
            committed = true;
            return new JSONObject().put("status", "session_submitted")
                    .put("package", inspection.packageName).put("modules", modules.size()).toString();
        } finally {
            if (!committed) {
                installer.abandonSession(sessionId);
                InstallHistoryStore.completed(context, sessionId, "error", "Kurulum oturumu başlatılamadı.");
            }
        }
    }

    private static Inspection scan(Context context, File bundle) throws Exception {
        if (bundle == null || !bundle.isFile()) throw new IOException("Özgün split paketi bulunamadı.");
        PackageManager manager = context.getPackageManager();
        Inspection inspection = new Inspection();
        Set<String> names = new HashSet<>();
        long totalBytes = 0;
        try (ZipFile zip = new ZipFile(bundle)) {
            Enumeration<? extends ZipEntry> entries = zip.entries();
            while (entries.hasMoreElements()) {
                ZipEntry entry = entries.nextElement();
                if (entry.isDirectory()) continue;
                String name = entry.getName();
                if (!names.add(name)) throw new IOException("Paket içinde yinelenen dosya adı var: " + name);
                if (name.toLowerCase(Locale.ROOT).endsWith(".obb")) {
                    throw new IOException("Bu XAPK, ayrıca OBB veri dosyası içeriyor; OBB kurulumu henüz desteklenmiyor.");
                }
                if (!name.toLowerCase(Locale.ROOT).endsWith(".apk")) continue;
                if (entry.getSize() <= 0 || entry.getSize() > MAX_EXPANDED_BYTES) {
                    throw new IOException("Split APK boyutu okunamadı veya güvenli sınırı aşıyor.");
                }
                totalBytes += entry.getSize();
                if (totalBytes > MAX_EXPANDED_BYTES || inspection.modules.size() >= MAX_MODULES) {
                    throw new IOException("Split paketi güvenli boyut veya modül sınırını aşıyor.");
                }
                Module module = new Module();
                module.name = name;
                module.size = entry.getSize();
                inspection.modules.add(module);
            }
            if (inspection.modules.isEmpty()) throw new IOException("Paket içinde kurulabilir APK bileşeni bulunamadı.");

            // A temporary module copy is used only for Android's APK parser and
            // signature verifier. Session input remains the untouched ZIP bytes.
            for (Module module : inspection.modules) {
                ZipEntry entry = zip.getEntry(module.name);
                File probe = File.createTempFile("apkcleaner-split-check-", ".apk", context.getCacheDir());
                try {
                    try (InputStream input = zip.getInputStream(entry); OutputStream output = new FileOutputStream(probe)) {
                        copy(input, output, entry.getSize());
                    }
                    ApkVerifier.Result verified = new ApkVerifier.Builder(probe)
                            .setMinCheckedPlatformVersion(Build.VERSION.SDK_INT)
                            .setMaxCheckedPlatformVersion(Build.VERSION.SDK_INT)
                            .build().verify();
                    if (!verified.isVerified() || verified.getSignerCertificates().isEmpty()) {
                        throw new IOException("Özgün APK bileşeninin imzası doğrulanamadı: " + entry.getName());
                    }
                    String currentSigner = signerFingerprint(verified.getSignerCertificates());
                    if (inspection.signer == null) {
                        inspection.signer = currentSigner;
                    } else if (!inspection.signer.equals(currentSigner)) {
                        throw new IOException("Split bileşenlerinin imzaları birbiriyle eşleşmiyor.");
                    }
                    // PackageManager may not parse a standalone configuration split
                    // without its base. Android validates every module on commit.
                    PackageInfo info = manager.getPackageArchiveInfo(probe.getAbsolutePath(), 0);
                    if (info != null && info.packageName != null) {
                        module.baseCandidate = true;
                        long currentVersion = versionCode(info);
                        if (inspection.packageName == null) {
                            inspection.packageName = info.packageName;
                            inspection.version = currentVersion;
                            inspection.versionName = info.versionName;
                        } else if (!inspection.packageName.equals(info.packageName) || inspection.version != currentVersion) {
                            throw new IOException("Split bileşenlerinin paket adı veya sürümü birbiriyle eşleşmiyor.");
                        }
                    }
                } finally {
                    probe.delete();
                }
            }
            if (inspection.packageName == null) {
                throw new IOException("Temel APK bileşeninin paket bilgisi okunamadı.");
            }
            inspection.baseName = chooseBase(inspection.modules);
            if (inspection.baseName == null) {
                throw new IOException("Bu cihazla uyumlu temel APK bileşeni bulunamadı.");
            }
            classifyModules(context, inspection);
            int signingFlags = Build.VERSION.SDK_INT >= 28
                    ? PackageManager.GET_SIGNING_CERTIFICATES : PackageManager.GET_SIGNATURES;
            try {
                PackageInfo installed = manager.getPackageInfo(inspection.packageName, signingFlags);
                inspection.installed = true;
                if (!inspection.signer.equals(installedSignerFingerprint(installed))) {
                    inspection.blockedReason = "Cihazdaki uygulamanın imzası bu paketle farklı. Mevcut verileri korumak için üzerine kurulum yapılmaz.";
                }
                if (inspection.blockedReason == null && versionCode(installed) > inspection.version) {
                    inspection.blockedReason = "Cihazda daha yeni bir sürüm kurulu. Sürüm düşürme başlatılmaz.";
                }
            } catch (PackageManager.NameNotFoundException ignored) {
                // New installation, not an update.
            }
            return inspection;
        }
    }

    private static String chooseBase(List<Module> modules) {
        Module fallback = null;
        int bestScore = Integer.MIN_VALUE;
        for (Module module : modules) {
            if (!module.baseCandidate) continue;
            String lower = module.name.toLowerCase(Locale.ROOT);
            if (lower.equals("base.apk") || lower.endsWith("/base.apk")
                    || lower.equals("base-master.apk") || lower.endsWith("/base-master.apk")) {
                return module.name;
            }
            String abi = detectedAbi(module.name);
            int abiIndex = -1;
            if (abi != null) {
                for (int index = 0; index < Build.SUPPORTED_ABIS.length; index++) {
                    if (abi.equals(Build.SUPPORTED_ABIS[index])) { abiIndex = index; break; }
                }
                if (abiIndex < 0) continue;
            }
            int score = lower.contains("universal") ? 80 : !lower.contains("standalone") ? 70 : 40;
            if (abiIndex >= 0) score += 20 - abiIndex;
            if (score > bestScore) { fallback = module; bestScore = score; }
        }
        return fallback == null ? null : fallback.name;
    }

    private static void classifyModules(Context context, Inspection inspection) {
        String preferredAbi = null;
        boolean hasAbiSplits = false;
        for (String abi : Build.SUPPORTED_ABIS) {
            for (Module module : inspection.modules) {
                if (!module.baseCandidate && abi.equals(detectedAbi(module.name))) { preferredAbi = abi; break; }
            }
            if (preferredAbi != null) break;
        }
        int deviceDensity = context.getResources().getDisplayMetrics().densityDpi;
        String preferredDensity = null;
        int closest = Integer.MAX_VALUE;
        for (int index = 0; index < DENSITIES.length; index++) {
            for (Module module : inspection.modules) {
                if (module.baseCandidate || !DENSITIES[index].equals(detectedDensity(module.name))) continue;
                int distance = Math.abs(deviceDensity - DENSITY_DPI[index]);
                if (distance < closest) { closest = distance; preferredDensity = DENSITIES[index]; }
            }
        }
        Set<String> languages = new HashSet<>();
        android.os.LocaleList locales = context.getResources().getConfiguration().getLocales();
        for (int index = 0; index < locales.size(); index++) {
            languages.add(locales.get(index).getLanguage().toLowerCase(Locale.ROOT));
        }
        for (Module module : inspection.modules) {
            if (module.name.equals(inspection.baseName)) {
                module.kind = "base"; module.autoSelected = true;
            } else if (module.baseCandidate) {
                module.kind = "alternative";
            } else if ((module.value = detectedAbi(module.name)) != null) {
                hasAbiSplits = true;
                module.kind = "abi"; module.autoSelected = module.value.equals(preferredAbi);
            } else if ((module.value = detectedDensity(module.name)) != null) {
                module.kind = "density"; module.autoSelected = module.value.equals(preferredDensity);
            } else if ((module.value = detectedLanguage(module.name)) != null) {
                module.kind = "language"; module.autoSelected = languages.contains(module.value);
            } else {
                module.kind = "feature"; module.autoSelected = true;
            }
        }
        if (hasAbiSplits && preferredAbi == null) {
            inspection.blockedReason = "Paketin işlemci mimarisi bu cihazla eşleşmiyor; uygun ABI split'i bulunamadı.";
        }
    }

    private static String normalizedStem(String name) {
        String basename = name.substring(name.lastIndexOf('/') + 1).toLowerCase(Locale.ROOT);
        return basename.substring(0, basename.length() - 4).replace('.', '_').replace('-', '_');
    }

    private static String detectedAbi(String name) {
        String stem = "_" + normalizedStem(name) + "_";
        String[] known = {"arm64_v8a", "armeabi_v7a", "riscv64", "x86_64", "armeabi", "x86"};
        for (String abi : known) {
            if (stem.contains("_" + abi + "_")) return abi.replace('_', '-').replace("x86-64", "x86_64");
        }
        return null;
    }

    private static String detectedDensity(String name) {
        String stem = "_" + normalizedStem(name) + "_";
        for (String density : DENSITIES) {
            if (stem.contains("_" + density + "_")) return density;
        }
        return null;
    }

    private static String detectedLanguage(String name) {
        Matcher match = LANGUAGE.matcher(normalizedStem(name));
        return match.find() ? match.group(1) : null;
    }

    private static void copy(InputStream input, OutputStream output, long expected) throws IOException {
        byte[] buffer = new byte[1024 * 1024];
        long written = 0;
        int count;
        while ((count = input.read(buffer)) != -1) {
            written += count;
            if (written > expected) throw new IOException("APK bileşeni bildirilen boyutu aşıyor.");
            output.write(buffer, 0, count);
        }
        if (written != expected) throw new IOException("APK bileşeni eksik veya bozuk.");
    }

    @SuppressWarnings("deprecation")
    private static long versionCode(PackageInfo info) {
        return Build.VERSION.SDK_INT >= 28 ? info.getLongVersionCode() : info.versionCode;
    }

    private static String signerFingerprint(List<X509Certificate> certificates) throws Exception {
        List<String> values = new ArrayList<>();
        for (X509Certificate certificate : certificates) {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(certificate.getEncoded());
            values.add(android.util.Base64.encodeToString(digest, android.util.Base64.NO_WRAP));
        }
        Collections.sort(values);
        return String.join("|", values);
    }

    private static String installedSignerFingerprint(PackageInfo info) throws Exception {
        android.content.pm.Signature[] signatures = Build.VERSION.SDK_INT >= 28 && info.signingInfo != null
                ? info.signingInfo.getApkContentsSigners() : info.signatures;
        if (signatures == null || signatures.length == 0) return "";
        List<String> values = new ArrayList<>();
        for (android.content.pm.Signature signature : signatures) {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(signature.toByteArray());
            values.add(android.util.Base64.encodeToString(digest, android.util.Base64.NO_WRAP));
        }
        Collections.sort(values);
        return String.join("|", values);
    }

    public static final class ResultReceiver extends BroadcastReceiver {
        @Override public void onReceive(Context context, Intent intent) {
            int status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
            int sessionId = intent.getIntExtra("session", -1);
            if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
                @SuppressWarnings("deprecation")
                Intent confirmation = intent.getParcelableExtra(Intent.EXTRA_INTENT);
                if (confirmation == null) {
                    notifyResult(context, sessionId, "error", "Android kurulum onayı açılamadı.");
                    return;
                }
                confirmation.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                try {
                    context.startActivity(confirmation);
                    notifyResult(context, sessionId, "confirmation_opened", "Android kurulum onayı açıldı.");
                } catch (RuntimeException error) {
                    notifyResult(context, sessionId, "error", "Android kurulum onayı açılamadı.");
                }
                return;
            }
            if (status == PackageInstaller.STATUS_SUCCESS) {
                notifyResult(context, sessionId, "installed", "Özgün split paketi kuruldu.");
            } else {
                String detail = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
                String reason;
                switch (status) {
                    case PackageInstaller.STATUS_FAILURE_ABORTED:
                        reason = "Kurulum iptal edildi veya Android onayı verilmedi."; break;
                    case PackageInstaller.STATUS_FAILURE_BLOCKED:
                        reason = "Kurulum cihaz ilkesi veya güvenlik denetimi tarafından engellendi."; break;
                    case PackageInstaller.STATUS_FAILURE_CONFLICT:
                        reason = "Cihazdaki bir uygulama veya mevcut imza bu kurulumla çakışıyor."; break;
                    case PackageInstaller.STATUS_FAILURE_INVALID:
                        reason = "Seçilen APK bileşenleri eksik, bozuk ya da birbiriyle uyumsuz."; break;
                    case PackageInstaller.STATUS_FAILURE_STORAGE:
                        reason = "Kurulum için yeterli depolama alanı bulunamadı."; break;
                    case PackageInstaller.STATUS_FAILURE_INCOMPATIBLE:
                        reason = "Paket bu cihazın Android sürümü veya donanımıyla uyumlu değil."; break;
                    default:
                        reason = Build.VERSION.SDK_INT >= 34 && status == PackageInstaller.STATUS_FAILURE_TIMEOUT
                                ? "Kurulum zaman aşımına uğradı." : "Android split kurulumunu tamamlayamadı (" + status + ").";
                }
                String message = detail == null || detail.trim().isEmpty()
                        ? reason : reason + "\nAndroid ayrıntısı: " + detail.trim();
                notifyResult(context, sessionId,
                        status == PackageInstaller.STATUS_FAILURE_ABORTED ? "cancelled" : "error", message);
            }
        }

        private void notifyResult(Context context, int sessionId, String status, String message) {
            if (!"confirmation_opened".equals(status)) {
                InstallHistoryStore.completed(context, sessionId, status, message);
            }
            try {
                String payload = new JSONObject().put("status", status).put("message", message).toString();
                if (MainActivity.publishOriginalSplitInstallResult(payload)) return;
            } catch (Exception ignored) {}
            Toast.makeText(context, message, Toast.LENGTH_LONG).show();
        }
    }
}
