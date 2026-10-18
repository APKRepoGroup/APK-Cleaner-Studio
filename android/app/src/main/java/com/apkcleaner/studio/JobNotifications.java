package com.apkcleaner.studio;

import android.Manifest;
import android.app.KeyguardManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.PowerManager;
import android.util.Log;

import java.util.LinkedHashSet;

/** Worker-driven results: independent of WebView timers, with no Activity reference. */
public final class JobNotifications {
    public static final String ACTION_RESULT = "com.apkcleaner.studio.JOB_RESULT";
    public static final String EXTRA_JOB = "job_id";
    private static final String CHANNEL = "apk_cleaner_job_results";
    private static final LinkedHashSet<String> delivered = new LinkedHashSet<>();
    private static volatile Context application;
    private static volatile boolean uiVisible;

    private JobNotifications() {}

    public static void initialize(Context context) { application = context.getApplicationContext(); }
    public static void setUiVisible(boolean visible) { uiVisible = visible; }

    public static synchronized void publish(String jobId, String status, String filename, String eventId) {
        Context context = application;
        if (context == null || jobId == null || !jobId.matches("[a-f0-9]{32}")
                || !("done".equals(status) || "error".equals(status))
                || eventId == null || !eventId.matches("[a-f0-9]{32}") || delivered.contains(eventId)) return;
        delivered.add(eventId);
        if (delivered.size() > 64) delivered.remove(delivered.iterator().next());
        try {
            PowerManager power = context.getSystemService(PowerManager.class);
            KeyguardManager keyguard = context.getSystemService(KeyguardManager.class);
            // A resumed Activity under the lock screen must still receive a result.
            if (uiVisible && power != null && power.isInteractive()
                    && keyguard != null && !keyguard.isKeyguardLocked()) return;
            if (Build.VERSION.SDK_INT >= 33 && context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                    != PackageManager.PERMISSION_GRANTED) return;
            NotificationManager manager = context.getSystemService(NotificationManager.class);
            if (manager == null || !manager.areNotificationsEnabled()) return;
            NotificationChannel channel = new NotificationChannel(CHANNEL,
                    context.getString(R.string.job_channel_name), NotificationManager.IMPORTANCE_DEFAULT);
            channel.setDescription(context.getString(R.string.job_channel_description));
            manager.createNotificationChannel(channel);
            Intent open = new Intent(context, MainActivity.class).setAction(ACTION_RESULT)
                    .setData(Uri.parse("apkcleaner://job/" + jobId)).putExtra(EXTRA_JOB, jobId)
                    .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            PendingIntent tap = PendingIntent.getActivity(context, 3, open,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            String title = context.getString("done".equals(status) ? R.string.job_done : R.string.job_failed);
            String name = filename == null ? "" : filename.replaceAll("[\\p{Cntrl}\\p{Cf}]", " ").trim();
            if (name.length() > 120) name = name.substring(0, 120);
            String text = context.getString("done".equals(status) ? R.string.job_done_text : R.string.job_failed_text);
            Notification publicVersion = new Notification.Builder(context, CHANNEL)
                    .setSmallIcon(R.mipmap.ic_launcher).setContentTitle(context.getString(R.string.app_name))
                    .setContentText(context.getString(R.string.job_result_private)).build();
            Notification result = new Notification.Builder(context, CHANNEL)
                    .setSmallIcon(R.mipmap.ic_launcher).setContentTitle(title)
                    .setContentText(name.isEmpty() ? text : name + " · " + text)
                    .setContentIntent(tap).setAutoCancel(true).setOnlyAlertOnce(true)
                    .setCategory(Notification.CATEGORY_STATUS).setVisibility(Notification.VISIBILITY_PRIVATE)
                    .setPublicVersion(publicVersion).build();
            // Job-specific tag prevents result intents from replacing one another or engine #31.
            manager.notify("job:" + jobId, 32, result);
        } catch (RuntimeException error) {
            Log.w("APKCleanerResults", "İşlem sonucu bildirimi gösterilemedi", error);
        }
    }
}
