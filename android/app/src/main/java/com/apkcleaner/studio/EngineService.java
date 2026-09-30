package com.apkcleaner.studio;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.util.Log;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.net.InetSocketAddress;
import java.net.Socket;

public final class EngineService extends Service {
    private static final String TAG = "APKCleanerEngine";
    public static final int PORT = 8765;
    public static final String ACTION_STOP = "com.apkcleaner.studio.STOP";
    public static volatile boolean ready = false;
    public static volatile String startupError = "";
    private static final String CHANNEL_ID = "apk_cleaner_engine";
    // Python is process-wide: an old Service's stop must finish before a new
    // Service starts it. A per-instance executor lets those operations race.
    // The one worker exits when idle; the queue remains reusable on recreation.
    private static final ExecutorService executor = new ThreadPoolExecutor(
            0, 1, 15, TimeUnit.SECONDS, new LinkedBlockingQueue<>());
    private final AtomicBoolean startScheduled = new AtomicBoolean(false);
    private volatile boolean stopping;

    @Override public void onCreate() {
        super.onCreate();
        ready = false;
        startupError = "";
        try {
            EmbeddedToolRunner.initialize(this);
            createNotificationChannel();
            startForeground(31, notification(getString(R.string.engine_starting)));
        } catch (Throwable error) {
            startupError = describe(error);
            DiagnosticRecorder.record(this, "engine-startup", error);
            Log.e(TAG, "Motor servisi başlatılamadı", error);
            stopSelf();
            return;
        }
        ensureEngineRunning();
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            stopEngine();
            stopSelf();
            return START_NOT_STICKY;
        }
        ensureEngineRunning();
        // Android bellek baskısı altında foreground servisini sonlandırırsa motoru
        // kullanıcı uygulamaya döndüğünde sıfırdan kurmadan yeniden oluşturabilsin.
        return START_STICKY;
    }

    private void ensureEngineRunning() {
        if (stopping) return;
        if (!startScheduled.compareAndSet(false, true)) return;
        executor.execute(() -> {
            try {
                if (stopping) return;
                if (isReachable(220)) {
                    ready = true;
                    startupError = "";
                } else {
                    ready = false;
                    startupError = "";
                    startPythonServer();
                }
            } finally {
                startScheduled.set(false);
            }
        });
    }

    public static boolean isReachable(int timeoutMs) {
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress("127.0.0.1", PORT), Math.max(80, timeoutMs));
            return true;
        } catch (Exception ignored) {
            return false;
        }
    }

    private void startPythonServer() {
        try {
            PyObject module = Python.getInstance().getModule("android_entry");
            boolean started = module.callAttr("start", getFilesDir().getAbsolutePath(), PORT).toBoolean();
            if (stopping) return;
            ready = started;
            startupError = started ? "" : getString(R.string.load_error);
            NotificationManager manager = getSystemService(NotificationManager.class);
            manager.notify(31, notification(started ? getString(R.string.engine_ready) : startupError));
        } catch (Throwable error) {
            ready = false;
            startupError = describe(error);
            DiagnosticRecorder.record(this, "engine-startup", error);
            Log.e(TAG, "Gömülü motor başlatılamadı", error);
        }
    }

    private static String describe(Throwable error) {
        return UserErrorMessages.describe(error, "Yerel işlem motoru başlatılamadı. Hata raporunu inceleyip yeniden dene.");
    }

    private Notification notification(String text) {
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent content = PendingIntent.getActivity(this, 1, open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Intent stop = new Intent(this, EngineService.class).setAction(ACTION_STOP);
        PendingIntent stopAction = PendingIntent.getService(this, 2, stop,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        return new Notification.Builder(this, CHANNEL_ID)
                .setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle(getString(R.string.app_name))
                .setContentText(text)
                .setContentIntent(content)
                .setOngoing(true)
                .addAction(new Notification.Action.Builder(null, getString(R.string.engine_stop), stopAction).build())
                .build();
    }

    private void createNotificationChannel() {
        NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID, getString(R.string.engine_channel_name), NotificationManager.IMPORTANCE_LOW);
        channel.setDescription(getString(R.string.engine_channel_description));
        getSystemService(NotificationManager.class).createNotificationChannel(channel);
    }

    private void stopEngine() {
        if (stopping) return;
        stopping = true;
        ready = false;
        EmbeddedToolRunner.requestCancel();
        // Serialize shutdown after a pending start, without blocking Android's main thread.
        executor.execute(() -> {
            try {
                if (Python.isStarted()) Python.getInstance().getModule("android_entry").callAttr("stop");
            } catch (Throwable error) {
                Log.w(TAG, "Motor kapatılamadı", error);
            }
        });
    }

    @Override public void onTaskRemoved(Intent rootIntent) {
        stopEngine();
        stopSelf();
        super.onTaskRemoved(rootIntent);
    }

    @Override public void onTimeout(int startId, int fgsType) {
        stopEngine();
        stopSelf(startId);
    }

    @Override public void onDestroy() {
        stopEngine();
        super.onDestroy();
    }

    @Override public IBinder onBind(Intent intent) { return null; }
}
