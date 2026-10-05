package com.apkcleaner.studio;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.PackageInfo;
import android.content.pm.ApplicationInfo;
import android.content.pm.ResolveInfo;
import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Rect;
import android.graphics.drawable.Drawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.util.Base64;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.window.OnBackInvokedDispatcher;
import android.webkit.JavascriptInterface;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.MimeTypeMap;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.RenderProcessGoneDetail;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import com.android.apksig.ApkVerifier;

import java.io.InputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.lang.ref.WeakReference;
import java.nio.channels.FileChannel;
import java.net.HttpURLConnection;
import java.net.Proxy;
import java.net.URL;
import java.security.MessageDigest;
import java.security.cert.X509Certificate;
import java.util.Locale;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.HashMap;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.zip.Deflater;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

import org.json.JSONArray;
import org.json.JSONObject;

public final class MainActivity extends Activity {
    private static final int PICK_FILE = 2001;
    private static final int SAVE_DOWNLOAD = 2002;
    private static final int NOTIFICATION_PERMISSION = 2003;
    private static final int UNINSTALL_FOR_REPLACE = 2004;
    private static final int UNKNOWN_SOURCE_PERMISSION = 2005;
    private static final String LOCAL_ORIGIN = "http://127.0.0.1:" + EngineService.PORT;
    private static final String STATE_DOWNLOAD_URL = "download_url";
    private static final String STATE_DOWNLOAD_MIME = "download_mime";
    private static final String STATE_DOWNLOAD_NAME = "download_name";
    private static final String STATE_DOWNLOAD_AGENT = "download_agent";
    private static final String STATE_INSTALL_PATH = "install_path";
    private static final String STATE_INSTALL_PACKAGE = "install_package";
    private static final String STATE_INSTALL_TOKEN = "install_token";
    private static final String STATE_INSTALL_ACTION = "install_action";
    private static final String STATE_SPLIT_INSTALL_PATH = "split_install_path";
    private static final String STATE_SPLIT_INSTALL_SELECTION = "split_install_selection";
    private static final String CLIENT_COOKIE_NAME = "apk_cleaner_client_id";
    private static final String TAG = "APKCleanerDownload";
    private WebView webView;
    private FrameLayout root;
    private LinearLayout loading;
    private TextView loadingText;
    private ValueCallback<Uri[]> fileCallback;
    private String pendingDownloadUrl;
    private String pendingDownloadMime;
    private String pendingDownloadFilename;
    private String pendingDownloadUserAgent;
    private int statusInsetTop;
    private int safeInsetLeft;
    private int safeInsetRight;
    private final ExecutorService io = Executors.newFixedThreadPool(3);
    private boolean activityVisible;
    private volatile boolean closed;
    private volatile int viewGeneration;
    private final ThreadLocal<Integer> taskGeneration = new ThreadLocal<>();
    private Button rendererRetry;
    private final AtomicBoolean installedPackagesLoading = new AtomicBoolean(false);
    private final AtomicBoolean installedPackagesPublishRequested = new AtomicBoolean(false);
    private final Map<String, Object> installedShareLocks = new ConcurrentHashMap<>();
    private volatile String installedPackagesCache = "[]";
    private volatile boolean installedPackagesReady;
    private volatile File pendingNativeInstall;
    private volatile String pendingNativeInstallPackage;
    private volatile String pendingNativeInstallToken;
    private volatile String pendingNativeInstallAction = "install";
    private volatile File pendingOriginalSplitArchive;
    private volatile String pendingOriginalSplitSelection;
    private static volatile WeakReference<MainActivity> activeInstance = new WeakReference<>(null);

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        DiagnosticRecorder.install(this);
        activeInstance = new WeakReference<>(this);
        ((ThreadPoolExecutor) io).setKeepAliveTime(15, TimeUnit.SECONDS);
        ((ThreadPoolExecutor) io).allowCoreThreadTimeOut(true);
        if (state != null) {
            pendingDownloadUrl = state.getString(STATE_DOWNLOAD_URL);
            pendingDownloadMime = state.getString(STATE_DOWNLOAD_MIME);
            pendingDownloadFilename = state.getString(STATE_DOWNLOAD_NAME);
            pendingDownloadUserAgent = state.getString(STATE_DOWNLOAD_AGENT);
            String installPath = state.getString(STATE_INSTALL_PATH);
            pendingNativeInstall = installPath == null ? null : new File(installPath);
            pendingNativeInstallPackage = state.getString(STATE_INSTALL_PACKAGE);
            pendingNativeInstallToken = state.getString(STATE_INSTALL_TOKEN);
            pendingNativeInstallAction = state.getString(STATE_INSTALL_ACTION, "install");
            String splitInstallPath = state.getString(STATE_SPLIT_INSTALL_PATH);
            pendingOriginalSplitArchive = splitInstallPath == null ? null : new File(splitInstallPath);
            pendingOriginalSplitSelection = state.getString(STATE_SPLIT_INSTALL_SELECTION);
        }
        try {
            // Paket listesini ekran ve yerel motor hazırlanırken paralel olarak
            // oluşturmaya başla; seçim penceresinin ilk açılışını bekletme.
            loadInstalledPackages(false);
            configureEdgeToEdge();
            buildUi();
            // Android 16'da WindowInsetsController ancak decor view oluşturulduktan
            // sonra güvenle alınabiliyor. Temayı setContentView sonrasında uygula.
            applySystemTheme(nativeTheme());
            configureBackNavigation();
            requestNotificationPermission();
            // Launcher normal açılışı başlatır; bu çağrı servis bellek baskısı veya
            // uzun bekleme sonrasında düşmüşse aynı motoru idempotent biçimde onarır.
            ensureEngineService();
            waitForEngine();
        } catch (Throwable error) {
            DiagnosticRecorder.record(this, "startup", error);
            showStartupError(error);
        }
    }

    // Results from native work must never target a closed or replaced WebView.
    private void executeIo(Runnable task) {
        if (closed) return;
        final int generation = viewGeneration;
        try {
            io.execute(() -> {
                if (closed) return;
                taskGeneration.set(generation);
                try { task.run(); }
                finally { taskGeneration.remove(); }
            });
        } catch (RejectedExecutionException error) {
            if (!closed) Log.w(TAG, "Arka plan işi başlatılamadı", error);
        }
    }

    private void postToUi(Runnable task) {
        Integer origin = taskGeneration.get();
        final int generation = origin == null ? viewGeneration : origin;
        runOnUiThread(() -> {
            if (!closed && !isFinishing() && !isDestroyed() && generation == viewGeneration) task.run();
        });
    }

    private void cancelFileSelection() {
        ValueCallback<Uri[]> callback = fileCallback;
        fileCallback = null;
        if (callback != null) {
            try { callback.onReceiveValue(null); }
            catch (RuntimeException error) { Log.w(TAG, "Dosya seçimi kapatılamadı", error); }
        }
    }

    private void disposeWebView(WebView view) {
        if (view == null) return;
        if (view.getParent() instanceof ViewGroup) ((ViewGroup) view.getParent()).removeView(view);
        view.destroy();
    }

    private void showRendererRecovery(WebView failed, boolean crashed) {
        Log.w(TAG, "WebView çizim süreci sonlandı; crashed=" + crashed);
        DiagnosticRecorder.record(this, crashed ? "renderer-crash" : "renderer-closed", null);
        if (failed != webView) {
            disposeWebView(failed);
            return;
        }
        viewGeneration++;
        webView = null;
        cancelFileSelection();
        disposeWebView(failed);
        if (closed || isFinishing() || isDestroyed()) return;
        installedPackagesCache = "[]";
        installedPackagesReady = false;
        loading.setVisibility(View.VISIBLE);
        loading.getChildAt(0).setVisibility(View.GONE);
        loadingText.setText(R.string.renderer_closed);
        if (rendererRetry == null) {
            rendererRetry = new Button(this);
            rendererRetry.setText(R.string.renderer_retry);
            loading.addView(rendererRetry);
            rendererRetry.setOnClickListener(button -> {
                if (closed || webView != null) return;
                rendererRetry.setVisibility(View.GONE);
                loading.getChildAt(0).setVisibility(View.VISIBLE);
                loadingText.setText(R.string.loading);
                try {
                    webView = new WebView(this);
                    root.addView(webView, 0, new FrameLayout.LayoutParams(
                            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
                    configureWebView();
                    webViewBackground("light".equals(nativeTheme()));
                    waitForEngine();
                } catch (RuntimeException error) {
                    Log.e(TAG, "WebView yeniden açılamadı", error);
                    WebView broken = webView;
                    webView = null;
                    disposeWebView(broken);
                    loading.getChildAt(0).setVisibility(View.GONE);
                    loadingText.setText(R.string.renderer_restart_error);
                    rendererRetry.setVisibility(View.VISIBLE);
                }
            });
        }
        // Never automatically reload a crashing URL in a loop.
        rendererRetry.setVisibility(View.VISIBLE);
    }

    private void showStartupError(Throwable error) {
        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setGravity(Gravity.CENTER);
        panel.setPadding(56, 56, 56, 56);
        boolean light = "light".equals(nativeTheme());
        panel.setBackgroundColor(light ? Color.rgb(242, 245, 239) : Color.rgb(7, 16, 13));

        TextView title = new TextView(this);
        title.setText(R.string.startup_failed);
        title.setTextSize(23);
        title.setTextColor(light ? Color.rgb(17, 28, 23) : Color.rgb(238, 245, 239));
        title.setGravity(Gravity.CENTER);
        panel.addView(title, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        TextView detail = new TextView(this);
        detail.setText(UserErrorMessages.describe(error, "Uygulama başlatılamadı. Hata raporunu inceleyip yeniden dene."));
        detail.setTextSize(14);
        detail.setTextColor(light ? Color.rgb(83, 103, 94) : Color.rgb(143, 164, 154));
        detail.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams detailParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        detailParams.topMargin = 28;
        panel.addView(detail, detailParams);
        setContentView(panel);
    }

    private void buildUi() {
        root = new FrameLayout(this);
        boolean light = "light".equals(nativeTheme());
        root.setBackgroundColor(light ? Color.rgb(242, 245, 239) : Color.rgb(7, 16, 13));
        applySystemBarInsets(root);
        webView = new WebView(this);
        root.addView(webView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        loading = new LinearLayout(this);
        loading.setOrientation(LinearLayout.VERTICAL);
        loading.setGravity(Gravity.CENTER);
        loading.setPadding(48, 48, 48, 48);
        ProgressBar spinner = new ProgressBar(this);
        loading.addView(spinner, new LinearLayout.LayoutParams(56, 56));
        loadingText = new TextView(this);
        loadingText.setText(R.string.loading);
        loadingText.setTextColor(light ? Color.rgb(17, 28, 23) : Color.rgb(238, 245, 239));
        loadingText.setTextSize(16);
        loadingText.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams textParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        textParams.topMargin = 24;
        loading.addView(loadingText, textParams);
        root.addView(loading, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(root);
        configureWebView();
    }

    private void configureWebView() {
        WebView.setWebContentsDebuggingEnabled(false);
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowContentAccess(true);
        settings.setAllowFileAccess(false);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setSafeBrowsingEnabled(true);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setTextZoom(100);
        // The interface is already sized for the device. Repeated taps on a
        // selectable card must not trigger WebView's persistent smart zoom.
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setUserAgentString(settings.getUserAgentString() + " APKCleanerStudio/Android");
        webView.addJavascriptInterface(new ThemeBridge(), "AndroidThemeBridge");

        CookieManager.getInstance().setAcceptCookie(true);
        webView.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (isTrustedLocalUri(uri)) return false;
                openExternal(uri);
                return true;
            }

            @Override public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
                showRendererRecovery(view, detail.didCrash());
                return true;
            }

            @Override public void onPageFinished(WebView view, String url) {
                if (closed || view != webView) return;
                publishStatusInset();
                publishUiVisibility();
                loading.setVisibility(View.GONE);
                webView.setVisibility(View.VISIBLE);
            }
        });
        webView.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                cancelFileSelection();
                fileCallback = callback;
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT)
                        .addCategory(Intent.CATEGORY_OPENABLE)
                        .setType("application/octet-stream")
                        .putExtra(Intent.EXTRA_MIME_TYPES, new String[] {
                                "application/vnd.android.package-archive", "application/zip", "application/octet-stream"
                        });
                try {
                    startActivityForResult(intent, PICK_FILE);
                } catch (ActivityNotFoundException | SecurityException error) {
                    fileCallback = null;
                    return false;
                }
                return true;
            }
        });
        webView.setDownloadListener(downloadListener());
        webView.setVisibility(View.INVISIBLE);
    }

    private DownloadListener downloadListener() {
        return (url, userAgent, contentDisposition, mimeType, contentLength) -> {
            if (!isTrustedJobUri(Uri.parse(url))) {
                Toast.makeText(this, R.string.save_failed, Toast.LENGTH_LONG).show();
                return;
            }
            pendingDownloadUrl = url;
            pendingDownloadMime = mimeType == null ? "application/octet-stream" : mimeType;
            pendingDownloadFilename = suggestedDownloadFilename(url, contentDisposition, pendingDownloadMime);
            pendingDownloadUserAgent = userAgent;
            Intent save = new Intent(Intent.ACTION_CREATE_DOCUMENT)
                    .addCategory(Intent.CATEGORY_OPENABLE)
                    .setType(pendingDownloadMime)
                    .putExtra(Intent.EXTRA_TITLE, pendingDownloadFilename);
            try {
                startActivityForResult(save, SAVE_DOWNLOAD);
            } catch (ActivityNotFoundException | SecurityException error) {
                clearPendingDownload();
                Toast.makeText(this, R.string.save_failed, Toast.LENGTH_LONG).show();
            }
        };
    }

    private static boolean isTrustedLocalUri(Uri uri) {
        if (uri == null || !"http".equalsIgnoreCase(uri.getScheme())) return false;
        String host = uri.getHost();
        if (!("127.0.0.1".equals(host) || "localhost".equalsIgnoreCase(host))) return false;
        int port = uri.getPort();
        return port == EngineService.PORT;
    }

    private static boolean isTrustedJobUri(Uri uri) {
        String path = uri == null ? null : uri.getPath();
        return isTrustedLocalUri(uri) && path != null && path.startsWith("/api/jobs/");
    }

    private String suggestedDownloadFilename(String url, String contentDisposition, String mimeType) {
        String candidate = "";
        try {
            candidate = Uri.parse(url).getQueryParameter("filename");
        } catch (RuntimeException ignored) {}
        if (candidate == null || candidate.trim().isEmpty()) {
            candidate = android.webkit.URLUtil.guessFileName(url, contentDisposition, mimeType);
        }
        candidate = new java.io.File(candidate == null ? "" : candidate).getName()
                .replaceAll("[\\x00-\\x1f\\x7f]", "").trim();
        boolean generic = candidate.isEmpty()
                || candidate.equalsIgnoreCase("download.bin")
                || candidate.equalsIgnoreCase("download");
        if (generic) candidate = "APK-Cleaner-Studio-output.apk";
        if (candidate.length() > 180) candidate = candidate.substring(candidate.length() - 180);
        return candidate;
    }

    private void waitForEngine() {
        executeIo(() -> {
            boolean reachable = awaitEngineReady(30000);
            postToUi(() -> {
                if (webView == null) return;
                if (reachable) {
                    webView.loadUrl(LOCAL_ORIGIN + "/?embedded=android&nativeTheme=" + nativeTheme());
                } else {
                    loadingText.setText(EngineService.startupError.isEmpty()
                            ? getString(R.string.load_error) : EngineService.startupError);
                }
            });
        });
    }

    private void ensureEngineService() {
        if (closed) return;
        Intent service = new Intent(this, EngineService.class);
        try {
            if (Build.VERSION.SDK_INT >= 26) startForegroundService(service); else startService(service);
        } catch (RuntimeException error) {
            Log.w(TAG, "Yerel motor yeniden başlatılamadı", error);
        }
    }

    private boolean awaitEngineReady(long timeoutMs) {
        if (EngineService.isReachable(220)) return true;
        ensureEngineService();
        long deadline = System.currentTimeMillis() + Math.max(1000, timeoutMs);
        while (!closed && !Thread.currentThread().isInterrupted() && System.currentTimeMillis() < deadline) {
            if (EngineService.isReachable(220)) return true;
            try {
                Thread.sleep(100);
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                return false;
            }
        }
        return false;
    }

    private String nativeTheme() {
        int mode = getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK;
        return mode == Configuration.UI_MODE_NIGHT_YES ? "dark" : "light";
    }

    private void applySystemBarInsets(View target) {
        target.setOnApplyWindowInsetsListener((view, insets) -> {
            int bottom;
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars());
                android.graphics.Insets cutout = insets.getInsets(WindowInsets.Type.displayCutout());
                statusInsetTop = Math.max(bars.top, cutout.top);
                safeInsetLeft = Math.max(bars.left, cutout.left);
                safeInsetRight = Math.max(bars.right, cutout.right);
                bottom = bars.bottom;
            } else {
                statusInsetTop = insets.getSystemWindowInsetTop();
                safeInsetLeft = insets.getSystemWindowInsetLeft();
                safeInsetRight = insets.getSystemWindowInsetRight();
                bottom = insets.getSystemWindowInsetBottom();
            }
            // Arka plan ve WebView kamera çentiğinin arkasına kadar uzanır.
            // Güvenli yatay boşluk yalnızca web üst çubuğunun içeriğine CSS
            // değişkenleriyle uygulanır; böylece kenarda siyah şerit oluşmaz.
            view.setPadding(0, 0, 0, bottom);
            publishStatusInset();
            return insets;
        });
        target.requestApplyInsets();
    }

    @Override public void onConfigurationChanged(Configuration configuration) {
        super.onConfigurationChanged(configuration);
        String theme = nativeTheme();
        applySystemTheme(theme);
        if (root != null) root.requestApplyInsets();
        if (webView != null) {
            postToUi(() -> {
                if (webView == null) return;
                publishStatusInset();
                // Activity yeniden oluşturulmadan yön değiştirdiği için WebView'e
                // yeni görsel alanı aynı karede bildir. Aktif işlem kartı ve yüzde
                // bilgisi kaybolmadan responsive ölçüler yeniden hesaplanır.
                String script = "globalThis.setNativeTheme?.('" + theme + "');"
                        + "globalThis.dispatchEvent(new Event('resize'));"
                        + "document.documentElement.style.setProperty('--app-viewport-width',innerWidth+'px')";
                webView.evaluateJavascript(script, null);
            });
        }
    }

    private void configureEdgeToEdge() {
        Window window = getWindow();
        window.setStatusBarColor(Color.TRANSPARENT);
        if (Build.VERSION.SDK_INT >= 30) {
            window.setDecorFitsSystemWindows(false);
        } else {
            window.getDecorView().setSystemUiVisibility(
                    View.SYSTEM_UI_FLAG_LAYOUT_STABLE | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN);
        }
        if (Build.VERSION.SDK_INT >= 28) {
            WindowManager.LayoutParams attributes = window.getAttributes();
            attributes.layoutInDisplayCutoutMode = Build.VERSION.SDK_INT >= 30
                    ? WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS
                    : WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;
            window.setAttributes(attributes);
        }
    }

    private void applySystemTheme(String theme) {
        boolean light = "light".equals(theme);
        int navigation = light ? Color.rgb(242, 245, 239) : Color.rgb(7, 16, 13);
        getWindow().setNavigationBarColor(navigation);
        webViewBackground(light);
        if (Build.VERSION.SDK_INT >= 30) {
            // Window#getInsetsController bazı Android 16 üretici sürümlerinde
            // decor view hazır değilken NullPointerException üretebiliyor.
            WindowInsetsController controller = getWindow().getDecorView().getWindowInsetsController();
            if (controller != null) {
                int mask = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                        | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
                controller.setSystemBarsAppearance(light ? mask : 0, mask);
            }
        } else if (Build.VERSION.SDK_INT >= 23) {
            int flags = View.SYSTEM_UI_FLAG_LAYOUT_STABLE | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN;
            if (light) flags |= View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
            if (light && Build.VERSION.SDK_INT >= 26) flags |= View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
            getWindow().getDecorView().setSystemUiVisibility(flags);
        }
    }

    private void webViewBackground(boolean light) {
        if (webView != null) webView.setBackgroundColor(light ? Color.rgb(242, 245, 239) : Color.rgb(7, 16, 13));
        if (root != null) root.setBackgroundColor(light ? Color.rgb(242, 245, 239) : Color.rgb(7, 16, 13));
    }

    private void publishStatusInset() {
        if (webView == null) return;
        // WindowInsets fiziksel piksel, WebView CSS değişkeni ise yoğunluktan
        // bağımsız piksel kullanır. Doğrudan aktarmak yüksek DPI ekranlarda üst
        // çubuğu 2-4 kat gereksiz büyütür.
        float density = getResources().getDisplayMetrics().density;
        int cssInsetTop = Math.max(0, Math.round(statusInsetTop / density));
        int cssInsetLeft = Math.max(0, Math.round(safeInsetLeft / density));
        int cssInsetRight = Math.max(0, Math.round(safeInsetRight / density));
        webView.evaluateJavascript(
                "document.documentElement.style.setProperty('--android-status-inset','" + cssInsetTop + "px');"
                        + "document.documentElement.style.setProperty('--android-safe-left','" + cssInsetLeft + "px');"
                        + "document.documentElement.style.setProperty('--android-safe-right','" + cssInsetRight + "px')", null);
    }

    private void configureBackNavigation() {
        if (Build.VERSION.SDK_INT >= 33) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                    OnBackInvokedDispatcher.PRIORITY_DEFAULT, this::handleBack);
        }
    }

    private void handleBack() {
        if (webView != null && webView.canGoBack()) webView.goBack(); else finish();
    }

    private final class ThemeBridge {
        @JavascriptInterface public void setTheme(String theme) {
            if (!"light".equals(theme) && !"dark".equals(theme)) return;
            postToUi(() -> applySystemTheme(theme));
        }

        @JavascriptInterface public void setProcessingActive(boolean active) {
            postToUi(() -> {
                if (closed || isFinishing()) return;
                if (active) getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                else getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            });
        }

        /** Returns only the already prepared cache and never blocks WebView. */
        @JavascriptInterface public String listInstalledPackages() {
            return installedPackagesCache;
        }

        /** Starts or joins the asynchronous scan and returns through JavaScript. */
        @JavascriptInterface public void requestInstalledPackages() {
            loadInstalledPackages(true);
        }

        /** Allows failed localhost requests to revive the foreground engine once and retry. */
        @JavascriptInterface public void ensureEngine() {
            ensureEngineService();
        }

        /** Packages the selected installed app and streams it to the existing local analysis endpoint. */
        @JavascriptInterface public void importInstalledPackage(String packageName) {
            executeIo(() -> {
                File staged = null;
                try {
                    PackageInfo info = getPackageManager().getPackageInfo(packageName, 0);
                    if (info.applicationInfo == null || info.applicationInfo.sourceDir == null) {
                        throw new IOException("Uygulamanın kurulum paketi okunamadı.");
                    }
                    boolean splitPackage = info.applicationInfo.splitSourceDirs != null
                            && info.applicationInfo.splitSourceDirs.length > 0;
                    String installedFilename = installedShareFilename(info, splitPackage ? ".apks" : ".apk");
                    if (!splitPackage) {
                        staged = new File(getCacheDir(), installedFilename);
                        copyFile(new File(info.applicationInfo.sourceDir), staged);
                    } else {
                        staged = new File(getCacheDir(), installedFilename);
                        try (ZipOutputStream output = new ZipOutputStream(new FileOutputStream(staged))) {
                            addZipFile(output, new File(info.applicationInfo.sourceDir), "base.apk");
                            int index = 1;
                            for (String split : info.applicationInfo.splitSourceDirs) {
                                File source = new File(split);
                                String entry = source.getName();
                                if (!entry.toLowerCase(Locale.ROOT).endsWith(".apk")) entry = "split-" + index + ".apk";
                                addZipFile(output, source, entry);
                                index++;
                            }
                        }
                    }
                    String response = uploadForAnalysis(staged);
                    JSONObject payload = new JSONObject(response);
                    payload.put("native_file", new JSONObject()
                            .put("name", staged.getName()).put("size", staged.length()));
                    publishInstalledImport(payload.toString());
                } catch (Exception error) {
                    try {
                        publishInstalledImport(new JSONObject().put("error",
                                messageOf(error, "Yüklü uygulama alınamadı.")).toString());
                    } catch (Exception ignored) {}
                } finally {
                    if (staged != null) staged.delete();
                }
            });
        }

        @JavascriptInterface public void prepareInstall(String url, String filename) {
            executeIo(() -> prepareNativeInstall(url, filename));
        }

        @JavascriptInterface public void inspectOriginalSplit(String url, String filename) {
            executeIo(() -> prepareOriginalSplitInstall(url, filename));
        }

        @JavascriptInterface public void installOriginalSplit(String selectedModules) {
            executeIo(() -> beginOriginalSplitInstall(selectedModules));
        }

        @JavascriptInterface public String getInstallHistory() {
            return InstallHistoryStore.list(MainActivity.this);
        }

        @JavascriptInterface public String getNativeCacheStorage() {
            return nativeCacheStorage(false);
        }

        @JavascriptInterface public String clearNativeCache() {
            return nativeCacheStorage(true);
        }

        @JavascriptInterface public void installUpdate(String url, String filename, String sha256) {
            executeIo(() -> prepareOfficialUpdate(url, filename, sha256));
        }

        @JavascriptInterface public void confirmReplaceInstall(String token) {
            postToUi(() -> {
                if (pendingNativeInstall == null || token == null || !token.equals(pendingNativeInstallToken)) return;
                try {
                    Intent remove = new Intent(Intent.ACTION_UNINSTALL_PACKAGE,
                            Uri.parse("package:" + pendingNativeInstallPackage));
                    remove.putExtra(Intent.EXTRA_RETURN_RESULT, true);
                    if (remove.resolveActivity(getPackageManager()) == null) {
                        remove = new Intent(Intent.ACTION_DELETE,
                                Uri.parse("package:" + pendingNativeInstallPackage));
                        remove.putExtra(Intent.EXTRA_RETURN_RESULT, true);
                    }
                    startActivityForResult(remove, UNINSTALL_FOR_REPLACE);
                } catch (ActivityNotFoundException | SecurityException error) {
                    publishNativeAction("install", jsonError("Mevcut uygulama kaldırıcısı açılamadı."));
                }
            });
        }

        @JavascriptInterface public void cancelPendingInstall(String token) {
            if (token == null || !token.equals(pendingNativeInstallToken)) return;
            File abandoned = pendingNativeInstall;
            clearPendingNativeInstall();
            if (abandoned != null) abandoned.delete();
        }

        @JavascriptInterface public void shareOutput(String url, String filename) {
            executeIo(() -> {
                try { shareFile(downloadNativePackage(url, filename, "processed")); }
                catch (Exception error) { publishNativeAction("share", jsonError(messageOf(error, "Çıktı paylaşılamadı."))); }
            });
        }

        @JavascriptInterface public void shareInstalledPackage(String packageName) {
            executeIo(() -> {
                try {
                    PackageInfo info = getPackageManager().getPackageInfo(packageName, 0);
                    if (info.applicationInfo == null || info.applicationInfo.sourceDir == null) {
                        throw new IOException("Kurulum paketi okunamadı.");
                    }
                    String filename = installedShareFilename(info,
                            info.applicationInfo.splitSourceDirs == null || info.applicationInfo.splitSourceDirs.length == 0
                                    ? ".apk" : ".apks");
                    if (info.applicationInfo.splitSourceDirs == null || info.applicationInfo.splitSourceDirs.length == 0) {
                        // Tek APK cihazdaki kurulu kaynaktan doğrudan yayınlanır;
                        // geçici kopya veya ikinci bir paketleme yapılmaz.
                        shareUri(ApkFileProvider.uriForInstalled(packageName, filename,
                                getPackageName() + ".files"), filename);
                    } else {
                        synchronized (installedShareLocks.computeIfAbsent(packageName, key -> new Object())) {
                            shareFile(stageInstalledSplitPackage(info, filename));
                        }
                    }
                }
                catch (Exception error) { publishNativeAction("share", jsonError(messageOf(error, "Uygulama paketi paylaşılamadı."))); }
            });
        }
    }

    private String nativeCacheStorage(boolean clean) {
        File directory = new File(getCacheDir(), "native-packages");
        long cutoff = System.currentTimeMillis() - 24L * 60L * 60L * 1000L;
        long bytes = 0;
        int count = 0;
        int removed = 0;
        File[] files = directory.listFiles();
        if (files != null) for (File file : files) {
            try {
                if (!file.isFile() || !file.getCanonicalFile().equals(file.getAbsoluteFile())
                        || file.lastModified() >= cutoff || file.equals(pendingNativeInstall)
                        || file.equals(pendingOriginalSplitArchive)) continue;
                if (clean && file.delete()) { removed++; continue; }
                count++;
                bytes += file.length();
            } catch (IOException ignored) {}
        }
        try { return new JSONObject().put("count", count).put("bytes", bytes).put("removed", removed).toString(); }
        catch (Exception ignored) { return "{}"; }
    }

    private File nativePackageDirectory() throws IOException {
        File directory = new File(getCacheDir(), "native-packages");
        if (!directory.isDirectory() && !directory.mkdirs()) throw new IOException("Geçici paket klasörü oluşturulamadı.");
        return directory;
    }

    private String safePackageFilename(String filename, String fallback) {
        String value = new File(filename == null ? "" : filename).getName()
                .replaceAll("[^\\p{L}\\p{N}._-]+", "-").replaceAll("^-+|-+$", "");
        return value.isEmpty() ? fallback : value;
    }

    private String safeShareFilenamePart(String value, String fallback) {
        String cleaned = (value == null ? "" : value)
                .replaceAll("[\\\\/:*?\"<>|\\p{Cntrl}]+", "-")
                .replaceAll("\\s+", " ").trim()
                .replaceAll("^[. ]+|[. ]+$", "");
        return cleaned.isEmpty() ? fallback : cleaned;
    }

    private String installedShareFilename(PackageInfo info, String extension) {
        String label = safeShareFilenamePart(String.valueOf(getPackageManager().getApplicationLabel(info.applicationInfo)), "Yüklü uygulama");
        String version = safeShareFilenamePart(info.versionName, "");
        return label + (version.isEmpty() ? "" : " v" + version) + extension;
    }

    private File stageInstalledSplitPackage(PackageInfo info, String filename) throws Exception {
        File destination = new File(nativePackageDirectory(), filename);
        if (destination.isFile() && destination.length() > 0
                && destination.lastModified() >= info.lastUpdateTime) return destination;
        File temporary = new File(nativePackageDirectory(), destination.getName() + ".part-" + UUID.randomUUID());
        try (ZipOutputStream output = new ZipOutputStream(new FileOutputStream(temporary))) {
            // Android splitleri ayrı APK dosyaları olarak tutar. Tek .apks çıktısı
            // için yalnızca bir kapsayıcı oluşturulur; içerik yeniden sıkıştırılmaz.
            output.setLevel(Deflater.NO_COMPRESSION);
            addZipFile(output, new File(info.applicationInfo.sourceDir), "base.apk");
            int index = 1;
            for (String split : info.applicationInfo.splitSourceDirs) {
                File source = new File(split);
                addZipFile(output, source, source.getName().toLowerCase(Locale.ROOT).endsWith(".apk") ? source.getName() : "split-" + index + ".apk");
                index++;
            }
        }
        replaceFile(temporary, destination);
        return destination;
    }

    private static void replaceFile(File temporary, File destination) throws IOException {
        if (destination.exists() && !destination.delete()) {
            temporary.delete();
            throw new IOException("Eski paylaşım paketi yenilenemedi.");
        }
        if (!temporary.renameTo(destination)) {
            temporary.delete();
            throw new IOException("Paylaşım paketi hazırlanamadı.");
        }
    }

    private File downloadNativePackage(String address, String filename, String prefix) throws Exception {
        if (address == null || !isTrustedJobUri(Uri.parse(address))) throw new IOException("Geçersiz yerel çıktı adresi.");
        File destination = new File(nativePackageDirectory(), prefix + "-" + UUID.randomUUID() + "-"
                + safePackageFilename(filename, "APK-Cleaner-Studio-output.apk"));
        HttpURLConnection connection = (HttpURLConnection) new URL(address).openConnection(Proxy.NO_PROXY);
        connection.setConnectTimeout(10000); connection.setReadTimeout(300000);
        String cookies = CookieManager.getInstance().getCookie(address);
        if (cookies != null) connection.setRequestProperty("Cookie", cookies);
        String client = cookieValue(cookies, CLIENT_COOKIE_NAME);
        if (!client.isEmpty()) connection.setRequestProperty("X-Client-ID", client);
        boolean completed = false;
        try {
            int status = connection.getResponseCode();
            if (status < 200 || status >= 300) throw new IOException("Yerel çıktı HTTP " + status + " döndürdü.");
            try (InputStream input = connection.getInputStream(); OutputStream output = new FileOutputStream(destination)) {
                byte[] buffer = new byte[1024 * 1024]; int count;
                while ((count = input.read(buffer)) >= 0) output.write(buffer, 0, count);
            }
            completed = true;
            return destination;
        } finally {
            connection.disconnect();
            if (!completed) destination.delete();
        }
    }

    private void prepareNativeInstall(String url, String filename) {
        try {
            File apk = downloadNativePackage(url, filename, "install");
            prepareNativeInstallFile(apk, false, "install");
        } catch (Exception error) { publishNativeAction("install", jsonError(messageOf(error, "APK kuruluma hazırlanamadı."))); }
    }

    private void prepareOriginalSplitInstall(String url, String filename) {
        File archive = null;
        try {
            String lower = filename == null ? "" : filename.toLowerCase(Locale.ROOT);
            Uri source = Uri.parse(url);
            if (!(lower.endsWith(".apks") || lower.endsWith(".apkm") || lower.endsWith(".xapk"))
                    || !isTrustedJobUri(source) || !source.getPath().endsWith("/source")) {
                throw new IOException("Doğrudan kurulum yalnızca özgün APKS, APKM veya XAPK paketiyle yapılır.");
            }
            archive = downloadNativePackage(url, filename, "original-split-install");
            String plan = OriginalSplitInstaller.inspect(this, archive);
            File previous = pendingOriginalSplitArchive;
            pendingOriginalSplitArchive = archive;
            pendingOriginalSplitSelection = null;
            if (previous != null && !previous.equals(archive)) previous.delete();
            publishNativeAction("split_install", plan);
        } catch (Exception error) {
            if (archive != null) archive.delete();
            publishNativeAction("split_install", jsonError(messageOf(error, "Özgün split paketi kuruluma hazırlanamadı.")));
        }
    }

    private void beginOriginalSplitInstall(String selectedModules) {
        File archive = pendingOriginalSplitArchive;
        if (archive == null || !archive.isFile()) {
            publishNativeAction("split_install", jsonError("Hazırlanan split paketi bulunamadı; dosyayı yeniden seç."));
            return;
        }
        try {
            new JSONArray(selectedModules);
            pendingOriginalSplitSelection = selectedModules;
            if (Build.VERSION.SDK_INT >= 26 && !getPackageManager().canRequestPackageInstalls()) {
                postToUi(() -> {
                    try {
                        startActivityForResult(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                                Uri.parse("package:" + getPackageName())), UNKNOWN_SOURCE_PERMISSION);
                        publishNativeAction("split_install", "{\"status\":\"permission_required\"}");
                    } catch (ActivityNotFoundException | SecurityException error) {
                        clearPendingOriginalSplitInstall();
                        publishNativeAction("split_install", jsonError("Bu kaynaktan yükleme izni ekranı açılamadı."));
                    }
                });
                return;
            }
            commitOriginalSplitInstall(archive, selectedModules);
        } catch (Exception error) {
            publishNativeAction("split_install", jsonError(messageOf(error, "Split bileşenleri okunamadı.")));
        }
    }

    private void clearPendingOriginalSplitInstall() {
        File archive = pendingOriginalSplitArchive;
        pendingOriginalSplitArchive = null;
        pendingOriginalSplitSelection = null;
        if (archive != null) archive.delete();
    }

    private void commitOriginalSplitInstall(File archive, String selectedModules) {
        try {
            publishNativeAction("split_install", OriginalSplitInstaller.install(this, archive, selectedModules));
        } catch (Exception error) {
            publishNativeAction("split_install", jsonError(messageOf(error, "Split kurulumu başlatılamadı.")));
        } finally {
            if (archive.equals(pendingOriginalSplitArchive)) {
                pendingOriginalSplitArchive = null;
                pendingOriginalSplitSelection = null;
            }
            archive.delete();
        }
    }

    static boolean publishOriginalSplitInstallResult(String payload) {
        MainActivity activity = activeInstance.get();
        if (activity == null || activity.closed || activity.webView == null) return false;
        activity.publishNativeAction("split_install", payload);
        return true;
    }

    private boolean isTrustedOfficialUpdateUrl(String address, String filename) {
        try {
            Uri uri = Uri.parse(address);
            String host = uri.getHost() == null ? "" : uri.getHost().toLowerCase(Locale.ROOT);
            String path = uri.getPath() == null ? "" : uri.getPath();
            return "https".equalsIgnoreCase(uri.getScheme())
                    && "github.com".equals(host)
                    && path.startsWith("/APKRepoGroup/APK-Cleaner-Studio/releases/download/")
                    && filename != null
                    && filename.matches("APK-Cleaner-Studio-v\\d+\\.\\d+\\.\\d+(?:-dev\\.\\d+)?-Android\\.apk")
                    && filename.equals(Uri.decode(path.substring(path.lastIndexOf('/') + 1)));
        } catch (RuntimeException ignored) {
            return false;
        }
    }

    private boolean isTrustedGithubDownloadHost(URL url) {
        String protocol = url.getProtocol() == null ? "" : url.getProtocol().toLowerCase(Locale.ROOT);
        String host = url.getHost() == null ? "" : url.getHost().toLowerCase(Locale.ROOT);
        return "https".equals(protocol) && ("github.com".equals(host)
                || host.endsWith(".githubusercontent.com") || host.endsWith(".githubassets.com"));
    }

    private File downloadOfficialUpdate(String address, String filename, String expectedSha256) throws Exception {
        String digestText = expectedSha256 == null ? "" : expectedSha256.trim().toLowerCase(Locale.ROOT);
        if (!isTrustedOfficialUpdateUrl(address, filename) || !digestText.matches("[a-f0-9]{64}")) {
            throw new IOException("Güncelleme paketi güvenilir GitHub kaydıyla eşleşmiyor.");
        }
        File destination = new File(nativePackageDirectory(), "update-" + UUID.randomUUID() + "-"
                + safePackageFilename(filename, "APK-Cleaner-Studio-update.apk"));
        HttpURLConnection connection = (HttpURLConnection) new URL(address).openConnection(Proxy.NO_PROXY);
        connection.setInstanceFollowRedirects(true);
        connection.setRequestProperty("User-Agent", "APK-Cleaner-Studio-Android-Updater/2.0");
        connection.setRequestProperty("Accept", "application/vnd.android.package-archive,application/octet-stream");
        connection.setConnectTimeout(20000);
        connection.setReadTimeout(300000);
        boolean completed = false;
        try {
            int status = connection.getResponseCode();
            if (status < 200 || status >= 300) throw new IOException("GitHub güncelleme sunucusu HTTP " + status + " döndürdü.");
            if (!isTrustedGithubDownloadHost(connection.getURL())) {
                throw new IOException("Güncelleme paketi güvenilir olmayan bir adrese yönlendirildi.");
            }
            long declared = connection.getContentLengthLong();
            if (declared > 750L * 1024L * 1024L) throw new IOException("Güncelleme paketi boyut sınırını aşıyor.");
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            long total = 0;
            try (InputStream input = connection.getInputStream(); OutputStream output = new FileOutputStream(destination)) {
                byte[] buffer = new byte[1024 * 1024]; int count;
                while ((count = input.read(buffer)) >= 0) {
                    total += count;
                    if (total > 750L * 1024L * 1024L) throw new IOException("Güncelleme paketi boyut sınırını aşıyor.");
                    digest.update(buffer, 0, count);
                    output.write(buffer, 0, count);
                }
            }
            StringBuilder actual = new StringBuilder(64);
            for (byte value : digest.digest()) actual.append(String.format(Locale.ROOT, "%02x", value & 0xff));
            if (!actual.toString().equals(digestText)) throw new IOException("Güncelleme paketinin SHA-256 doğrulaması başarısız oldu.");
            completed = true;
            return destination;
        } finally {
            connection.disconnect();
            if (!completed) destination.delete();
        }
    }

    private void prepareOfficialUpdate(String url, String filename, String sha256) {
        File apk = null;
        try {
            apk = downloadOfficialUpdate(url, filename, sha256);
            prepareNativeInstallFile(apk, true, "update");
        } catch (Exception error) {
            if (apk != null && apk != pendingNativeInstall) apk.delete();
            publishNativeAction("update", jsonError(messageOf(error, "Güncelleme indirilemedi.")));
        }
    }

    private void prepareNativeInstallFile(File apk, boolean officialUpdate, String action) throws Exception {
            PackageManager manager = getPackageManager();
            int flags = Build.VERSION.SDK_INT >= 28 ? PackageManager.GET_SIGNING_CERTIFICATES : PackageManager.GET_SIGNATURES;
            PackageInfo archive = manager.getPackageArchiveInfo(apk.getAbsolutePath(), flags);
            if (archive == null || archive.applicationInfo == null || archive.packageName == null) throw new IOException("APK paket bilgileri okunamadı.");
            archive.applicationInfo.sourceDir = apk.getAbsolutePath();
            archive.applicationInfo.publicSourceDir = apk.getAbsolutePath();
            JSONArray incompatibilities = new JSONArray();
            if (archive.applicationInfo.minSdkVersion > Build.VERSION.SDK_INT) {
                incompatibilities.put("Paket Android " + archive.applicationInfo.minSdkVersion + " veya üzerini gerektiriyor; cihaz Android " + Build.VERSION.SDK_INT + " kullanıyor.");
            }
            Set<String> apkAbis = apkAbis(apk);
            if (!apkAbis.isEmpty()) {
                boolean supported = false;
                for (String abi : Build.SUPPORTED_ABIS) if (apkAbis.contains(abi)) { supported = true; break; }
                if (!supported) incompatibilities.put("Paketin işlemci mimarisi (" + String.join(", ", apkAbis) + ") bu cihazla uyumlu değil.");
            }
            JSONObject result = new JSONObject().put("package", archive.packageName).put("filename", apk.getName());
            if (incompatibilities.length() > 0) {
                result.put("status", "incompatible").put("reasons", incompatibilities);
                apk.delete(); publishNativeAction(action, result.toString()); return;
            }
            PackageInfo installed = null;
            try { installed = manager.getPackageInfo(archive.packageName, flags); } catch (PackageManager.NameNotFoundException ignored) {}
            if (officialUpdate && !getPackageName().equals(archive.packageName)) {
                apk.delete();
                throw new IOException("Güncelleme paketi APK Cleaner Studio kimliğiyle eşleşmiyor.");
            }
            if (installed != null) {
                JSONArray reasons = new JSONArray();
                // Some Android package managers leave archive signingInfo empty even
                // for a valid APK. Verify both actual APK files for official updates.
                String archiveSigner = officialUpdate
                        ? verifiedApkSignerDigest(apk, "Güncelleme paketinin") : signerDigest(archive);
                String installedSigner = officialUpdate
                        ? verifiedApkSignerDigest(new File(getApplicationInfo().sourceDir), "Cihazdaki uygulamanın")
                        : signerDigest(installed);
                if (archiveSigner.isEmpty() || installedSigner.isEmpty()) {
                    throw new IOException("Paket imzası güvenli biçimde karşılaştırılamadı.");
                }
                if (!archiveSigner.equals(installedSigner)) reasons.put("Cihazdaki uygulama farklı bir imzayla kurulmuş.");
                if (officialUpdate && packageVersionCode(installed) >= packageVersionCode(archive)) reasons.put("Güncelleme paketi cihazdaki sürümden daha yeni değil.");
                else if (packageVersionCode(installed) > packageVersionCode(archive)) reasons.put("Cihazda daha yeni bir sürüm kurulu.");
                if (reasons.length() > 0) {
                    if (officialUpdate) {
                        apk.delete();
                        throw new IOException(reasons.join(" "));
                    }
                    pendingNativeInstall = apk; pendingNativeInstallPackage = archive.packageName;
                    pendingNativeInstallToken = UUID.randomUUID().toString();
                    pendingNativeInstallAction = action;
                    result.put("status", "requires_uninstall").put("reasons", reasons).put("token", pendingNativeInstallToken);
                    publishNativeAction(action, result.toString()); return;
                }
            }
            pendingNativeInstall = apk;
            pendingNativeInstallPackage = archive.packageName;
            pendingNativeInstallToken = null;
            pendingNativeInstallAction = action;
            launchInstaller(apk);
    }

    private Set<String> apkAbis(File apk) throws IOException {
        Set<String> result = new HashSet<>();
        try (java.util.zip.ZipFile archive = new java.util.zip.ZipFile(apk)) {
            java.util.Enumeration<? extends ZipEntry> entries = archive.entries();
            while (entries.hasMoreElements()) {
                String name = entries.nextElement().getName();
                if (name.startsWith("lib/") && name.endsWith(".so")) {
                    String[] parts = name.split("/"); if (parts.length > 2) result.add(parts[1]);
                }
            }
        }
        return result;
    }

    @SuppressWarnings("deprecation")
    private long packageVersionCode(PackageInfo info) {
        return Build.VERSION.SDK_INT >= 28 ? info.getLongVersionCode() : info.versionCode;
    }

    private String signerDigest(PackageInfo info) throws Exception {
        android.content.pm.Signature[] signatures = Build.VERSION.SDK_INT >= 28 && info.signingInfo != null
                ? info.signingInfo.getApkContentsSigners() : info.signatures;
        if (signatures == null || signatures.length == 0) return "";
        List<String> digests = new ArrayList<>();
        for (android.content.pm.Signature signature : signatures) {
            digests.add(Base64.encodeToString(
                    MessageDigest.getInstance("SHA-256").digest(signature.toByteArray()), Base64.NO_WRAP));
        }
        Collections.sort(digests);
        return String.join("|", digests);
    }

    private String verifiedApkSignerDigest(File apk, String description) throws Exception {
        if (apk == null || !apk.isFile()) throw new IOException(description + " APK dosyası okunamadı.");
        ApkVerifier.Result verified;
        try {
            verified = new ApkVerifier.Builder(apk)
                    .setMinCheckedPlatformVersion(Build.VERSION.SDK_INT)
                    .setMaxCheckedPlatformVersion(Build.VERSION.SDK_INT)
                    .build().verify();
        } catch (Exception error) {
            throw new IOException(description + " imzası doğrulanamadı.", error);
        }
        if (!verified.isVerified() || verified.getSignerCertificates().isEmpty()) {
            throw new IOException(description + " imzası doğrulanamadı.");
        }
        List<String> digests = new ArrayList<>();
        for (X509Certificate certificate : verified.getSignerCertificates()) {
            digests.add(Base64.encodeToString(
                    MessageDigest.getInstance("SHA-256").digest(certificate.getEncoded()), Base64.NO_WRAP));
        }
        Collections.sort(digests);
        return String.join("|", digests);
    }

    private Uri nativeUri(File file) { return ApkFileProvider.uriFor(file, getPackageName() + ".files"); }

    private void launchInstaller(File apk) {
        postToUi(() -> {
            String action = pendingNativeInstallAction == null ? "install" : pendingNativeInstallAction;
            if (Build.VERSION.SDK_INT >= 26 && !getPackageManager().canRequestPackageInstalls()) {
                try {
                    pendingNativeInstall = apk;
                    pendingNativeInstallToken = null;
                    startActivityForResult(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                            Uri.parse("package:" + getPackageName())), UNKNOWN_SOURCE_PERMISSION);
                    publishNativeAction(action, "{\"status\":\"permission_required\"}");
                } catch (ActivityNotFoundException | SecurityException error) {
                    clearPendingNativeInstall();
                    publishNativeAction(action, jsonError("Bilinmeyen uygulama yükleme izni ekranı açılamadı."));
                }
                return;
            }
            Uri uri = nativeUri(apk);
            Intent install = new Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
            try {
                startActivity(install);
                clearPendingNativeInstall();
                publishNativeAction(action, "{\"status\":\"installer_opened\"}");
            } catch (ActivityNotFoundException | SecurityException error) {
                clearPendingNativeInstall();
                publishNativeAction(action, jsonError("Android Paket Yükleyici açılamadı."));
            }
        });
    }

    private void clearPendingNativeInstall() {
        pendingNativeInstall = null;
        pendingNativeInstallPackage = null;
        pendingNativeInstallToken = null;
        pendingNativeInstallAction = "install";
    }

    private boolean packageIsInstalled(String packageName) {
        if (packageName == null || packageName.isEmpty()) return false;
        try {
            getPackageManager().getPackageInfo(packageName, 0);
            return true;
        } catch (PackageManager.NameNotFoundException ignored) {
            return false;
        }
    }

    private boolean waitForPackageRemoval(String packageName) {
        long deadline = android.os.SystemClock.uptimeMillis() + 8000L;
        do {
            if (!packageIsInstalled(packageName)) return true;
            try { Thread.sleep(120L); }
            catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                return false;
            }
        } while (android.os.SystemClock.uptimeMillis() < deadline);
        return !packageIsInstalled(packageName);
    }

    private void shareFile(File file) {
        shareUri(nativeUri(file), file.getName());
    }

    private void shareUri(Uri uri, String filename) {
        postToUi(() -> {
            Intent share = new Intent(Intent.ACTION_SEND).setType(filename.toLowerCase(Locale.ROOT).endsWith(".apk")
                    ? "application/vnd.android.package-archive" : "application/zip")
                    .putExtra(Intent.EXTRA_STREAM, uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            try { startActivity(Intent.createChooser(share, "Uygulama paketini paylaş")); publishNativeAction("share", "{\"status\":\"opened\"}"); }
            catch (ActivityNotFoundException | SecurityException error) { publishNativeAction("share", jsonError("Paylaşım uygulaması bulunamadı.")); }
        });
    }

    private String jsonError(String message) {
        try { return new JSONObject().put("status", "error").put("error", message).toString(); }
        catch (Exception ignored) { return "{\"status\":\"error\"}"; }
    }

    private String messageOf(Exception error, String fallback) {
        return UserErrorMessages.describe(error, fallback);
    }

    private void publishNativeAction(String action, String payload) {
        postToUi(() -> { if (webView != null) webView.evaluateJavascript(
                "globalThis.onNativeAction?.(" + JSONObject.quote(action) + "," + JSONObject.quote(payload) + ")", null); });
    }

    private void loadInstalledPackages(boolean publishWhenReady) {
        if (publishWhenReady) installedPackagesPublishRequested.set(true);
        if (installedPackagesReady) {
            if (installedPackagesPublishRequested.getAndSet(false)) publishInstalledPackages(installedPackagesCache);
            return;
        }
        if (!installedPackagesLoading.compareAndSet(false, true)) return;
        executeIo(() -> {
            String payload = "[]";
            try {
                payload = buildInstalledPackages();
                installedPackagesCache = payload;
                installedPackagesReady = true;
            } catch (Exception error) {
                Log.e(TAG, "Yüklü uygulamalar okunamadı.", error);
            } finally {
                installedPackagesLoading.set(false);
            }
            if (installedPackagesPublishRequested.getAndSet(false)) publishInstalledPackages(payload);
        });
    }

    private String buildInstalledPackages() throws Exception {
        JSONArray result = new JSONArray();
        PackageManager manager = getPackageManager();
        List<PackageInfo> packages = new ArrayList<>(manager.getInstalledPackages(0));
        packages.removeIf(item -> item.applicationInfo == null
                || item.packageName.equals(getPackageName())
                || item.applicationInfo.sourceDir == null);
        Map<String, String> labels = new HashMap<>();
        for (PackageInfo item : packages) {
            labels.put(item.packageName, String.valueOf(manager.getApplicationLabel(item.applicationInfo)));
        }
        Map<String, ResolveInfo> launcherIcons = new HashMap<>();
        Intent launcherIntent = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
        for (ResolveInfo launcher : manager.queryIntentActivities(launcherIntent, 0)) {
            if (launcher.activityInfo != null) launcherIcons.putIfAbsent(launcher.activityInfo.packageName, launcher);
        }
        packages.sort(Comparator
                .comparing((PackageInfo item) -> (item.applicationInfo.flags & ApplicationInfo.FLAG_SYSTEM) != 0)
                .thenComparing(item -> labels.get(item.packageName),
                        String.CASE_INSENSITIVE_ORDER));
        for (PackageInfo item : packages) {
            if (closed || Thread.currentThread().isInterrupted()) throw new java.io.InterruptedIOException();
            JSONObject row = new JSONObject();
            row.put("package", item.packageName);
            row.put("label", labels.get(item.packageName));
            row.put("version", item.versionName == null ? "" : item.versionName);
            row.put("system", (item.applicationInfo.flags & ApplicationInfo.FLAG_SYSTEM) != 0);
            row.put("splits", item.applicationInfo.splitSourceDirs == null ? 0 : item.applicationInfo.splitSourceDirs.length);
            try {
                ResolveInfo launcher = launcherIcons.get(item.packageName);
                String icon = null;
                if (launcher != null) {
                    try { icon = drawableDataUri(launcher.loadIcon(manager)); }
                    catch (Exception ignored) { /* Fall back to the package icon. */ }
                }
                row.put("icon", icon != null ? icon : drawableDataUri(manager.getApplicationIcon(item.applicationInfo)));
            } catch (Exception iconError) {
                row.put("icon", "");
            }
            result.put(row);
        }
        return result.toString();
    }

    static String drawableDataUri(Drawable drawable) throws IOException {
        // 72 px, 42 CSS px kartlarda keskin kalırken ikon kodlama yükünü ve
        // WebView köprü verisini 96 px'e göre belirgin biçimde azaltır.
        final int size = 72;
        if (drawable == null) throw new IOException("Uygulama ikonu bulunamadı.");
        drawable = drawable.mutate();
        Rect previousBounds = new Rect(drawable.getBounds());
        // Fixed dp insets must be laid out at the drawable's natural size.
        // Drawing an adaptive icon straight into 72px can collapse its foreground
        // at high density (e.g. two 18dp insets consume a 108px adaptive layer).
        final int logicalSize = Math.max(size,
                Math.max(drawable.getIntrinsicWidth(), drawable.getIntrinsicHeight()));
        Bitmap bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
        try (ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            drawable.setState(new int[] { android.R.attr.state_enabled });
            drawable.setVisible(true, false);
            drawable.jumpToCurrentState();
            drawable.setBounds(0, 0, logicalSize, logicalSize);
            Canvas canvas = new Canvas(bitmap);
            canvas.scale(size / (float) logicalSize, size / (float) logicalSize);
            drawable.draw(canvas);
            if (!bitmap.compress(Bitmap.CompressFormat.PNG, 90, output)) {
                throw new IOException("Uygulama ikonu dönüştürülemedi.");
            }
            return "data:image/png;base64," + Base64.encodeToString(output.toByteArray(), Base64.NO_WRAP);
        } finally {
            drawable.setBounds(previousBounds);
            bitmap.recycle();
        }
    }

    private static void copyFile(File source, File destination) throws IOException {
        try (FileChannel input = new FileInputStream(source).getChannel();
             FileChannel output = new FileOutputStream(destination).getChannel()) {
            long position = 0;
            long size = input.size();
            while (position < size) {
                long transferred = input.transferTo(position, Math.min(size - position, 32L * 1024L * 1024L), output);
                if (transferred <= 0) throw new IOException("Paket kopyalama işlemi tamamlanamadı.");
                position += transferred;
            }
        }
    }

    private static void addZipFile(ZipOutputStream output, File source, String name) throws IOException {
        output.putNextEntry(new ZipEntry(name));
        try (InputStream input = new FileInputStream(source)) {
            byte[] buffer = new byte[1024 * 1024];
            int count;
            while ((count = input.read(buffer)) >= 0) output.write(buffer, 0, count);
        }
        output.closeEntry();
    }

    private String uploadForAnalysis(File packageFile) throws Exception {
        if (!awaitEngineReady(30000)) {
            throw new IOException(EngineService.startupError.isEmpty()
                    ? "Yerel işlem motoruna bağlanılamadı. Uygulamayı kapatmadan yeniden dene."
                    : EngineService.startupError);
        }
        String boundary = "----APKCleanerNative" + Long.toHexString(System.nanoTime());
        byte[] prefix = ("--" + boundary + "\r\nContent-Disposition: form-data; name=\"package\"; filename=\""
                + packageFile.getName().replace("\"", "") + "\"\r\nContent-Type: application/octet-stream\r\n\r\n")
                .getBytes(java.nio.charset.StandardCharsets.UTF_8);
        byte[] suffix = ("\r\n--" + boundary + "--\r\n").getBytes(java.nio.charset.StandardCharsets.US_ASCII);
        HttpURLConnection connection = (HttpURLConnection) new URL(LOCAL_ORIGIN + "/api/analyze").openConnection(Proxy.NO_PROXY);
        connection.setRequestMethod("POST");
        connection.setDoOutput(true);
        connection.setConnectTimeout(10000);
        connection.setReadTimeout(300000);
        connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
        connection.setRequestProperty("Origin", LOCAL_ORIGIN);
        String cookies = CookieManager.getInstance().getCookie(LOCAL_ORIGIN);
        if (cookies != null) connection.setRequestProperty("Cookie", cookies);
        String client = cookieValue(cookies, CLIENT_COOKIE_NAME);
        if (!client.isEmpty()) connection.setRequestProperty("X-Client-ID", client);
        connection.setFixedLengthStreamingMode(prefix.length + packageFile.length() + suffix.length);
        try {
            try (OutputStream output = connection.getOutputStream(); InputStream input = new FileInputStream(packageFile)) {
                output.write(prefix);
                byte[] buffer = new byte[1024 * 1024];
                int count;
                while ((count = input.read(buffer)) >= 0) output.write(buffer, 0, count);
                output.write(suffix);
            }
            int status = connection.getResponseCode();
            InputStream response = status >= 200 && status < 300 ? connection.getInputStream() : connection.getErrorStream();
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            if (response != null) {
                try (InputStream input = response) {
                    byte[] buffer = new byte[64 * 1024]; int count;
                    while ((count = input.read(buffer)) >= 0) bytes.write(buffer, 0, count);
                }
            }
            String body = bytes.toString("UTF-8");
            if (status < 200 || status >= 300) throw new IOException(body.isEmpty() ? "Yerel motor HTTP " + status + " döndürdü." : body);
            return body;
        } finally {
            connection.disconnect();
        }
    }

    private void publishInstalledImport(String payload) {
        postToUi(() -> { if (webView != null) webView.evaluateJavascript(
                "globalThis.onInstalledPackageImported?.(" + JSONObject.quote(payload) + ")", null); });
    }

    private void publishInstalledPackages(String payload) {
        postToUi(() -> {
            if (webView != null) webView.evaluateJavascript(
                    "globalThis.onInstalledPackagesLoaded?.(" + JSONObject.quote(payload) + ")", null);
        });
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == UNINSTALL_FOR_REPLACE) {
            File apk = pendingNativeInstall;
            String packageName = pendingNativeInstallPackage;
            String action = pendingNativeInstallAction;
            executeIo(() -> {
                boolean removed = waitForPackageRemoval(packageName);
                if (removed && apk != null && apk.isFile()) launchInstaller(apk);
                else {
                    clearPendingNativeInstall();
                    publishNativeAction(action, jsonError(
                            "Mevcut uygulama kaldırılmadı. Sistem kaldırma ekranından işlemi onaylayıp yeniden dene."));
                }
            });
            return;
        }
        if (requestCode == UNKNOWN_SOURCE_PERMISSION) {
            File splitArchive = pendingOriginalSplitArchive;
            String splitSelection = pendingOriginalSplitSelection;
            if (splitArchive != null && splitSelection != null) {
                if (Build.VERSION.SDK_INT < 26 || getPackageManager().canRequestPackageInstalls()) {
                    executeIo(() -> commitOriginalSplitInstall(splitArchive, splitSelection));
                } else {
                    clearPendingOriginalSplitInstall();
                    publishNativeAction("split_install", jsonError("Bu kaynaktan uygulama yükleme izni verilmedi; kurulum durduruldu."));
                }
                return;
            }
            File apk = pendingNativeInstall;
            String action = pendingNativeInstallAction;
            if (Build.VERSION.SDK_INT < 26 || getPackageManager().canRequestPackageInstalls()) {
                if (apk != null && apk.isFile()) launchInstaller(apk);
                else {
                    clearPendingNativeInstall();
                    publishNativeAction(action, jsonError("Kuruluma hazırlanmış APK artık bulunamıyor."));
                }
            } else {
                clearPendingNativeInstall();
                publishNativeAction(action, jsonError("Bu kaynaktan uygulama yükleme izni verilmedi; kurulum durduruldu."));
            }
            return;
        }
        if (requestCode == PICK_FILE) {
            Uri[] result = resultCode == RESULT_OK && data != null && data.getData() != null
                    ? new Uri[] {data.getData()} : null;
            if (fileCallback != null) fileCallback.onReceiveValue(result);
            fileCallback = null;
            return;
        }
        if (requestCode == SAVE_DOWNLOAD && resultCode == RESULT_OK && data != null && data.getData() != null) {
            copyDownload(data.getData());
        } else if (requestCode == SAVE_DOWNLOAD) {
            clearPendingDownload();
        }
    }

    private void copyDownload(Uri destination) {
        String source = pendingDownloadUrl;
        String userAgent = pendingDownloadUserAgent;
        if (source == null || !isTrustedJobUri(Uri.parse(source))) {
            clearPendingDownload();
            Toast.makeText(this, R.string.save_failed, Toast.LENGTH_LONG).show();
            return;
        }
        executeIo(() -> {
            HttpURLConnection connection = null;
            try {
                connection = (HttpURLConnection) new URL(source).openConnection(Proxy.NO_PROXY);
                connection.setInstanceFollowRedirects(true);
                String cookies = CookieManager.getInstance().getCookie(source);
                if (cookies != null) connection.setRequestProperty("Cookie", cookies);
                String clientId = cookieValue(cookies, CLIENT_COOKIE_NAME);
                if (!clientId.isEmpty()) connection.setRequestProperty("X-Client-ID", clientId);
                if (userAgent != null && !userAgent.trim().isEmpty()) {
                    connection.setRequestProperty("User-Agent", userAgent);
                }
                connection.setRequestProperty("Accept", "application/vnd.android.package-archive,text/plain,*/*");
                connection.setConnectTimeout(10000);
                connection.setReadTimeout(300000);
                int status = connection.getResponseCode();
                if (status < 200 || status >= 300) {
                    throw new IOException("İndirme sunucusu HTTP " + status + " döndürdü.");
                }
                try (InputStream input = connection.getInputStream();
                     OutputStream output = getContentResolver().openOutputStream(destination, "w")) {
                    if (output == null) throw new IllegalStateException("Çıktı açılamadı.");
                    byte[] buffer = new byte[1024 * 1024];
                    int count;
                    while ((count = input.read(buffer)) >= 0) output.write(buffer, 0, count);
                    output.flush();
                }
                postToUi(() -> Toast.makeText(this, R.string.save_output, Toast.LENGTH_LONG).show());
            } catch (Exception error) {
                Log.e(TAG, "Çıktı kaydedilemedi: " + source, error);
                try { getContentResolver().delete(destination, null, null); }
                catch (RuntimeException ignored) {}
                postToUi(() -> Toast.makeText(this, R.string.save_failed, Toast.LENGTH_LONG).show());
            } finally {
                if (connection != null) connection.disconnect();
                clearPendingDownload();
            }
        });
    }

    private String cookieValue(String cookies, String name) {
        if (cookies == null || cookies.isEmpty()) return "";
        for (String row : cookies.split(";")) {
            String item = row.trim();
            int separator = item.indexOf('=');
            if (separator > 0 && name.equals(item.substring(0, separator).trim())) {
                return item.substring(separator + 1).trim();
            }
        }
        return "";
    }

    private void clearPendingDownload() {
        pendingDownloadUrl = null;
        pendingDownloadMime = null;
        pendingDownloadFilename = null;
        pendingDownloadUserAgent = null;
    }

    @Override protected void onSaveInstanceState(Bundle state) {
        super.onSaveInstanceState(state);
        state.putString(STATE_DOWNLOAD_URL, pendingDownloadUrl);
        state.putString(STATE_DOWNLOAD_MIME, pendingDownloadMime);
        state.putString(STATE_DOWNLOAD_NAME, pendingDownloadFilename);
        state.putString(STATE_DOWNLOAD_AGENT, pendingDownloadUserAgent);
        state.putString(STATE_INSTALL_PATH,
                pendingNativeInstall == null ? null : pendingNativeInstall.getAbsolutePath());
        state.putString(STATE_INSTALL_PACKAGE, pendingNativeInstallPackage);
        state.putString(STATE_INSTALL_TOKEN, pendingNativeInstallToken);
        state.putString(STATE_INSTALL_ACTION, pendingNativeInstallAction);
        state.putString(STATE_SPLIT_INSTALL_PATH,
                pendingOriginalSplitArchive == null ? null : pendingOriginalSplitArchive.getAbsolutePath());
        state.putString(STATE_SPLIT_INSTALL_SELECTION, pendingOriginalSplitSelection);
    }

    private void openExternal(Uri uri) {
        if (uri == null || uri.getScheme() == null) return;
        String scheme = uri.getScheme().toLowerCase(Locale.ROOT);
        if (!"https".equals(scheme) && !"http".equals(scheme)) return;
        try { startActivity(new Intent(Intent.ACTION_VIEW, uri)); }
        catch (ActivityNotFoundException | SecurityException ignored) {}
    }

    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[] {Manifest.permission.POST_NOTIFICATIONS}, NOTIFICATION_PERMISSION);
        }
    }

    @SuppressLint("GestureBackNavigation")
    @Override public void onBackPressed() {
        handleBack();
    }

    private void publishUiVisibility() {
        if (webView != null) webView.evaluateJavascript(
                "globalThis.setNativeVisibility?.(" + activityVisible + ")", null);
    }

    @Override protected void onResume() {
        super.onResume();
        activityVisible = true;
        ensureEngineService();
        if (webView != null) webView.onResume();
        publishUiVisibility();
    }

    @Override protected void onPause() {
        activityVisible = false;
        publishUiVisibility();
        // Pause rendering, not the Python service or a pending analyze/clean request.
        // pauseTimers() is deliberately avoided: it affects every WebView and can
        // stall callbacks needed by an in-flight import or system installer.
        if (webView != null) webView.onPause();
        super.onPause();
    }

    @Override public void onTrimMemory(int level) {
        super.onTrimMemory(level);
        if (!activityVisible && !installedPackagesLoading.get()
                && (level == TRIM_MEMORY_RUNNING_CRITICAL || level >= TRIM_MEMORY_BACKGROUND)) {
            // Rebuild only this disposable native icon cache on the next request.
            // User jobs, install state and the WebView's current form stay intact.
            installedPackagesReady = false;
            installedPackagesCache = "[]";
        }
    }

    @Override protected void onDestroy() {
        closed = true;
        if (activeInstance.get() == this) activeInstance = new WeakReference<>(null);
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        viewGeneration++;
        io.shutdownNow();
        cancelFileSelection();
        if (isFinishing()) {
            // Do not start a service while the Activity is being torn down.
            try { stopService(new Intent(this, EngineService.class)); }
            catch (RuntimeException error) { Log.w(TAG, "Motor servisi durdurulamadı", error); }
        }
        WebView previous = webView;
        webView = null;
        disposeWebView(previous);
        super.onDestroy();
    }
}
