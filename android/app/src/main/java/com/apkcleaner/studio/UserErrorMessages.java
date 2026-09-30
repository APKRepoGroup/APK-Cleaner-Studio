package com.apkcleaner.studio;

import java.util.Locale;
import java.util.regex.Pattern;

/** User-visible messages only; full exceptions remain in local technical diagnostics. */
final class UserErrorMessages {
    private UserErrorMessages() {}

    static String describe(Throwable error, String fallback) {
        String raw = error == null ? "" : error.getMessage();
        if (raw == null || raw.trim().isEmpty()) return fallback;
        String message = raw.split("\\r?\\n", 2)[0].trim();
        String lower = message.toLowerCase(Locale.ROOT);
        if (lower.contains("no space left") || lower.contains("not enough space"))
            return "İşlem için yeterli boş depolama alanı yok.";
        if (lower.contains("outofmemory") || lower.contains("out of memory"))
            return "İşlem için yeterli kullanılabilir bellek yok.";
        if (lower.contains("permission denied") || lower.contains("access denied"))
            return "İşlem için gereken dosyaya erişim izni yok.";
        if (lower.contains("no such file") || lower.contains("file not found"))
            return "İşlem için gereken dosya bulunamadı.";
        if (lower.contains("timeout") || lower.contains("timed out"))
            return "İşlem zaman aşımına uğradı. Bağlantıyı ve işlem durumunu kontrol et.";
        if (lower.contains("connection refused") || lower.contains("connection reset") || lower.contains("unable to resolve host"))
            return "Bağlantı kurulamadı. Ağ bağlantısını ve yerel işlem motorunu kontrol et.";
        if (Pattern.compile("(?:^|\\s)(?:error|exception|failed|unable|cannot|invalid|unsupported|unexpected)\\b|java\\.[\\w.]+", Pattern.CASE_INSENSITIVE).matcher(message).find()) {
            String prefix = message.split(":", 2)[0].trim();
            return Pattern.compile("[çğıöşüÇĞİÖŞÜ]").matcher(prefix).find() ? prefix + "." : fallback;
        }
        return Pattern.compile("[çğıöşüÇĞİÖŞÜ]").matcher(message).find() ? message : fallback;
    }
}
