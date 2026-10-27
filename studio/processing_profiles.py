"""Validate small, explicit profile downloads; never export package-specific data."""
import json
import re

FORMAT = "apk-cleaner-processing-profiles"
MAX_BYTES = 16384
FLAGS = {"patchAds", "stripDebug", "restrictStoreUpdates", "normalizeDex", "optimizeApk", "deobfuscateResources"}


def export_profile_document(text: str) -> bytes:
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Profil dosyası en fazla 16 KB olmalı.")
    try:
        document = json.loads(text)
    except (ValueError, RecursionError) as error:
        raise ValueError("Profil dosyası geçerli bir JSON dosyası değil.") from error
    if (not isinstance(document, dict) or set(document) != {"format", "version", "profiles"}
            or document["format"] != FORMAT or type(document["version"]) is not int or document["version"] != 1
            or not isinstance(document["profiles"], list) or not 1 <= len(document["profiles"]) <= 12):
        raise ValueError("Bu dosya desteklenen bir işlem profili dosyası değil.")
    names = set()
    for profile in document["profiles"]:
        if not isinstance(profile, dict) or set(profile) != {"name", "options"}:
            raise ValueError("Profil kaydı geçersiz.")
        name, options = profile["name"], profile["options"]
        if not isinstance(name, str) or re.search(r"[\x00-\x1f\x7f\u202a-\u202e\u2066-\u2069]", name):
            raise ValueError("Profil adı geçersiz.")
        name = " ".join(name.split())
        key = name.translate(str.maketrans({"I": "ı", "İ": "i"})).lower()
        if not name or len(name.encode("utf-16-le")) // 2 > 40 or key in names:
            raise ValueError("Profil adları benzersiz ve 1–40 karakter olmalı.")
        names.add(key)
        profile["name"] = name
        if (not isinstance(options, dict) or set(options) - FLAGS - {"operation", "profile"}
                or options.get("operation") not in ("patch", "clone", "convert")
                or options.get("profile") not in ("safe", "balanced", "deep")
                or any(type(value) is not bool for field, value in options.items() if field in FLAGS)):
            raise ValueError("Profil işlem seçenekleri geçersiz.")
        profile["options"] = {"operation": options["operation"], "profile": options["profile"], **{key: options.get(key, False) for key in sorted(FLAGS)}}
    payload = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(payload) > MAX_BYTES:
        raise ValueError("Profil dosyası en fazla 16 KB olmalı.")
    return payload
