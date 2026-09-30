import io
import os
import re
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "android"
APK = Path(os.environ.get(
    "APK_CLEANER_ANDROID_APK",
    ROOT / "outputs" / "APK-Cleaner-Studio-v0.6.3-dev.2-Android.apk",
))


class AndroidPackageTests(unittest.TestCase):
    def test_direct_split_install_history_is_local_and_bounded(self):
        native = (ANDROID / "app/src/main/java/com/apkcleaner/studio/InstallHistoryStore.java").read_text(encoding="utf-8")
        installer = (ANDROID / "app/src/main/java/com/apkcleaner/studio/OriginalSplitInstaller.java").read_text(encoding="utf-8")
        activity = (ANDROID / "app/src/main/java/com/apkcleaner/studio/MainActivity.java").read_text(encoding="utf-8")
        self.assertIn('MAX_ENTRIES = 50', native)
        self.assertIn('Context.MODE_PRIVATE', native)
        self.assertIn('InstallHistoryStore.submitted', installer)
        self.assertIn('InstallHistoryStore.completed', installer)
        self.assertIn('getInstallHistory()', activity)
        self.assertIn('getNativeCacheStorage()', activity)
        self.assertIn('clearNativeCache()', activity)
        self.assertIn('file.lastModified() >= cutoff', activity)
        html = (ROOT / "studio/web/index.html").read_text(encoding="utf-8")
        self.assertIn('id="storageCard"', html)
        self.assertIn('id="installHistoryCard"', html)
        for tester in ('@mrepomod', '@Seckkk', '@muharrem0001', '@ByTECHNO'):
            self.assertIn(f'<b>{tester}</b><small>Tester</small>', html)
        self.assertLess(html.index('<b>@mrepomod</b>'), html.index('<b>@Seckkk</b>'))
        for asset in ('tester-mrepomod.png', 'tester-seckkk.png', 'tester-muharrem0001.png', 'tester-bytechno.png'):
            self.assertIn(f'src="icons/{asset}', html)
            self.assertTrue((ROOT / "studio/web/icons" / asset).is_file())

    def test_requested_android_matrix_and_version_are_declared(self):
        gradle = (ANDROID / "app" / "build.gradle").read_text(encoding="utf-8")
        self.assertIn('applicationId "com.apkrepo.apkcleanerstudio"', gradle)
        self.assertNotIn("applicationIdSuffix", gradle)
        self.assertIn("versionCode 6302", gradle)
        self.assertIn('versionName "0.6.3-dev.2"', gradle)
        self.assertGreaterEqual(gradle.count("signingConfig signingConfigs.studio"), 2)
        self.assertIn("enableV1Signing false", gradle)
        self.assertIn("enableV2Signing true", gradle)
        self.assertIn("enableV3Signing true", gradle)
        self.assertIn('abiFilters "arm64-v8a", "armeabi-v7a"', gradle)
        self.assertNotRegex(gradle, r'abiFilters[^\n]*(?:x86|mips)')
        self.assertIn('resourceConfigurations += ["en", "tr"]', gradle)
        self.assertEqual(
            {path.name for path in (ANDROID / "app" / "src" / "main" / "res").glob("mipmap-*")},
            {"mipmap-xhdpi", "mipmap-xxhdpi"},
        )

    def test_android_shell_does_not_require_termux_or_external_java(self):
        manifest = (ANDROID / "app" / "src" / "main" / "AndroidManifest.xml").read_text(encoding="utf-8")
        activity = (ANDROID / "app" / "src" / "main" / "java" / "com" / "apkcleaner" / "studio" / "MainActivity.java").read_text(encoding="utf-8")
        runner = (ANDROID / "app" / "src" / "main" / "java" / "com" / "apkcleaner" / "studio" / "EmbeddedToolRunner.java").read_text(encoding="utf-8")
        self.assertIn("com.chaquo.python.android.PyApplication", manifest)
        self.assertIn("new WebView(this)", activity)
        self.assertIn("setOnApplyWindowInsetsListener", activity)
        self.assertIn("DirectDexPatcher.execute", runner)
        self.assertIn("BinaryManifestPatcher.main", runner)
        self.assertIn("Main.execute", runner)
        self.assertIn("new ApkVerifier.Builder", runner)
        self.assertIn("setAlignmentPreserved(false)", runner)
        self.assertIn("setLibraryPageAlignmentBytes(16 * 1024)", runner)
        self.assertNotIn("ProcessBuilder", runner)

    def test_android_can_import_installed_app_packages_locally(self):
        manifest = (ANDROID / "app" / "src" / "main" / "AndroidManifest.xml").read_text(encoding="utf-8")
        activity = (ANDROID / "app" / "src" / "main" / "java" / "com" / "apkcleaner" / "studio" / "MainActivity.java").read_text(encoding="utf-8")
        html = (ROOT / "studio" / "web" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "studio" / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("android.permission.QUERY_ALL_PACKAGES", manifest)
        self.assertIn("listInstalledPackages", activity)
        self.assertIn("requestInstalledPackages", activity)
        self.assertIn("loadInstalledPackages(false);", activity)
        self.assertIn("final int size = 72;", activity)
        self.assertIn("getApplicationIcon", activity)
        self.assertIn("onInstalledPackagesLoaded", activity)
        self.assertIn("importInstalledPackage", activity)
        self.assertIn("splitSourceDirs", activity)
        self.assertIn("installedShareFilename(info, splitPackage ? \".apks\" : \".apk\")", activity)
        self.assertIn('id="installedAppsButton"', html)
        self.assertIn('id="installedApps"', html)
        self.assertIn("onInstalledPackageImported", script)
        self.assertIn("installed-app-icon", script)
        self.assertIn("awaitEngineReady(30000)", activity)
        self.assertIn("ensureEngine", activity)

    def test_android_local_engine_recovers_after_idle_or_process_pressure(self):
        activity = (ANDROID / "app" / "src" / "main" / "java" / "com" / "apkcleaner" / "studio" / "MainActivity.java").read_text(encoding="utf-8")
        service = (ANDROID / "app" / "src" / "main" / "java" / "com" / "apkcleaner" / "studio" / "EngineService.java").read_text(encoding="utf-8")
        script = (ROOT / "studio" / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("return START_STICKY", service)
        self.assertIn("isReachable", service)
        self.assertIn("startScheduled.compareAndSet(false, true)", service)
        self.assertIn("ensureEngineService();", activity)
        self.assertIn("if (!awaitEngineReady(30000))", activity)
        self.assertIn("recoverEmbeddedEngine", script)
        self.assertIn("async function apiFetch", script)

    def test_android_tool_output_and_dex_work_are_bounded(self):
        runner = (ANDROID / "app/src/main/java/com/apkcleaner/studio/EmbeddedToolRunner.java").read_text(encoding="utf-8")
        engine = (ROOT / "studio/engine.py").read_text(encoding="utf-8")
        self.assertIn("TailOutputStream capture = new TailOutputStream()", runner)
        self.assertIn("private static final int CAPACITY = 64 * 1024", runner)
        self.assertIn("if (!CANCEL_REQUESTED.get()) Thread.interrupted();", runner)
        self.assertIn("worker_limit = 1 if android", engine)

    def test_android_keeps_screen_awake_only_while_processing(self):
        activity = (ANDROID / "app/src/main/java/com/apkcleaner/studio/MainActivity.java").read_text(encoding="utf-8")
        script = (ROOT / "studio/web/app.js").read_text(encoding="utf-8")
        self.assertIn("setProcessingActive(boolean active)", activity)
        self.assertIn("WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON", activity)
        self.assertIn("getWindow().addFlags", activity)
        self.assertIn("getWindow().clearFlags", activity)
        self.assertIn("function setJobRunning(active)", script)
        self.assertIn("setProcessingActive?.(state.jobRunning)", script)
        self.assertIn("setJobRunning(true)", script)
        self.assertIn("finally { setJobRunning(false);", script)

    def test_installed_icons_preserve_density_dependent_insets_before_scaling(self):
        activity = (ANDROID / "app/src/main/java/com/apkcleaner/studio/MainActivity.java").read_text(encoding="utf-8")
        renderer = activity.split("private String drawableDataUri(", 1)[1].split("private static void copyFile", 1)[0]
        self.assertIn("drawable.getIntrinsicWidth()", renderer)
        self.assertIn("drawable.getIntrinsicHeight()", renderer)
        self.assertIn("setBounds(0, 0, logicalSize, logicalSize)", renderer)
        self.assertIn("canvas.scale(size / (float) logicalSize", renderer)
        self.assertIn("Bitmap.createBitmap(size, size", renderer)
        self.assertNotIn("Bitmap.createBitmap(logicalSize", renderer)
        self.assertLess(renderer.index("if (drawable == null)"), renderer.index("Bitmap.createBitmap"))

    def test_android_renderer_and_late_callbacks_have_lifecycle_guards(self):
        activity = (ANDROID / "app/src/main/java/com/apkcleaner/studio/MainActivity.java").read_text(encoding="utf-8")
        service = (ANDROID / "app/src/main/java/com/apkcleaner/studio/EngineService.java").read_text(encoding="utf-8")
        self.assertIn("onRenderProcessGone", activity)
        self.assertIn("showRendererRecovery(view, detail.didCrash());", activity)
        self.assertIn("generation == viewGeneration", activity)
        self.assertIn("closed = true;", activity)
        self.assertIn("webView = null;", activity)
        self.assertIn("cancelFileSelection();", activity)
        self.assertIn("Executors.newFixedThreadPool(3)", activity)
        self.assertIn("allowCoreThreadTimeOut(true)", activity)
        self.assertNotIn("setLayerType(View.LAYER_TYPE_HARDWARE", activity)
        self.assertNotIn("startService(new Intent(this, EngineService.class).setAction", activity)
        self.assertIn("private static final ExecutorService executor", service)
        self.assertNotIn("executor.shutdown()", service)

    def test_android_icons_use_launcher_and_recycle_on_draw_failure(self):
        activity = (ANDROID / "app/src/main/java/com/apkcleaner/studio/MainActivity.java").read_text(encoding="utf-8")
        self.assertIn("Intent.CATEGORY_LAUNCHER", activity)
        self.assertIn("launcher.loadIcon(manager)", activity)
        self.assertIn("android.R.attr.state_enabled", activity)
        self.assertIn("drawable.jumpToCurrentState()", activity)
        rasterizer = activity.split("private String drawableDataUri", 1)[1].split("private static void copyFile", 1)[0]
        self.assertLess(rasterizer.index("try ("), rasterizer.index("drawable.draw("))
        self.assertIn("bitmap.recycle()", rasterizer.split("finally", 1)[1])

    def test_android_smart_install_and_package_sharing_are_wired(self):
        manifest = (ANDROID / "app" / "src" / "main" / "AndroidManifest.xml").read_text(encoding="utf-8")
        activity = (ANDROID / "app" / "src" / "main" / "java" / "com" / "apkcleaner" / "studio" / "MainActivity.java").read_text(encoding="utf-8")
        script = (ROOT / "studio" / "web" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "studio" / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("android.permission.REQUEST_INSTALL_PACKAGES", manifest)
        self.assertIn("android.permission.REQUEST_DELETE_PACKAGES", manifest)
        self.assertIn(".ApkFileProvider", manifest)
        self.assertIn("prepareInstall", activity)
        self.assertIn("applicationInfo.minSdkVersion", activity)
        self.assertIn("Build.SUPPORTED_ABIS", activity)
        self.assertIn("signerDigest", activity)
        self.assertIn("requires_uninstall", activity)
        self.assertIn("Intent.ACTION_UNINSTALL_PACKAGE", activity)
        self.assertIn("waitForPackageRemoval", activity)
        self.assertIn("shareInstalledPackage", activity)
        self.assertIn("info.versionName", activity)
        self.assertIn("Deflater.NO_COMPRESSION", activity)
        self.assertIn("input.transferTo", activity)
        self.assertIn("uriForInstalled", activity)
        self.assertIn("UNKNOWN_SOURCE_PERMISSION", activity)
        self.assertIn("cancelPendingInstall", activity)
        self.assertIn("STATE_INSTALL_PATH", activity)
        self.assertIn("permission_required", activity)
        self.assertIn("installUpdate", activity)
        self.assertIn("downloadOfficialUpdate", activity)
        self.assertIn("APKRepoGroup/APK-Cleaner-Studio/releases/download", activity)
        self.assertIn('id="installButton"', html)
        self.assertIn('id="shareOutputButton"', html)
        self.assertIn("onNativeAction", script)
        self.assertIn("cancelPendingInstall", script)
        self.assertNotIn('id="appDialogAlternate"', html)
        self.assertIn("selectedInstalledPackage", script)
        self.assertIn('data-installed-action="share"', script)
        self.assertIn('data-installed-action="process"', script)
        self.assertIn("installed-app-actions", script)
        self.assertIn("updateInstalledAppSelection(item);", script)
        self.assertIn("finishInstalledShareUi()", script)
        self.assertGreaterEqual(activity.count("openConnection(Proxy.NO_PROXY)"), 3)

    def test_official_update_verifies_both_apk_files_before_install(self):
        activity = (ANDROID / "app/src/main/java/com/apkcleaner/studio/MainActivity.java").read_text(encoding="utf-8")
        self.assertIn('verifiedApkSignerDigest(apk, "Güncelleme paketinin")', activity)
        self.assertIn('verifiedApkSignerDigest(new File(getApplicationInfo().sourceDir), "Cihazdaki uygulamanın")', activity)
        self.assertIn("new ApkVerifier.Builder(apk)", activity)
        self.assertIn(".setMinCheckedPlatformVersion(Build.VERSION.SDK_INT)", activity)
        self.assertIn(".setMaxCheckedPlatformVersion(Build.VERSION.SDK_INT)", activity)
        self.assertIn("!verified.isVerified() || verified.getSignerCertificates().isEmpty()", activity)
        self.assertIn('if (!archiveSigner.equals(installedSigner))', activity)

    def test_no_ad_analysis_strictly_disables_cleaning_profiles(self):
        script = (ROOT / "studio" / "web" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "studio" / "web" / "index.html").read_text(encoding="utf-8")
        css = (ROOT / "studio" / "web" / "theme.css").read_text(encoding="utf-8")
        self.assertIn("button.disabled = !profilesEnabled", script)
        self.assertIn("updateAdProfileAvailability(wantsAds)", script)
        self.assertNotIn("!state.patchAdsSelected) state.patchAdsSelected = true", script)
        self.assertIn("#noAdsProfileNote", script)
        self.assertIn('id="noAdsProfileNote"', html)
        self.assertIn(".profile:disabled", css)

    def test_android_runtime_uses_a_self_healing_private_temp_directory(self):
        entry = (ANDROID / "app" / "src" / "main" / "python" / "android_entry.py").read_text(encoding="utf-8")
        engine = (ROOT / "studio" / "engine.py").read_text(encoding="utf-8")
        self.assertIn('Path(data_root).resolve() / "runtime" / "tmp"', entry)
        for name in ('"TMPDIR"', '"TEMP"', '"TMP"', '"APK_CLEANER_TEMP_ROOT"'):
            self.assertIn(name, entry)
        self.assertIn("tempfile.tempdir = value", entry)
        self.assertIn("def _temporary_directory", engine)
        self.assertIn("root.mkdir(parents=True, exist_ok=True)", engine)
        self.assertIn('with _temporary_directory(prefix="apkcleaner-")', engine)
        self.assertIn('with _temporary_directory(prefix="apkcleaner-split-scan-")', engine)

    def test_android_16_applies_system_bar_theme_after_content_view_exists(self):
        activity = (ANDROID / "app" / "src" / "main" / "java" / "com" / "apkcleaner" / "studio" / "MainActivity.java").read_text(encoding="utf-8")
        on_create = activity[activity.index("@Override protected void onCreate"):activity.index("private void showStartupError")]
        self.assertLess(on_create.index("buildUi();"), on_create.index("applySystemTheme(nativeTheme());"))
        self.assertIn("getWindow().getDecorView().getWindowInsetsController()", activity)

    def test_built_apk_contains_only_requested_native_abis_and_shared_ui(self):
        if not APK.is_file():
            self.skipTest("Android geliştirme APK'sı henüz derlenmedi.")
        with zipfile.ZipFile(APK) as archive:
            names = archive.namelist()
            abis = {name.split("/")[1] for name in names if name.startswith("lib/")}
            self.assertEqual(abis, {"arm64-v8a", "armeabi-v7a"})
            self.assertIn("assets/output-signing.p12", names)
            app_archive = zipfile.ZipFile(io.BytesIO(archive.read("assets/chaquopy/app.imy")))
            embedded = set(app_archive.namelist())
        for required in (
            "android_entry.py", "engine.py", "server.py", "profiles.json",
            "web/index.html", "web/app.js", "web/styles.css", "web/ui-runtime.js",
        ):
            self.assertIn(required, embedded)
        for relative in ("engine.py", "server.py", "profiles.json", "web/index.html", "web/app.js", "web/theme.css", "web/ui-runtime.js"):
            self.assertEqual(
                app_archive.read(relative),
                (ROOT / "studio" / relative).read_bytes(),
                f"Android APK içindeki {relative} ortak kaynakla eşleşmiyor.",
            )

    def test_embedded_apkeditor_keeps_only_default_and_turkish_messages(self):
        jar = ANDROID / "app" / "libs" / "APKEditor-android.jar"
        if not jar.is_file():
            self.skipTest("Android araçları henüz eşitlenmedi.")
        with zipfile.ZipFile(jar) as archive:
            names = set(archive.namelist())
        self.assertIn("strings/strings.properties", names)
        self.assertNotIn("strings/strings-ar.properties", names)
        self.assertNotIn("strings/strings-fr.properties", names)

    def test_android_embedded_ui_hides_network_only_panels_and_keeps_manual_certificate_tool(self):
        css = (ROOT / "studio" / "web" / "theme.css").read_text(encoding="utf-8")
        html = (ROOT / "studio" / "web" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "studio" / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('html[data-embedded="android"] .mobile-https-banner', css)
        self.assertIn('html[data-embedded="android"] #clientCard', css)
        self.assertIn('details class="mobile-cert auto-hide-scrollbar"', html)
        self.assertIn('html[data-embedded="android"] #toolCard .mobile-cert { display: block !important; }', css)
        self.assertIn('html[data-embedded="android"] #toolCard { display: flex !important; }', css)
        self.assertIn('class="embedded-cert-copy"', html)
        self.assertIn('html[data-embedded="android"] #toolCard .host-cert-copy { display: none; }', css)
        self.assertIn("height: calc(61px + var(--android-status-inset", css)
        self.assertIn("globalThis.setNativeTheme", script)
        self.assertIn("AndroidThemeBridge", script)
        self.assertIn("}, 510);", script)
        self.assertIn("opacity .51s", css)
        self.assertIn("download?filename=${encodeURIComponent(outputFilename)}", script)
        self.assertIn("focusProcessingView(\"#workingView\")", script)
        self.assertIn("orientation: landscape", css)
        self.assertIn("align-self: center", css)
        self.assertIn("Seçili işlemleri başlat", script)
        self.assertIn('id="normalizeDex"', html)
        self.assertIn("normalize_dex", script)
        self.assertIn("Gelişmiş", html)
        self.assertIn("app-dialog-card", css)
        self.assertIn("report-viewer-card", css)
        self.assertIn("body.modal-scroll-locked", css)
        self.assertIn("overscroll-behavior: contain", css)
        self.assertIn('lockPageScroll("app-dialog")', script)
        self.assertIn('lockPageScroll("report-viewer")', script)
        self.assertIn('lockPageScroll("message-review")', script)
        self.assertIn('lockPageScroll("installed-apps")', script)
        self.assertIn('containModalTouch("#installedApps", ".installed-apps-list")', script)
        self.assertIn('containModalTouch("#reportViewer", "#reportViewerContent")', script)
        self.assertIn('containModalTouch("#messageReview", ".message-review-body")', script)
        self.assertIn("openReportViewer", script)
        self.assertIn('data-history-report=', script)
        self.assertIn("-webkit-text-stroke: 0 transparent", css)
        self.assertIn('"CN=APK Cleaner Studio"', (ROOT / "studio" / "engine.py").read_text(encoding="utf-8"))

    def test_android_download_bridge_preserves_generated_apk_filename(self):
        activity = (ANDROID / "app" / "src" / "main" / "java" / "com" / "apkcleaner" / "studio" / "MainActivity.java").read_text(encoding="utf-8")
        strings = (ANDROID / "app" / "src" / "main" / "res" / "values-tr" / "strings.xml").read_text(encoding="utf-8")
        self.assertIn('getQueryParameter("filename")', activity)
        self.assertIn('"APK-Cleaner-Studio-output.apk"', activity)
        self.assertIn("suggestedDownloadFilename", activity)
        self.assertIn('setRequestProperty("X-Client-ID"', activity)
        self.assertIn("getResponseCode()", activity)
        self.assertIn("onSaveInstanceState", activity)
        self.assertIn("getContentResolver().delete(destination", activity)
        self.assertIn("Çıktı kaydedildi", strings)

    def test_direct_dex_patcher_covers_programmatic_google_banner_and_normalization(self):
        source = (ROOT / "direct-patcher" / "src" / "local" / "apkcleaner" / "dex" / "DirectDexPatcher.java").read_text(encoding="utf-8")
        self.assertIn("AdManagerAdView", source)
        self.assertIn("setAdUnitId", source)
        self.assertIn("--normalize-dex", source)
        self.assertIn("messageContext", source)
        self.assertIn("FragmentManager", source)
        self.assertIn("namedMessageHelper", source)

    def test_android_release_uses_shrinking_and_integrated_system_bars(self):
        gradle = (ANDROID / "app" / "build.gradle").read_text(encoding="utf-8")
        build_script = (ANDROID / "build-android.ps1").read_text(encoding="utf-8")
        styles = (ANDROID / "app" / "src" / "main" / "res" / "values" / "styles.xml").read_text(encoding="utf-8")
        activity = (ANDROID / "app" / "src" / "main" / "java" / "com" / "apkcleaner" / "studio" / "MainActivity.java").read_text(encoding="utf-8")
        launcher = (ANDROID / "app" / "src" / "main" / "java" / "com" / "apkcleaner" / "studio" / "LauncherActivity.java").read_text(encoding="utf-8")
        self.assertIn("debuggable false", gradle)
        self.assertIn("jniDebuggable false", gradle)
        self.assertIn("minifyEnabled true", gradle)
        self.assertIn("shrinkResources true", gradle)
        self.assertIn("zipalign.exe", build_script)
        self.assertIn("-c -P 16 4", build_script)
        self.assertIn("apksigner.bat", build_script)
        self.assertIn("verify --verbose", build_script)
        self.assertIn("@android:color/transparent", styles)
        self.assertIn("setDecorFitsSystemWindows(false)", activity)
        self.assertIn("setOnApplyWindowInsetsListener", activity)
        self.assertIn("LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS", activity)
        self.assertIn("view.setPadding(0, 0, 0, bottom)", activity)
        self.assertIn("--android-safe-right", activity)
        self.assertIn("OvershootInterpolator", launcher)
        self.assertIn("R.mipmap.ic_launcher", launcher)
        self.assertIn("progress.animate().scaleX(1f)", launcher)

    def test_android_status_inset_is_converted_from_physical_to_css_pixels(self):
        activity = (ANDROID / "app" / "src" / "main" / "java" / "com" / "apkcleaner" / "studio" / "MainActivity.java").read_text(encoding="utf-8")
        self.assertIn("statusInsetTop / density", activity)
        self.assertIn("+ cssInsetTop +", activity)

    def test_android_sync_script_covers_all_shared_runtime_files(self):
        sync = (ROOT / "packaging" / "sync_android.py").read_text(encoding="utf-8")
        for name in ("engine.py", "server.py", "setup_tools.py", "updater.py", "device_catalog.py"):
            self.assertIn(f'"{name}"', sync)
        self.assertIn("shutil.copytree(STUDIO / \"web\"", sync)
        for relative in ("engine.py", "server.py", "profiles.json", "web/app.js", "web/theme.css", "web/ui-runtime.js"):
            self.assertEqual(
                (ANDROID / "app" / "src" / "main" / "python" / relative).read_bytes(),
                (ROOT / "studio" / relative).read_bytes(),
                f"Android çalışma kaynağı güncel değil: {relative}",
            )


if __name__ == "__main__":
    unittest.main()
