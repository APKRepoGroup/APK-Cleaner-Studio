package com.apkcleaner.studio;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

/** Bounded, device-local history of original split PackageInstaller sessions. */
final class InstallHistoryStore {
    private static final String PREFS = "original_split_install_history";
    private static final String KEY = "sessions";
    private static final int MAX_ENTRIES = 50;

    private InstallHistoryStore() {}

    static synchronized String list(Context context) {
        return entries(context).toString();
    }

    static synchronized void submitted(Context context, int sessionId, String packageName, int modules) {
        try {
            JSONArray previous = entries(context);
            JSONArray next = new JSONArray();
            next.put(new JSONObject().put("session", sessionId).put("package", packageName)
                    .put("modules", modules).put("status", "pending")
                    .put("message", "Android kurulum onayı bekleniyor.")
                    .put("timestamp", System.currentTimeMillis()));
            for (int i = 0; i < previous.length() && next.length() < MAX_ENTRIES; i++) {
                JSONObject row = previous.optJSONObject(i);
                if (row != null && row.optInt("session", -1) != sessionId) next.put(row);
            }
            save(context, next);
        } catch (Exception ignored) {}
    }

    static synchronized void completed(Context context, int sessionId, String status, String message) {
        if (sessionId < 0) return;
        try {
            JSONArray rows = entries(context);
            for (int i = 0; i < rows.length(); i++) {
                JSONObject row = rows.optJSONObject(i);
                if (row != null && row.optInt("session", -1) == sessionId) {
                    String detail = message == null ? "" : message.substring(0, Math.min(message.length(), 500));
                    row.put("status", status).put("message", detail)
                            .put("timestamp", System.currentTimeMillis());
                    save(context, rows);
                    return;
                }
            }
        } catch (Exception ignored) {}
    }

    private static JSONArray entries(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        try { return new JSONArray(prefs.getString(KEY, "[]")); }
        catch (Exception ignored) { return new JSONArray(); }
    }

    private static void save(Context context, JSONArray rows) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString(KEY, rows.toString()).commit();
    }
}
