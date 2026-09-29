package com.apkcleaner.studio;

import android.content.Context;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;

/** App-owned crash breadcrumbs; never records logcat, user APKs or exception messages. */
final class DiagnosticRecorder {
    private static final String FILE_NAME = "diagnostic-native.txt";
    private static boolean installed;

    private DiagnosticRecorder() {}

    static synchronized void install(Context context) {
        if (installed) return;
        installed = true;
        Context app = context.getApplicationContext();
        Thread.UncaughtExceptionHandler previous = Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler((thread, error) -> {
            record(app, "uncaught", error);
            if (previous != null) previous.uncaughtException(thread, error);
        });
    }

    static synchronized void record(Context context, String event, Throwable error) {
        try {
            StringBuilder text = new StringBuilder();
            text.append("Olay: ").append(event.replaceAll("[^a-z-]", "")).append('\n');
            text.append("Zaman (epoch ms): ").append(System.currentTimeMillis()).append('\n');
            if (error != null) {
                text.append("Tür: ").append(error.getClass().getSimpleName()).append('\n');
                StackTraceElement[] frames = error.getStackTrace();
                for (int i = 0; i < Math.min(frames.length, 12); i++) {
                    StackTraceElement frame = frames[i];
                    text.append("  ").append(frame.getClassName().replaceAll("[^A-Za-z0-9_.$]", ""))
                            .append('.').append(frame.getMethodName().replaceAll("[^A-Za-z0-9_$]", ""))
                            .append(':').append(frame.getLineNumber()).append('\n');
                }
            }
            File target = new File(context.getFilesDir(), FILE_NAME);
            try (FileOutputStream output = new FileOutputStream(target, false)) {
                output.write(text.toString().getBytes(StandardCharsets.UTF_8));
            }
        } catch (Throwable ignored) {
            // Diagnostics must not turn a recoverable UI failure into a crash.
        }
    }
}
