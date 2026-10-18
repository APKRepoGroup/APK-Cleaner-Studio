package com.apkcleaner.studio;

import android.app.Activity;
import android.app.ActivityManager;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.PowerManager;
import android.provider.Settings;
import org.json.JSONObject;

/** Observe system policy; opening Settings never implies that the user changed it. */
final class BackgroundPolicy {
    private BackgroundPolicy() {}

    static String status(Activity activity) {
        try {
            PowerManager power = activity.getSystemService(PowerManager.class);
            ActivityManager tasks = activity.getSystemService(ActivityManager.class);
            if (power == null || tasks == null) return "{\"known\":false}";
            boolean restricted = Build.VERSION.SDK_INT >= 28 && tasks.isBackgroundRestricted();
            return new JSONObject().put("known", true)
                    .put("backgroundRestricted", restricted)
                    .put("ignoringOptimizations", power.isIgnoringBatteryOptimizations(activity.getPackageName()))
                    .toString();
        } catch (Exception error) {
            return "{\"known\":false}";
        }
    }

    static boolean openSettings(Activity activity, boolean appDetails) {
        Intent details = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                Uri.parse("package:" + activity.getPackageName()));
        try {
            activity.startActivity(appDetails ? details : new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS));
            return true;
        } catch (RuntimeException unavailable) {
            try { activity.startActivity(details); return true; }
            catch (RuntimeException ignored) { return false; }
        }
    }

    static boolean requestExemption(Activity activity) {
        PowerManager power = activity.getSystemService(PowerManager.class);
        // The Doze allowlist and OEM/user background restrictions are separate policies.
        if (power != null && power.isIgnoringBatteryOptimizations(activity.getPackageName())) {
            ActivityManager tasks = activity.getSystemService(ActivityManager.class);
            if (Build.VERSION.SDK_INT >= 28 && tasks != null && tasks.isBackgroundRestricted()) {
                return openSettings(activity, true);
            }
            return true;
        }
        try {
            activity.startActivity(new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                    Uri.parse("package:" + activity.getPackageName())));
            return true;
        } catch (RuntimeException unavailable) {
            return openSettings(activity, false);
        }
    }
}
