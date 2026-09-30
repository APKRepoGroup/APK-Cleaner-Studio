from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
BUNDLED_TOOLS = ROOT / "tools"
PROFILES_PATH = ROOT / "profiles.json"
SUPPORTED_PACKAGES = {".apk", ".apks", ".apkm", ".xapk"}
SPLIT_PACKAGES = {".apks", ".apkm", ".xapk"}
ANDROID_NS = "http://schemas.android.com/apk/res/android"
ENGINE_VERSION = "2.0"
TOOL_TIMEOUT_SECONDS = 15 * 60
MAX_ARCHIVE_ENTRIES = 100_000
MAX_ARCHIVE_EXPANDED_BYTES = 3 * 1024 * 1024 * 1024
MAX_ARCHIVE_ENTRY_BYTES = 1536 * 1024 * 1024
MAX_ARCHIVE_COMPRESSION_RATIO = 500
MAX_DEX_BYTES = 512 * 1024 * 1024
ABI_DENSITY_DEFAULTS = {
    "armeabi-v7a": "xhdpi",
    "arm64-v8a": "xxhdpi",
    "x86": "xhdpi",
    "x86_64": "xxhdpi",
}
KNOWN_ABIS = tuple(ABI_DENSITY_DEFAULTS)
KNOWN_DENSITIES = ("ldpi", "mdpi", "tvdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi")
SUPPORTED_SPLIT_LANGUAGES = {"en": "İngilizce", "tr": "Türkçe"}
PACKAGE_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
ET.register_namespace("android", ANDROID_NS)


def _data_root() -> Path:
    explicit = os.environ.get("APK_CLEANER_DATA_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve()
    if not getattr(sys, "frozen", False):
        return ROOT
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return base / "APKCleanerStudio"


DATA_ROOT = _data_root()
TOOLS = DATA_ROOT / "tools"
RUNTIME = DATA_ROOT / "runtime"


def _temporary_directory(prefix: str) -> tempfile.TemporaryDirectory:
    """Return a temp directory, repairing Android's private temp root first."""
    directory: str | None = None
    if os.environ.get("APK_CLEANER_ANDROID") == "1":
        root = Path(os.environ.get("APK_CLEANER_TEMP_ROOT", RUNTIME / "tmp"))
        root.mkdir(parents=True, exist_ok=True)
        probe = root / f".write-test-{os.getpid()}-{threading.get_ident()}-{time.time_ns()}"
        try:
            with probe.open("xb") as handle:
                handle.write(b"ok")
        finally:
            probe.unlink(missing_ok=True)
        directory = str(root)
        for name in ("TMPDIR", "TEMP", "TMP"):
            os.environ[name] = directory
        tempfile.tempdir = directory
    return tempfile.TemporaryDirectory(prefix=prefix, dir=directory)

INSTALL_SOURCE_MARKERS = {
    "Play Integrity API": (b"com/google/android/play/core/integrity", b"IntegrityManager"),
    "Paket yükleme kaynağı denetimi": (b"getInstallerPackageName", b"getInstallSourceInfo"),
    "Play Store paket doğrulaması": (b"com.android.vending", b"com/android/vending"),
    "Lisans / dağıtım doğrulaması": (b"initializeLicenseCheck",),
}

SOURCE_INTEGRITY_RISK_LABELS = {
    "Play Integrity API",
    "Paket yükleme kaynağı denetimi",
    "Lisans / dağıtım doğrulaması",
}

# Bunlar yalnızca kullanıcı arayüzü mesajı adaylarını sınıflandırır. Bir APK'nın
# özgün sürümüyle karşılaştırma yapılmadan mesajın sonradan eklendiği güvenilir
# biçimde söylenemeyeceğinden analiz aşamasında otomatik silme uygulanmaz.
MESSAGE_UI_MARKERS = {
    "Toast mesajı": (b"Landroid/widget/Toast;", b"makeText"),
    "Snackbar mesajı": (
        b"Lcom/google/android/material/snackbar/Snackbar;",
        b"Landroid/support/design/widget/Snackbar;",
    ),
    "Diyalog penceresi": (
        b"Landroid/app/AlertDialog$Builder;",
        b"Landroidx/appcompat/app/AlertDialog$Builder;",
        b"Lcom/google/android/material/dialog/MaterialAlertDialogBuilder;",
    ),
}

# Google Play bu kayıtları split dağıtımı için kullanır. Kayıtlar yeniden
# paketlenmiş/universal APK'larda da kalabildiği için tek başına, dosyanın kesin
# olarak kurulamayacağını kanıtlamaz. Analizde kurulum riski olarak gösterilir;
# işlem motorunu engellemek için kullanılmaz.
SPLIT_REQUIRED_MARKERS = (
    "com.android.vending.splits.required",
    "requiredSplitTypes",
)
_ACTIVE_TOOLS: set[subprocess.Popen] = set()
_ACTIVE_TOOL_THREADS: dict[subprocess.Popen, int] = {}
_ACTIVE_TOOLS_LOCK = threading.Lock()


@lru_cache(maxsize=1)
def load_profiles() -> dict[str, dict]:
    """Load immutable bundled detection profiles once per process."""
    return json.loads(PROFILES_PATH.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_package_archive(path: Path) -> None:
    """Reject archive ambiguity and decompression bombs before third-party tools see input."""
    if not zipfile.is_zipfile(path):
        raise ValueError("Dosya geçerli bir APK/ZIP paketi değil.")
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_ARCHIVE_ENTRIES:
            raise ValueError("Paket güvenli arşiv kayıt sınırını aşıyor.")
        expanded = 0
        compressed = 0
        seen: set[str] = set()
        for info in entries:
            normalized = info.filename.replace("\\", "/")
            parts = [part for part in normalized.split("/") if part not in {"", "."}]
            if (
                "\x00" in normalized
                or normalized.startswith("/")
                or re.match(r"^[A-Za-z]:", normalized)
                or ".." in parts
            ):
                raise ValueError("Paket güvenli olmayan bir arşiv yolu içeriyor.")
            key = "/".join(parts)
            if key and key in seen:
                raise ValueError("Paket aynı arşiv yolunu birden fazla kez içeriyor.")
            if key:
                seen.add(key)
            if info.flag_bits & 0x1:
                raise ValueError("Şifreli arşiv girdileri desteklenmiyor.")
            if ((info.external_attr >> 16) & 0xF000) == 0xA000:
                raise ValueError("Sembolik bağlantı içeren paketler desteklenmiyor.")
            if info.file_size > MAX_ARCHIVE_ENTRY_BYTES:
                raise ValueError("Paket tek dosya güvenlik sınırını aşıyor.")
            expanded += info.file_size
            compressed += max(0, info.compress_size)
            if expanded > MAX_ARCHIVE_EXPANDED_BYTES:
                raise ValueError("Paket açıldığında güvenli boyut sınırını aşıyor.")
        if compressed > 0 and expanded > compressed * MAX_ARCHIVE_COMPRESSION_RATIO:
            raise ValueError("Paket olağandışı sıkıştırma oranı nedeniyle reddedildi.")


def _entry_fingerprint(archive: zipfile.ZipFile, name: str) -> dict:
    info = archive.getinfo(name)
    digest = hashlib.sha256()
    with archive.open(info) as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"size": info.file_size, "sha256": digest.hexdigest()}


def validate_clone_package_name(original: str, candidate: str) -> str:
    if not PACKAGE_NAME_PATTERN.fullmatch(original):
        raise ValueError("Özgün paket adı okunamadı; klonlamadan önce paketi yeniden analiz et.")
    name = candidate.strip()
    if len(name) > 200 or not PACKAGE_NAME_PATTERN.fullmatch(name):
        raise ValueError("Klon paket adı en az iki geçerli bölüm içermeli; yalnızca harf, rakam, alt çizgi ve nokta kullanılabilir.")
    if name == original:
        raise ValueError("Klonun paket adı özgün uygulamanın paket adından farklı olmalı.")
    return name


def suggest_clone_package_name(original: str) -> str:
    suggestion = original + ".clone"
    return suggestion if len(suggestion) <= 200 else original[:-1] + "2"


def inspect_manifest_package(manifest_bytes: bytes, tools: Toolchain) -> str:
    if not tools.java or not tools.binary_manifest_patcher or not tools.apkeditor:
        return ""
    with _temporary_directory(prefix="apkcleaner-package-") as temp_name:
        manifest = Path(temp_name) / "AndroidManifest.xml"
        manifest.write_bytes(manifest_bytes)
        log: list[str] = []
        try:
            run_checked([
                tools.java, "-cp", os.pathsep.join((str(tools.apkeditor), str(tools.binary_manifest_patcher))),
                "local.apkcleaner.xml.BinaryManifestPatcher", "--input", str(manifest), "--inspect-package",
            ], log)
        except (OSError, RuntimeError):
            # Old, not-yet-rebuilt tool bundles may lack the inspection switch.
            return ""
        package = next((line.split("\t", 1)[1] for line in log if line.startswith("PACKAGE\t")), "")
        return package if PACKAGE_NAME_PATTERN.fullmatch(package) else ""


def _android_archive_package(apk_path: Path) -> str:
    if os.environ.get("APK_CLEANER_ANDROID") != "1":
        return ""
    try:
        from java import jclass
        package = str(jclass("com.apkcleaner.studio.EmbeddedToolRunner").inspectArchivePackage(str(apk_path)) or "")
        return package if PACKAGE_NAME_PATTERN.fullmatch(package) else ""
    except Exception:
        return ""


def verify_output_apk(
    source: Path,
    output: Path,
    tools: Toolchain,
    log: list[str],
    *,
    removed_files: set[str] | None = None,
    expected_package_name: str | None = None,
) -> dict:
    """Fail closed before a generated APK is offered for download/install."""
    validate_package_archive(output)
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(output) as produced:
        source_names = set(original.namelist())
        output_names = set(produced.namelist())
        if "AndroidManifest.xml" not in source_names:
            raise RuntimeError("Kaynak APK'da AndroidManifest.xml bulunamadı.")
        required = {"AndroidManifest.xml"} | {
            name for name in source_names if re.fullmatch(r"classes(?:\d+)?\.dex", name)
        }
        planned_removals = removed_files or set()
        # Deep cleaning deliberately removes matched ad SDK libraries. Only those
        # exact planned entries are exempt; unexpected native losses still fail.
        required_libraries = {
            name for name in source_names if name.startswith("lib/") and name.endswith(".so")
        } - planned_removals
        if len(required) == 1 or required - output_names:
            raise RuntimeError("Çıktı doğrulanamadı: manifest veya beklenen DEX bileşeni eksik.")
        if required_libraries - output_names:
            raise RuntimeError("Çıktı doğrulanamadı: seçilen paketin native kütüphanesi eksik.")
        if any(name in output_names for name in planned_removals):
            raise RuntimeError("Çıktı doğrulanamadı: kaldırılması istenen dosya pakette kaldı.")
        for name in required:
            if produced.getinfo(name).file_size == 0:
                raise RuntimeError(f"Çıktı doğrulanamadı: {name} boş.")
        corrupt = produced.testzip()
        if corrupt is not None:
            raise RuntimeError(f"Çıktı doğrulanamadı: ZIP bütünlük hatası ({corrupt}).")
        if expected_package_name:
            actual_package_name = inspect_manifest_package(produced.read("AndroidManifest.xml"), tools)
            if actual_package_name != expected_package_name:
                raise RuntimeError("Çıktı doğrulanamadı: klon paket adı manifestte korunmadı.")

    if os.environ.get("APK_CLEANER_ANDROID") == "1":
        try:
            from java import jclass
            jclass("com.apkcleaner.studio.EmbeddedToolRunner").verifyApk(str(output))
        except Exception as exc:
            raise RuntimeError(f"Çıktı imzası doğrulanamadı: {exc}") from exc
        signature_tool = "Android apksig"
    elif tools.apksigner:
        run_checked([tools.apksigner, "verify", "--verbose", str(output)], log)
        signature_tool = "apksigner"
    elif tools.java and tools.uber_signer:
        run_checked([tools.java, "-jar", str(tools.uber_signer), "--apks", str(output), "--onlyVerify", "--skipZipAlign"], log)
        signature_tool = "uber-apk-signer"
    else:
        raise RuntimeError("Çıktı imzası için bağımsız doğrulayıcı bulunamadı.")
    return {
        "passed": True,
        "archive_crc": "ok",
        "manifest": "ok",
        "dex_count": len(required) - 1,
        "native_library_count": len(required_libraries),
        "removed_files": "ok",
        "signature": "ok",
        "signature_tool": signature_tool,
        "package_name": expected_package_name,
    }


def _which_any(names: Iterable[str]) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def _latest_build_tool(name: str) -> str | None:
    roots = [
        os.environ.get("ANDROID_HOME"),
        os.environ.get("ANDROID_SDK_ROOT"),
        str(Path.home() / "AppData/Local/Android/Sdk") if os.name == "nt" else None,
    ]
    candidates: list[Path] = []
    for root in filter(None, roots):
        base = Path(root) / "build-tools"
        if base.is_dir():
            candidates.extend(base.glob(f"*/{name}*"))
    return str(sorted(candidates, reverse=True)[0]) if candidates else None


def _local_binary(names: Iterable[str]) -> str | None:
    for name in names:
        candidates = sorted(RUNTIME.rglob(name)) if RUNTIME.is_dir() else []
        if candidates:
            return str(candidates[0])
    return None


def _available_jar(name: str) -> Path | None:
    for base in (TOOLS, BUNDLED_TOOLS):
        candidate = base / name
        if candidate.is_file():
            return candidate
    return None


def _bundled_zipalign() -> str | None:
    if os.name != "nt":
        return None
    candidate = BUNDLED_TOOLS / "zipalign-win.exe"
    return str(candidate) if candidate.is_file() else None


@dataclass
class Toolchain:
    java: str | None
    keytool: str | None
    dexlib2: Path | None
    direct_patcher: Path | None
    binary_manifest_patcher: Path | None
    apkeditor: Path | None
    uber_signer: Path | None
    zipalign: str | None
    apksigner: str | None

    @classmethod
    def detect(cls) -> "Toolchain":
        if os.environ.get("APK_CLEANER_ANDROID") == "1":
            # Android sürümünde araçlar ayrı çalıştırılabilir dosyalar değildir.
            # DEX, AXML, APKEditor ve imzalama sınıfları uygulamanın DEX'i içinde
            # çalışır. Bu işaretçiler mevcut motorun yetenek denetimini tek bir
            # kod yolunda tutar; kullanıcıdan Java/Termux kurulumu istenmez.
            return cls(
                java="embedded-android-runtime",
                keytool=None,
                dexlib2=BUNDLED_TOOLS / "dexlib2-runtime.jar",
                direct_patcher=BUNDLED_TOOLS / "direct-dex-patcher.jar",
                binary_manifest_patcher=BUNDLED_TOOLS / "binary-xml-patcher.jar",
                apkeditor=BUNDLED_TOOLS / "APKEditor.jar",
                uber_signer=None,
                zipalign="embedded-apksig-alignment",
                apksigner="embedded-apksig",
            )
        java_name = "java.exe" if os.name == "nt" else "java"
        keytool_name = "keytool.exe" if os.name == "nt" else "keytool"
        return cls(
            java=_which_any(["java"]) or _local_binary([java_name]),
            keytool=_which_any(["keytool"]) or _local_binary([keytool_name]),
            dexlib2=_available_jar("dexlib2-runtime.jar"),
            direct_patcher=_available_jar("direct-dex-patcher.jar"),
            binary_manifest_patcher=_available_jar("binary-xml-patcher.jar"),
            apkeditor=_available_jar("APKEditor.jar"),
            uber_signer=_available_jar("uber-apk-signer.jar"),
            zipalign=_which_any(["zipalign"]) or _latest_build_tool("zipalign") or _bundled_zipalign(),
            apksigner=_which_any(["apksigner", "apksigner.bat"]) or _latest_build_tool("apksigner"),
        )

    def status(self) -> dict:
        dex = bool(self.java and self.dexlib2 and self.direct_patcher)
        package = bool(self.java and self.apkeditor)
        manifest = bool(package and self.binary_manifest_patcher)
        signer = bool(self.apksigner or (self.java and self.uber_signer))
        return {
            "java": bool(self.java),
            "dex_tools": dex,
            "manifest_tool": manifest,
            "split_tool": package,
            "resource_tool": package,
            "zipalign": bool(self.zipalign),
            "signer": signer,
            "scan_ready": True,
            "clean_ready": dex,
            "fully_ready": bool(dex and package and manifest and signer),
        }


def inspect_apk(apk_path: Path, known_sha256: str | None = None) -> dict:
    profiles = load_profiles()
    validate_package_archive(apk_path)

    detections: dict[str, dict] = {}
    dex_rows: list[dict] = []
    suspicious_files: list[str] = []
    manifest_hits: dict[str, int] = {}
    layout_hits: list[dict] = []
    install_source_checks: set[str] = set()
    message_ui_candidates: dict[str, dict] = {}
    requires_splits = False

    package_name = ""
    tools = Toolchain.detect()
    with zipfile.ZipFile(apk_path) as archive:
        names = archive.namelist()
        dex_names = sorted(name for name in names if re.fullmatch(r"classes\d*\.dex", Path(name).name))
        if not dex_names:
            raise ValueError("APK içinde classes*.dex bulunamadı.")

        for dex_name in dex_names:
            if archive.getinfo(dex_name).file_size > MAX_DEX_BYTES:
                raise ValueError(f"{Path(dex_name).name} güvenli DEX boyut sınırını aşıyor.")
            payload = archive.read(dex_name)
            for label, markers in INSTALL_SOURCE_MARKERS.items():
                if any(marker in payload for marker in markers):
                    install_source_checks.add(label)
            for label, markers in MESSAGE_UI_MARKERS.items():
                references = sum(payload.count(marker) for marker in markers)
                if references:
                    entry = message_ui_candidates.setdefault(
                        label, {"label": label, "references": 0, "dex": []}
                    )
                    entry["references"] += references
                    entry["dex"].append(dex_name)
            matched: list[str] = []
            for profile_id, profile in profiles.items():
                count = sum(payload.count(marker.encode()) for marker in profile["descriptors"])
                if count:
                    matched.append(profile_id)
                    entry = detections.setdefault(
                        profile_id,
                        {"id": profile_id, "label": profile["label"], "references": 0, "dex": []},
                    )
                    entry["references"] += count
                    entry["dex"].append(dex_name)
            dex_rows.append({"name": dex_name, "size": len(payload), "networks": matched})

        for name in names:
            lowered = name.lower()
            for profile in profiles.values():
                markers = profile.get("assets", []) + profile.get("libraries", [])
                if any(marker.lower() in lowered for marker in markers):
                    suspicious_files.append(name)
                    break

            if lowered.startswith("res/layout") and lowered.endswith(".xml"):
                payload = archive.read(name)
                matched_layout: list[str] = []
                for profile_id, profile in profiles.items():
                    prefixes = [value.rstrip(".") for value in profile.get("manifest", [])]
                    if any(
                        marker.encode("utf-8") in payload or marker.encode("utf-16le") in payload
                        for marker in prefixes
                    ):
                        matched_layout.append(profile_id)
                if matched_layout:
                    layout_hits.append({"name": name, "networks": matched_layout})

        if "AndroidManifest.xml" in names:
            manifest = archive.read("AndroidManifest.xml")
            package_name = inspect_manifest_package(manifest, tools)
            if not package_name:
                package_name = _android_archive_package(apk_path)
            requires_splits = any(
                marker.encode("utf-8") in manifest or marker.encode("utf-16le") in manifest
                for marker in SPLIT_REQUIRED_MARKERS
            )
            for profile_id, profile in profiles.items():
                markers = profile.get("manifest", []) + profile.get("metadata", [])
                hits = sum(
                    manifest.count(marker.encode("utf-8")) + manifest.count(marker.encode("utf-16le"))
                    for marker in markers
                )
                if hits:
                    manifest_hits[profile_id] = hits

    source_integrity_risk = bool(SOURCE_INTEGRITY_RISK_LABELS.intersection(install_source_checks))
    return {
        "filename": apk_path.name,
        "size": apk_path.stat().st_size,
        "sha256": known_sha256 or sha256(apk_path),
        "package_name": package_name,
        "suggested_clone_package_name": suggest_clone_package_name(package_name) if package_name else "",
        "dex": dex_rows,
        "dex_count": len(dex_rows),
        "detections": sorted(detections.values(), key=lambda item: item["references"], reverse=True),
        "network_count": len(detections),
        "manifest_hits": manifest_hits,
        "layout_hits": layout_hits[:250],
        "install_source_checks": sorted(install_source_checks),
        "source_integrity_risk": source_integrity_risk,
        "message_ui_candidates": sorted(
            message_ui_candidates.values(), key=lambda item: item["references"], reverse=True
        ),
        "message_ui_candidate_count": sum(item["references"] for item in message_ui_candidates.values()),
        "requires_splits": requires_splits,
        "suspicious_files": sorted(set(suspicious_files))[:500],
        "toolchain": tools.status(),
        "warnings": [
            "Otomatik tespit yüzde yüz kapsama garantisi vermez; özel ve gizlenmiş reklam yöneticileri ayrıca raporlanabilir.",
            "Yeniden imzalanan APK, mağaza sürümünün üzerine doğrudan kurulamayabilir.",
        ],
    }


def inspect_split_package(
    source: Path,
    inventory: dict | None = None,
    progress: Callable[[str, int], None] | None = None,
    known_sha256: str | None = None,
) -> dict:
    """Inspect base/feature APKs directly, avoiding an early universal-APK merge."""
    validate_package_archive(source)
    inventory = inventory or inspect_split_components(source)
    candidates = [
        item["name"] for item in inventory.get("modules", [])
        if item.get("kind") in {"base", "feature"}
    ]
    if not candidates:
        candidates = [item["name"] for item in inventory.get("modules", [])[:1]]
    if not candidates:
        raise ValueError("Split paket içinde incelenebilir APK modülü bulunamadı.")

    detections: dict[str, dict] = {}
    dex_rows: list[dict] = []
    manifest_hits: dict[str, int] = {}
    layout_hits: list[dict] = []
    install_source_checks: set[str] = set()
    message_ui_candidates: dict[str, dict] = {}
    suspicious_files: set[str] = set()
    warnings: list[str] = []
    package_name = ""
    notify = progress or (lambda _message, _percent: None)

    with _temporary_directory(prefix="apkcleaner-split-scan-") as temp_name:
        temp = Path(temp_name)
        with zipfile.ZipFile(source) as outer:
            outer_names = set(outer.namelist())
            valid_candidates = [name for name in candidates if name in outer_names]
            for index, name in enumerate(valid_candidates, 1):
                notify(
                    f"Split modülü taranıyor ({index}/{len(valid_candidates)})",
                    12 + int(70 * index / max(1, len(valid_candidates))),
                )
                extracted = temp / f"{index:03d}-{Path(name).name}"
                with outer.open(name) as source_stream, extracted.open("wb") as target_stream:
                    shutil.copyfileobj(source_stream, target_stream, length=1024 * 1024)
                if not zipfile.is_zipfile(extracted):
                    continue
                report = inspect_apk(extracted)
                candidate_package = str(report.get("package_name") or "")
                is_base = any(item.get("name") == name and item.get("kind") == "base" for item in inventory.get("modules", []))
                if candidate_package and (not package_name or is_base):
                    package_name = candidate_package
                module_label = Path(name).name
                for row in report["dex"]:
                    dex_rows.append({**row, "name": f"{module_label}:{row['name']}"})
                for item in report["detections"]:
                    entry = detections.setdefault(
                        item["id"],
                        {"id": item["id"], "label": item["label"], "references": 0, "dex": []},
                    )
                    entry["references"] += item["references"]
                    entry["dex"].extend(f"{module_label}:{value}" for value in item["dex"])
                for profile_id, count in report["manifest_hits"].items():
                    manifest_hits[profile_id] = manifest_hits.get(profile_id, 0) + count
                layout_hits.extend(
                    {**item, "name": f"{module_label}:{item['name']}"}
                    for item in report["layout_hits"]
                )
                install_source_checks.update(report["install_source_checks"])
                for item in report.get("message_ui_candidates", []):
                    entry = message_ui_candidates.setdefault(
                        item["label"], {"label": item["label"], "references": 0, "dex": []}
                    )
                    entry["references"] += item["references"]
                    entry["dex"].extend(f"{module_label}:{value}" for value in item["dex"])
                suspicious_files.update(f"{module_label}:{value}" for value in report["suspicious_files"])
                warnings.extend(value for value in report["warnings"] if value not in warnings)

    if not dex_rows:
        raise ValueError("Split paket içinde classes*.dex içeren geçerli bir APK bulunamadı.")
    source_integrity_risk = bool(SOURCE_INTEGRITY_RISK_LABELS.intersection(install_source_checks))
    return {
        "filename": source.name,
        "size": source.stat().st_size,
        "sha256": known_sha256 or sha256(source),
        "package_name": package_name,
        "suggested_clone_package_name": suggest_clone_package_name(package_name) if package_name else "",
        "dex": dex_rows,
        "dex_count": len(dex_rows),
        "detections": sorted(detections.values(), key=lambda item: item["references"], reverse=True),
        "network_count": len(detections),
        "manifest_hits": manifest_hits,
        "layout_hits": layout_hits[:250],
        "install_source_checks": sorted(install_source_checks),
        "source_integrity_risk": source_integrity_risk,
        "message_ui_candidates": sorted(
            message_ui_candidates.values(), key=lambda item: item["references"], reverse=True
        ),
        "message_ui_candidate_count": sum(item["references"] for item in message_ui_candidates.values()),
        "suspicious_files": sorted(suspicious_files)[:500],
        "toolchain": Toolchain.detect().status(),
        "warnings": warnings,
        "fast_split_scan": True,
    }


def run_checked(
    args: list[str],
    log: list[str],
    cwd: Path | None = None,
    timeout: int = TOOL_TIMEOUT_SECONDS,
) -> None:
    command = [str(item) for item in args]
    log.append("$ " + " ".join(command))
    if os.environ.get("APK_CLEANER_ANDROID") == "1":
        try:
            from java import jclass
            runner = jclass("com.apkcleaner.studio.EmbeddedToolRunner")
            result = runner.run(command, str(cwd) if cwd else "")
            output = str(result.output or "")
            if output:
                lines = output.rstrip().splitlines()
                tail = lines[-80:]
                log.extend(line for line in lines if line.startswith(("RESULT ", "MESSAGE\t", "STARTUP\t", "AUTHORITY\t", "CLONE\t", "WARNING\t", "PACKAGE\t")) and line not in tail)
                log.extend(tail)
            if int(result.exitCode) != 0:
                tool, operation = "Android aracı", ""
                if "-jar" in command:
                    index = command.index("-jar")
                    tool = Path(command[index + 1]).stem
                    operation = command[index + 2] if len(command) > index + 2 else ""
                elif "-cp" in command:
                    tool = command[command.index("-cp") + 2].rsplit(".", 1)[-1]
                diagnostics = [
                    line.strip() for line in output.splitlines()
                    if line.strip() and not line.lstrip().startswith(("at ", "... ", "$ "))
                    and "APKEditor çıkış kodu" not in line
                ]
                reason = next((
                    line for line in reversed(diagnostics)
                    if line.startswith(("Caused by:", "Error:", "ERROR:", "Hata:", "Exception:"))
                ), diagnostics[-1] if diagnostics else "")
                label = f"{tool} {operation}".strip()
                detail = f": {reason[:220]}" if reason else ""
                raise RuntimeError(f"{label} başarısız oldu ({result.exitCode}){detail}.")
            return
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Gömülü Android aracı çalıştırılamadı: {exc}") from exc
    structured_dex = "local.apkcleaner.dex.DirectDexPatcher" in command
    proc = subprocess.Popen(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            encoding="utf-8" if structured_dex else None, errors="replace" if structured_dex else None)
    with _ACTIVE_TOOLS_LOCK:
        _ACTIVE_TOOLS.add(proc)
        _ACTIVE_TOOL_THREADS[proc] = threading.get_ident()
    try:
        try:
            output, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            output, _ = proc.communicate()
            if output:
                log.extend(output.rstrip().splitlines()[-80:])
            raise RuntimeError(f"Araç zaman aşımına uğradı ({timeout} sn): {Path(command[0]).name}") from None
    finally:
        with _ACTIVE_TOOLS_LOCK:
            _ACTIVE_TOOLS.discard(proc)
            _ACTIVE_TOOL_THREADS.pop(proc, None)
    if output:
        lines = output.rstrip().splitlines()
        tail = lines[-80:]
        # Doğrudan DEX yardımcısının makinece okunan sonuç satırı uzun risk
        # raporlarının başında kalabilir. Günlüğü kısaltırken bu satırı koru.
        log.extend(line for line in lines if line.startswith(("RESULT ", "MESSAGE\t", "STARTUP\t")) and line not in tail)
        log.extend(tail)
    if proc.returncode:
        raise RuntimeError(f"Araç başarısız oldu ({proc.returncode}): {Path(command[0]).name}")


def terminate_active_tools(thread_id: int | None = None) -> None:
    """Stop all tools, or only tools owned by one APK worker thread."""
    if os.environ.get("APK_CLEANER_ANDROID") == "1":
        try:
            from java import jclass
            jclass("com.apkcleaner.studio.EmbeddedToolRunner").requestCancel()
        except Exception:
            pass
        return
    with _ACTIVE_TOOLS_LOCK:
        processes = [process for process in _ACTIVE_TOOLS if thread_id is None or _ACTIVE_TOOL_THREADS.get(process) == thread_id]
    for process in processes:
        if process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
    for process in processes:
        if process.poll() is not None:
            continue
        try:
            process.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                pass


def reset_tool_cancellation() -> None:
    """Reset the embedded runner only when a new Android job is claimed."""
    if os.environ.get("APK_CLEANER_ANDROID") != "1":
        return
    try:
        from java import jclass
        jclass("com.apkcleaner.studio.EmbeddedToolRunner").clearCancellation()
    except Exception:
        pass


def _split_token(name: str) -> str:
    stem = Path(name).stem.lower().replace("-", "_").replace(".", "_")
    for prefix in ("split_config_", "config_", "split_"):
        if stem.startswith(prefix):
            return stem[len(prefix):]
    return stem


def inspect_split_components(source: Path) -> dict:
    """Describe selectable APK modules without decoding their resources."""
    if source.suffix.lower() not in SPLIT_PACKAGES or not zipfile.is_zipfile(source):
        return {"modules": [], "abis": [], "densities": [], "languages": [], "recommended_densities": {}}
    validate_package_archive(source)
    modules: list[dict] = []
    with zipfile.ZipFile(source) as archive:
        apk_entries = [name for name in archive.namelist() if name.lower().endswith(".apk") and not name.endswith("/")]
    for name in apk_entries:
        lower = Path(name).name.lower()
        token = _split_token(lower)
        normalized = token.replace("_", "-")
        kind = "feature"
        value = None
        if lower == "base.apk" or token == "base":
            kind = "base"
        else:
            for abi in KNOWN_ABIS:
                aliases = {abi, abi.replace("-", "_"), abi.replace("-", "")}
                if token in aliases or normalized == abi:
                    kind, value = "abi", abi
                    break
            if kind == "feature":
                for density in KNOWN_DENSITIES:
                    if token == density or token.endswith("_" + density):
                        kind, value = "density", density
                        break
            if kind == "feature" and token in SUPPORTED_SPLIT_LANGUAGES:
                kind, value = "language", token
            elif kind == "feature" and re.fullmatch(r"[a-z]{2}(?:_r[a-z]{2})?", token):
                kind, value = "other_language", token
        modules.append({"name": name, "kind": kind, "value": value})
    if modules and not any(item["kind"] == "base" for item in modules):
        first = next((item for item in modules if item["kind"] == "feature"), modules[0])
        first["kind"] = "base"
    abis = [abi for abi in KNOWN_ABIS if any(item["kind"] == "abi" and item["value"] == abi for item in modules)]
    densities = [density for density in KNOWN_DENSITIES if any(item["kind"] == "density" and item["value"] == density for item in modules)]
    languages = [
        {"code": code, "label": label}
        for code, label in SUPPORTED_SPLIT_LANGUAGES.items()
        if any(item["kind"] == "language" and item["value"] == code for item in modules)
    ]
    return {
        "modules": modules,
        "abis": abis,
        "densities": densities,
        "languages": languages,
        "recommended_densities": {abi: ABI_DENSITY_DEFAULTS[abi] for abi in abis if ABI_DENSITY_DEFAULTS[abi] in densities},
    }


def _selected_split_modules(inventory: dict, selection: dict | None) -> list[str]:
    if not selection:
        return [item["name"] for item in inventory["modules"]]
    selected_abis = {str(value) for value in selection.get("abis", [])}
    selected_languages = {str(value) for value in selection.get("languages", [])}
    selected_densities = {
        ABI_DENSITY_DEFAULTS[abi] for abi in selected_abis
        if abi in ABI_DENSITY_DEFAULTS
    }
    result: list[str] = []
    for module in inventory["modules"]:
        kind, value = module["kind"], module["value"]
        include = (
            kind in {"base", "feature"}
            or (kind == "abi" and value in selected_abis)
            or (kind == "density" and value in selected_densities)
            or (kind == "language" and value in selected_languages)
        )
        if include:
            result.append(module["name"])
    return result


def merge_split_package(
    source: Path,
    output_dir: Path,
    progress: Callable[[str, int], None] | None = None,
    selection: dict | None = None,
    details: dict | None = None,
) -> tuple[Path, list[str]]:
    if source.suffix.lower() not in SPLIT_PACKAGES:
        return source, []
    validate_package_archive(source)
    tools = Toolchain.detect()
    if not tools.java or not tools.apkeditor:
        raise RuntimeError("Split paket birleştirme bileşeni hazır değil. ‘Eksik bileşenleri hazırla’ düğmesini kullan.")
    output_dir.mkdir(parents=True, exist_ok=True)
    merged = output_dir / "prepared-universal.apk"
    log: list[str] = []
    (progress or (lambda _m, _p: None))("Split paket tek APK olarak birleştiriliyor", 8)
    merge_input = source
    if selection:
        inventory = inspect_split_components(source)
        selected = _selected_split_modules(inventory, selection)
        if inventory["abis"] and not selection.get("abis"):
            raise ValueError("En az bir işlemci mimarisi seçilmelidir.")
        if not any(item["kind"] == "base" and item["name"] in selected for item in inventory["modules"]):
            raise ValueError("Seçilen split bileşenlerinde temel APK bulunamadı.")
        if set(selection.get("abis", [])) - set(inventory["abis"]):
            raise ValueError("Seçilen işlemci mimarisi kaynak pakette bulunamadı.")
        if set(selection.get("languages", [])) - {item["code"] for item in inventory["languages"]}:
            raise ValueError("Seçilen dil bileşeni kaynak pakette bulunamadı.")
        filtered = output_dir / "selected-modules"
        filtered.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source) as archive:
            for index, name in enumerate(selected):
                target = filtered / f"{index:03d}-{Path(name).name}"
                with archive.open(name) as source_stream, target.open("xb") as target_stream:
                    shutil.copyfileobj(source_stream, target_stream, length=1024 * 1024)
                validate_package_archive(target)
                with zipfile.ZipFile(target) as module:
                    if "AndroidManifest.xml" not in module.namelist():
                        raise ValueError(f"Split bileşeninde manifest bulunamadı: {Path(name).name}")
        if not any(filtered.glob("*.apk")):
            raise ValueError("Seçilen split bileşenlerinden bir APK oluşturulamadı.")
        merge_input = filtered
        log.append("SELECTED " + ", ".join(selected))
        if details is not None:
            details.update({"selected_modules": selected, "module_count": len(selected), "validated": True})
    run_checked(
        [tools.java, "-jar", str(tools.apkeditor), "m", "-i", str(merge_input), "-o", str(merged), "-clean-meta"],
        log,
    )
    if not merged.is_file():
        raise RuntimeError("Split paket birleştirildi ancak çıktı APK dosyası bulunamadı.")
    return merged, log


def patch_manifest_xml(path: Path, detected_ids: set[str]) -> dict:
    profiles = load_profiles()
    prefixes = tuple(value for pid in detected_ids for value in profiles[pid].get("manifest", []))
    metadata = tuple(value for pid in detected_ids for value in profiles[pid].get("metadata", []))
    ad_permissions = {
        "com.google.android.gms.permission.AD_ID",
        "android.permission.AD_ID",
        "android.permission.ACCESS_ADSERVICES_AD_ID",
        "android.permission.ACCESS_ADSERVICES_ATTRIBUTION",
        "android.permission.ACCESS_ADSERVICES_TOPICS",
        "android.permission.AD_SERVICES_CONFIG",
    }
    tree = ET.parse(path)
    root = tree.getroot()
    removed: list[str] = []
    name_key = f"{{{ANDROID_NS}}}name"

    for parent in list(root.iter()):
        for child in list(parent):
            name = child.attrib.get(name_key, "")
            local = child.tag.rsplit("}", 1)[-1]
            should_remove = False
            if local in {"activity", "activity-alias", "service", "receiver", "provider"}:
                should_remove = bool(prefixes and name.startswith(prefixes))
            elif local == "meta-data":
                should_remove = bool(metadata and name.startswith(metadata))
            elif local in {"uses-permission", "uses-permission-sdk-23"}:
                should_remove = name in ad_permissions
            if should_remove:
                parent.remove(child)
                removed.append(f"{local}: {name}")
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return {"removed": removed, "count": len(removed)}


def patch_manifest_binary(
    source: Path,
    destination: Path,
    tools: Toolchain,
    detected_ids: set[str],
    log: list[str],
    clone_package_name: str | None = None,
) -> dict:
    """Patch binary AXML without decoding or rebuilding its resource table."""
    if not tools.java or not tools.apkeditor or not tools.binary_manifest_patcher:
        raise RuntimeError("Doğrudan manifest düzenleme aracı hazır değil.")
    profiles = load_profiles()
    prefixes = [value for pid in detected_ids for value in profiles[pid].get("manifest", [])]
    metadata = [value for pid in detected_ids for value in profiles[pid].get("metadata", [])]
    ad_permissions = [
        "com.google.android.gms.permission.AD_ID",
        "android.permission.AD_ID",
        "android.permission.ACCESS_ADSERVICES_AD_ID",
        "android.permission.ACCESS_ADSERVICES_ATTRIBUTION",
        "android.permission.ACCESS_ADSERVICES_TOPICS",
        "android.permission.AD_SERVICES_CONFIG",
    ]
    classpath = os.pathsep.join((str(tools.apkeditor), str(tools.binary_manifest_patcher)))
    command = [
        tools.java,
        "-cp",
        classpath,
        "local.apkcleaner.xml.BinaryManifestPatcher",
        "--input",
        str(source),
        "--output",
        str(destination),
    ]
    for value in prefixes:
        command.extend(("--prefix", value))
    for value in metadata:
        command.extend(("--metadata", value))
    if detected_ids:
        for value in ad_permissions:
            command.extend(("--permission", value))
    if clone_package_name:
        command.extend(("--clone-package", clone_package_name))
    manifest_log: list[str] = []
    run_checked(command, manifest_log)
    log.extend(manifest_log)
    removed = [line.split("\t", 1)[1] for line in manifest_log if line.startswith("REMOVED\t")]
    count = len(removed)
    for line in manifest_log:
        match = re.search(r"\bRESULT\s+removed=(\d+)", line)
        if match:
            count = int(match.group(1))
    if not destination.is_file():
        raise RuntimeError("Doğrudan manifest motoru çıktı üretmedi.")
    return {
        "removed": removed,
        "count": count,
        "clone_changes": [line.split("\t", 1)[1] for line in manifest_log if line.startswith("CLONE\t")],
        "clone_warnings": [line.split("\t", 1)[1] for line in manifest_log if line.startswith("WARNING\t")],
        "authority_changes": {
            fields[1]: fields[2] for line in manifest_log if line.startswith("AUTHORITY\t")
            if len(fields := line.split("\t", 2)) == 3
        },
        "references_preserved": True,
        "engine": "binary-axml",
    }


_DEEP_AD_VIEW_IDS = {
    "ad_banner",
    "ad_container",
    "ad_frame",
    "ad_holder",
    "ad_layout",
    "ad_placeholder",
    "ad_slot",
    "ad_view",
    "ad_wrapper",
    "ad_manager_view",
    "ad_view_container",
    "ad_view_holder",
    "admob_adview",
    "admob_banner",
    "admob_container",
    "adbanner",
    "adcontainer",
    "adframe",
    "adholder",
    "adlayout",
    "adplaceholder",
    "adslot",
    "adview",
    "adwrapper",
    "banner_ad",
    "banner_container",
    "banner_slot",
    "banner_view",
    "banner_view_container",
    "bannerad",
    "bannercontainer",
    "bannerslot",
    "medium_rectangle_ad",
    "google_ad_view",
    "google_ads_banner",
    "mrec_ad",
    "native_ad",
    "native_ad_container",
    "native_ad_view",
    "nativead",
    "nativeadcontainer",
    "nativeadview",
    "sponsored_ad",
}


def _resource_identifier(value: str) -> str:
    """Return a normalized Android resource name without matching ordinary text."""
    candidate = value.rsplit("/", 1)[-1].strip().lower()
    return re.sub(r"[^a-z0-9_]+", "_", candidate).strip("_")


def patch_ad_layouts(decoded: Path, detected_ids: set[str], mode: str = "balanced") -> dict:
    profiles = load_profiles()
    prefixes = tuple(
        value.rstrip(".")
        for profile_id in detected_ids
        for value in profiles[profile_id].get("manifest", [])
    )
    width_key = f"{{{ANDROID_NS}}}layout_width"
    height_key = f"{{{ANDROID_NS}}}layout_height"
    visibility_key = f"{{{ANDROID_NS}}}visibility"
    class_key = "class"
    name_key = f"{{{ANDROID_NS}}}name"
    id_key = f"{{{ANDROID_NS}}}id"
    changed_files = 0
    hidden: list[str] = []
    field_changes: list[dict] = []
    archive_entries: set[str] = set()

    for path in decoded.rglob("*.xml"):
        relative = path.relative_to(decoded).as_posix()
        parts = relative.split("/")
        is_layout = any(parts[index] == "res" and parts[index + 1].startswith("layout") for index in range(len(parts) - 1))
        if not is_layout:
            continue
        try:
            tree = ET.parse(path)
        except ET.ParseError:
            continue
        changed = False
        for element in tree.getroot().iter():
            tag = element.tag.rsplit("}", 1)[-1]
            class_name = element.attrib.get(class_key, "")
            android_name = element.attrib.get(name_key, "")
            signature = f"{tag} {class_name} {android_name}"
            sdk_view = bool(prefixes and any(prefix in signature for prefix in prefixes))
            resource_id = _resource_identifier(element.attrib.get(id_key, ""))
            # Native/banner SDK'leri çoğu zaman XML'e kendi sınıfını yazmak yerine
            # genel bir FrameLayout/ConstraintLayout bırakıp reklam görünümünü çalışma
            # anında bu kapsayıcıya ekler. Yalnızca Gelişmiş profilde ve paket içinde
            # doğrulanmış bir reklam SDK'sı varken kesin reklam kimliklerini de gizle.
            dynamic_ad_container = bool(
                mode == "deep"
                and prefixes
                and resource_id in _DEEP_AD_VIEW_IDS
            )
            if not (sdk_view or dynamic_ad_container):
                continue
            before = {
                "width": element.get(width_key),
                "height": element.get(height_key),
                "visibility": element.get(visibility_key),
            }
            element.set(width_key, "0dp")
            element.set(height_key, "0dp")
            element.set(visibility_key, "gone")
            label = class_name or android_name or tag
            if dynamic_ad_container and resource_id:
                label = f"{label} (@id/{resource_id})"
            hidden.append(f"{relative}: {label}")
            field_changes.append({
                "file": relative, "view": label, "before": before,
                "after": {"width": "0dp", "height": "0dp", "visibility": "gone"},
            })
            changed = True
        if changed:
            tree.write(path, encoding="utf-8", xml_declaration=True)
            changed_files += 1
            res_index = parts.index("res")
            archive_entries.add("/".join(parts[res_index:]))
    return {
        "hidden": hidden,
        "changes": field_changes,
        "count": len(hidden),
        "changed_files": changed_files,
        "archive_entries": sorted(archive_entries),
        "skipped": False,
    }


def rewrite_apk(source: Path, destination: Path, replacements: dict[str, Path], remove_files: set[str]) -> None:
    with zipfile.ZipFile(source, "r") as src, zipfile.ZipFile(
        destination, "w", allowZip64=True, compresslevel=1
    ) as dst:
        for info in src.infolist():
            name = info.filename
            upper = name.upper()
            if upper.startswith("META-INF/") and upper.endswith((".RSA", ".DSA", ".EC", ".SF", "MANIFEST.MF")):
                continue
            if name in remove_files:
                continue
            data = replacements[name].read_bytes() if name in replacements else src.read(name)
            dst.writestr(info, data)


def deep_removals(apk_path: Path, detected_ids: set[str]) -> set[str]:
    profiles = load_profiles()
    markers = tuple((profiles[pid].get("assets", []) + profiles[pid].get("libraries", [])) for pid in detected_ids)
    flat = tuple(item.lower() for group in markers for item in group)
    removed: set[str] = set()
    with zipfile.ZipFile(apk_path) as archive:
        for name in archive.namelist():
            lower = name.lower()
            if lower.startswith(("assets/", "lib/")) and any(marker in lower for marker in flat):
                removed.add(name)
    return removed


def find_manifest(decoded: Path) -> Path | None:
    candidates = list(decoded.rglob("AndroidManifest.xml"))
    return min(candidates, key=lambda p: len(p.parts)) if candidates else None


def sign_apk(
    unsigned: Path,
    output: Path,
    tools: Toolchain,
    log: list[str],
    *,
    optimize: bool = False,
) -> tuple[bool, str | None]:
    if os.environ.get("APK_CLEANER_ANDROID") == "1":
        try:
            from java import jclass
            runner = jclass("com.apkcleaner.studio.EmbeddedToolRunner")
            runner.signApk(str(unsigned), str(output), bool(optimize))
            log.append(
                "RESULT embedded_signer=1 alignment=" + ("1" if optimize else "0")
            )
            return output.is_file(), None if output.is_file() else "Gömülü imzalayıcı çıktı üretmedi."
        except Exception as exc:
            # Android paketinde imzasız çıktı sunmuyoruz. Önceki akış burada
            # False döndürüp hiç oluşturulmamış `*.unsigned.apk` dosyasını sonuç
            # kabul ediyor, böylece asıl imza hatası yanıltıcı Errno 2 mesajıyla
            # maskeleniyordu. Gerçek nedeni işlem durumuna taşı ve bozuk/eksik
            # bir paketin indirilmesini kesin olarak engelle.
            raise RuntimeError(f"Gömülü APK imzalayıcı başarısız oldu: {exc}") from exc
    bundled_keystore = BUNDLED_TOOLS / "output-signing.p12"
    keystore = bundled_keystore if bundled_keystore.is_file() else TOOLS / "output-signing.p12"
    keystore_password = "apkcleaner"
    keystore_alias = "apkcleaner-output"
    if not keystore.exists():
        if not tools.keytool:
            return False, "APK Cleaner Studio çıktı imzası bulunamadı ve keytool kullanılamıyor."
        keystore.parent.mkdir(parents=True, exist_ok=True)
        run_checked(
            [
                tools.keytool, "-genkeypair", "-storetype", "PKCS12",
                "-keystore", str(keystore), "-storepass", keystore_password,
                "-alias", keystore_alias, "-keypass", keystore_password,
                "-dname", "CN=APK Cleaner Studio", "-keyalg", "RSA",
                "-keysize", "2048", "-validity", "10000", "-noprompt",
            ],
            log,
        )
    if tools.java and tools.uber_signer and (not tools.apksigner or optimize):
        signer_output = unsigned.parent / "signed"
        signer_output.mkdir(parents=True, exist_ok=True)
        command = [
            tools.java,
            "-jar",
            str(tools.uber_signer),
            "--apks",
            str(unsigned),
            "--out",
            str(signer_output),
            "--allowResign",
            "--ks",
            str(keystore),
            "--ksAlias",
            keystore_alias,
            "--ksPass",
            keystore_password,
            "--ksKeyPass",
            keystore_password,
        ]
        if not optimize:
            command.append("--skipZipAlign")
        elif tools.zipalign:
            command.extend(("--zipAlignPath", str(tools.zipalign)))
        run_checked(
            command,
            log,
        )
        signed_candidates = sorted(signer_output.glob("*.apk"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not signed_candidates:
            return False, "İmzalama aracı çıktı APK üretemedi."
        shutil.copy2(signed_candidates[0], output)
        return True, None
    if not tools.apksigner:
        shutil.copy2(unsigned, output.with_suffix(".unsigned.apk"))
        return False, "apksigner bulunamadı; imzasız APK üretildi."
    prepared = unsigned
    if optimize and tools.zipalign:
        aligned = unsigned.with_name("aligned.apk")
        run_checked([tools.zipalign, "-f", "4", str(unsigned), str(aligned)], log)
        prepared = aligned
    run_checked(
        [tools.apksigner, "sign", "--ks", str(keystore), "--ks-key-alias", keystore_alias, "--ks-pass", f"pass:{keystore_password}", "--key-pass", f"pass:{keystore_password}", "--out", str(output), str(prepared)],
        log,
    )
    run_checked([tools.apksigner, "verify", "--verbose", str(output)], log)
    return True, None


def _process_one_dex(
    dex_name: str,
    dex_in: Path,
    temp: Path,
    tools: Toolchain,
    detected_ids: set[str],
    mode: str,
    strip_debug: bool,
    normalize_dex: bool = False,
    message_targets: set[str] | None = None,
    clone_strings: dict[str, str] | None = None,
) -> tuple[str, Path, dict, list[str]]:
    log: list[str] = []
    dex_out = temp / f"patched-{Path(dex_name).name}"
    profiles = load_profiles()
    descriptors = sorted({
        marker
        for profile_id in detected_ids
        for marker in profiles[profile_id]["descriptors"]
    })
    classpath = os.pathsep.join((str(tools.direct_patcher), str(tools.dexlib2)))
    command = [
        tools.java,
        "-cp",
        classpath,
        "local.apkcleaner.dex.DirectDexPatcher",
        "--input",
        str(dex_in),
        "--output",
        str(dex_out),
        "--mode",
        mode,
        "--strip-debug",
        str(strip_debug).lower(),
        "--normalize-dex",
        str(normalize_dex).lower(),
    ]
    for descriptor in descriptors:
        command.extend(("--descriptor", descriptor))
    for target in sorted(message_targets or set()):
        command.extend(("--startup-target", target))
    for original, replacement in sorted((clone_strings or {}).items()):
        command.extend(("--clone-string", original, replacement))
    run_checked(command, log)
    result_line = next((line for line in log if line.startswith("RESULT ")), None)
    if not result_line or not dex_out.is_file():
        raise RuntimeError("Doğrudan DEX motoru geçerli bir sonuç üretmedi.")
    values = {
        key: int(value)
        for key, value in re.findall(r"(\w+)=(\d+)", result_line)
    }
    patch = {
        "changed_files": values.get("changed_files", 0),
        "void_patches": values.get("void_patches", 0),
        "boolean_patches": values.get("boolean_patches", 0),
        "callback_patches": values.get("callback_patches", 0),
        "message_patches": values.get("message_patches", 0),
        "debug_directives_removed": values.get("debug_directives_removed", 0),
        "clone_strings_changed": values.get("clone_strings_changed", 0),
        "risky_calls": [line.split("\t", 1)[1] for line in log if line.startswith("RISKY\t")],
    }
    return dex_name, dex_out, patch, log


def _list_message_calls_in_dex(dex_name: str, dex_in: Path, temp: Path, tools: Toolchain) -> list[dict]:
    log: list[str] = []
    dex_out = temp / f"scanned-{Path(dex_name).name}"
    classpath = os.pathsep.join((str(tools.direct_patcher), str(tools.dexlib2)))
    run_checked([
        tools.java, "-cp", classpath, "local.apkcleaner.dex.DirectDexPatcher",
        "--input", str(dex_in), "--output", str(dex_out), "--mode", "safe",
        "--strip-debug", "false", "--normalize-dex", "false", "--list-messages", "true",
    ], log)
    calls: list[dict] = []
    for line in log:
        if not line.startswith("MESSAGE\t"):
            continue
        fields = line.split("\t")
        if len(fields) < 7:
            continue
        _, target_id, kind, owner_class, owner_method, target_class, target_method = fields[:7]
        context_signature = fields[7] if len(fields) > 7 else ""
        target_descriptor = fields[8] if len(fields) > 8 else ""
        signature = "|".join((kind, owner_class, owner_method, target_class, target_method, target_descriptor))
        calls.append({
            "id": f"{dex_name}:{target_id}", "dex": dex_name, "target_id": target_id,
            "kind": kind, "owner_class": owner_class, "owner_method": owner_method,
            "target_class": target_class, "target_method": target_method,
            "target_descriptor": target_descriptor, "context_signature": context_signature,
            "signature": signature,
        })
    return calls


def _startup_namespace(descriptor: str) -> tuple[str, ...]:
    """Return a conservative package/vendor boundary for a DEX descriptor."""
    parts = descriptor.removeprefix("L").removesuffix(";").split("/")[:-1]
    # Default-package obfuscation such as La; / Lb; has no trustworthy namespace.
    return tuple(parts[:2])


def _startup_risk_assessment(
    owner: str,
    target: str,
    lifecycle: str,
    location: str,
    confidence: str,
    deferred: bool = False,
    root_count: int = 1,
    trace: str = "",
) -> dict:
    """Rank likely injected startup calls without claiming their provenance is proven.

    The scanner deliberately combines independent structural signals.  A dialog
    sink by itself is never enough: placement around the superclass call,
    package ownership, chain purity and reuse across lifecycle roots all affect
    the result.  Scores are only triage hints; removal remains an explicit user
    choice.
    """
    score = 0
    signals: list[str] = []

    if location == "before_super":
        score += 4
        signals.append("Üst sınıf yaşam döngüsü çağrısından önce çalışıyor.")
    else:
        score += 1
        signals.append("Yaşam döngüsü gövdesinden çalışıyor; eklenmiş olduğuna tek başına kanıt değildir.")

    owner_namespace = _startup_namespace(owner)
    target_namespace = _startup_namespace(target)
    if owner == target:
        score -= 3
        signals.append("Çağrı aynı sınıfın kendi başlangıç akışında.")
    elif owner_namespace and target_namespace:
        if owner_namespace != target_namespace:
            score += 2
            signals.append("Hedef, başlangıç sınıfından farklı bir kod alanında.")
        else:
            score -= 2
            signals.append("Hedef uygulamanın kendi kod alanıyla eşleşiyor.")
    else:
        score -= 1
        signals.append("Yoğun ad karartma nedeniyle kod alanı güvenilir biçimde ayrılamadı.")

    owner_leaf = owner.removeprefix("L").removesuffix(";").rsplit("/", 1)[-1]
    target_leaf = target.removeprefix("L").removesuffix(";").rsplit("/", 1)[-1]
    owner_is_plain = bool(re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", owner_leaf))
    target_is_plain = bool(re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", target_leaf))
    if location == "before_super" and owner_is_plain and not target_is_plain:
        score += 2
        signals.append("Başlangıç sınıfı ile hedef arasında belirgin ad-karartma biçimi farkı var.")

    if confidence == "candidate":
        score += 2
        signals.append("Mesaj zinciri belirgin ek yan etki olmadan çözüldü.")
    elif confidence == "review":
        signals.append("Zincirde mesaj dışında olası yan etkiler var.")
    elif confidence == "partial":
        score -= 3
        signals.append("Çağrı grafiğinin yalnızca bir bölümü çözülebildi.")
    else:
        score -= 4
        signals.append("Çağrı zincirinin güven düzeyi belirlenemedi.")

    if root_count >= 4:
        score -= 2
        signals.append("Aynı hedef birçok başlangıç kökünde ortak kullanılıyor.")
    elif root_count >= 2:
        score -= 1
        signals.append("Aynı hedef birden fazla başlangıç kökünde kullanılıyor.")

    hop_count = trace.count(" > ") + 1 if trace else 0
    if hop_count >= 7:
        score -= 1
        signals.append("Uzun çağrı zinciri nedeniyle kaynak yorumu daha belirsiz.")
    if deferred:
        signals.append("Mesaja gecikmeli görev üzerinden ulaşılıyor.")

    if score >= 6:
        focus, assessment = "priority", "likely_added"
    elif score >= 3:
        focus, assessment = "review", "needs_review"
    else:
        focus, assessment = "other", "likely_internal"
    return {
        "score": score,
        "focus": focus,
        "assessment": assessment,
        "signals": signals,
    }


def _startup_focus_group(owner: str, target: str, location: str, confidence: str) -> str:
    """Compatibility helper used by tests and callers needing binary triage."""
    result = _startup_risk_assessment(owner, target, "", location, confidence)
    return "priority" if result["focus"] == "priority" else "other"


def inspect_startup_calls(apk_path: Path) -> list[dict]:
    """Trace and rank lifecycle roots across DEX files; provenance remains unproven."""
    tools = Toolchain.detect()
    if not tools.status()["clean_ready"]:
        raise RuntimeError("Başlangıç çağrılarını incelemek için DEX bileşenleri hazır değil.")
    with _temporary_directory(prefix="apkcleaner-startup-") as temp_name:
        temp = Path(temp_name)
        command = [tools.java, "-cp", os.pathsep.join((str(tools.direct_patcher), str(tools.dexlib2))),
                   "local.apkcleaner.dex.DirectDexPatcher", "--scan-startup"]
        with zipfile.ZipFile(apk_path) as archive:
            entries = [item for item in archive.infolist() if re.fullmatch(r"classes(?:\d+)?\.dex", item.filename)]
            if len(entries) > 64 or sum(item.file_size for item in entries) > 256 * 1024 * 1024:
                raise ValueError("Başlangıç taramasının 64 DEX / 256 MB inceleme sınırı aşıldı.")
            for item in entries:
                path = temp / item.filename
                with archive.open(item) as src, path.open("wb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
                command.extend(("--dex", item.filename, str(path)))
        log: list[str] = []
        run_checked(command, log, timeout=120)
    calls = []
    for line in log:
        if not line.startswith("STARTUP\t"):
            continue
        fields = line.split("\t")
        if len(fields) != 12:
            raise RuntimeError("Başlangıç çağrı taramasının yanıtı okunamadı.")
        _, dex, identity, kind, owner, lifecycle, target, method, location, confidence, dispatch, trace = fields
        calls.append({"id": f"{dex}:{identity}", "dex": dex, "kind": kind,
                      "owner_class": owner, "owner_method": lifecycle, "target_class": target,
                      "target_method": method, "location": location, "confidence": confidence,
                      "deferred": dispatch == "deferred", "trace": trace,
                      "provenance": "unverified"})

    target_roots: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for call in calls:
        key = (call["target_class"], call["target_method"])
        target_roots.setdefault(key, set()).add((call["owner_class"], call["owner_method"]))
    for call in calls:
        key = (call["target_class"], call["target_method"])
        assessment = _startup_risk_assessment(
            call["owner_class"], call["target_class"], call["owner_method"],
            call["location"], call["confidence"], call["deferred"],
            len(target_roots[key]), call["trace"],
        )
        call.update(assessment)

    focus_order = {"priority": 0, "review": 1, "other": 2}
    return sorted(calls, key=lambda row: (
        focus_order.get(row["focus"], 3), -row["score"],
        row["confidence"] != "candidate", row["id"],
    ))


def inspect_message_calls(apk_path: Path) -> list[dict]:
    """List terminal Toast/Snackbar/dialog show calls without changing the APK."""
    tools = Toolchain.detect()
    if not tools.status()["clean_ready"]:
        raise RuntimeError("Mesaj çağrılarını incelemek için DEX bileşenleri hazır değil.")
    with _temporary_directory(prefix="apkcleaner-messages-") as temp_name:
        temp = Path(temp_name)
        calls: list[dict] = []
        with zipfile.ZipFile(apk_path) as archive:
            dex_names = sorted(name for name in archive.namelist() if re.fullmatch(r"classes\d*\.dex", Path(name).name))
            for dex_name in dex_names:
                dex_in = temp / f"input-{Path(dex_name).name}"
                dex_in.write_bytes(archive.read(dex_name))
                calls.extend(_list_message_calls_in_dex(dex_name, dex_in, temp, tools))
        return calls


def compare_message_calls(modified_apk: Path, original_apk: Path) -> list[dict]:
    """Return only message calls whose occurrence exceeds the matching original APK."""
    from collections import Counter
    modified = inspect_message_calls(modified_apk)
    original = inspect_message_calls(original_apk)
    original_counts = Counter(item["signature"] for item in original)
    exact_original_counts = Counter(
        (item["signature"], item.get("context_signature", "")) for item in original
    )
    unmatched: dict[str, list[dict]] = {}
    for item in modified:
        signature = item["signature"]
        exact = (signature, item.get("context_signature", ""))
        # First consume calls whose offset-independent DEX neighborhood still
        # matches the original. This avoids selecting an old show() call merely
        # because a mod inserted another occurrence earlier in the method.
        if exact_original_counts[exact] > 0:
            exact_original_counts[exact] -= 1
            original_counts[signature] -= 1
            continue
        unmatched.setdefault(signature, []).append(item)

    added: list[dict] = []
    for signature, candidates in unmatched.items():
        # Recompilation can legitimately rewrite every surrounding instruction.
        # Preserve the remaining original occurrence count as a conservative
        # fallback and expose only the true numerical excess.
        excess = max(0, len(candidates) - original_counts[signature])
        for item in candidates[-excess:] if excess else []:
            safe = dict(item)
            safe.pop("signature", None)
            safe.pop("target_id", None)
            safe.pop("context_signature", None)
            safe.pop("target_descriptor", None)
            added.append(safe)
    # Mod paketlerinde tanıtım/atıf pencereleri çoğunlukla ana, açılış, ayarlar
    # veya Fragment Activity yaşam döngüsüne eklenir. Güvenlik koşulunu
    # değiştirmeden bu yüksek olasılıklı farkları önce göster.
    def priority(item: dict) -> tuple:
        owner = str(item.get("owner_class", "")).lower()
        method = str(item.get("owner_method", ""))
        activity_hint = any(name in owner for name in (
            "mainactivity", "splashactivity", "fragmentactivity", "settingsactivity", "settingactivity",
        ))
        lifecycle = method in {"onCreate", "onStart", "onResume", "onViewCreated", "onCreateView"}
        return (not (activity_hint and lifecycle), not lifecycle, item.get("dex", ""), item.get("id", ""))

    return sorted(added, key=priority)


def process_apk(
    apk_path: Path,
    output_dir: Path,
    mode: str = "balanced",
    progress: Callable[[str, int], None] | None = None,
    *,
    patch_ads: bool = True,
    strip_debug: bool = False,
    normalize_dex: bool = False,
    normalize_resources: bool = False,
    optimize_apk: bool = False,
    deobfuscate_resources: bool = False,
    source_name: str | None = None,
    split_merged: bool = False,
    split_details: dict | None = None,
    analysis_report: dict | None = None,
    message_targets: list[str] | None = None,
    clone_package_name: str | None = None,
) -> dict:
    if mode not in {"safe", "balanced", "deep"}:
        raise ValueError("Bilinmeyen temizlik profili.")
    # The server already inspected ordinary APK uploads. Reuse that immutable
    # report instead of reading and hashing the complete archive a second time.
    # Split selections still receive a fresh report because their merged APK
    # can differ from the package inspected during upload.
    report = dict(analysis_report) if analysis_report is not None else inspect_apk(apk_path)
    original_package_name = str(report.get("package_name") or "")
    if clone_package_name is not None:
        clone_package_name = validate_clone_package_name(original_package_name, clone_package_name)
    # `requires_splits` yalnızca manifest metadata'sından türetilen bir risk
    # işaretidir. Universal veya sonradan yeniden paketlenmiş APK'larda metadata
    # geride kalabilir; bu nedenle kullanıcı açıkça işlem istediğinde devam et.
    detected_ids = {item["id"] for item in report["detections"]}
    if patch_ads and not detected_ids:
        raise ValueError("Bilinen reklam SDK’sı bulunamadı; reklam yaması uygulanmadı.")
    tools = Toolchain.detect()
    tool_status = tools.status()
    selected_message_targets = {str(item) for item in (message_targets or []) if isinstance(item, str)}
    selected_startup_calls = []
    if selected_message_targets:
        available = {item["id"]: item for item in inspect_startup_calls(apk_path)}
        if not selected_message_targets.issubset(available):
            raise ValueError("Seçilen başlangıç çağrıları bu paketle eşleşmiyor. Başlangıç taramasını yeniden açıp seçim yap.")
        selected_startup_calls = [available[identity] for identity in sorted(selected_message_targets)]
    targets_by_dex: dict[str, set[str]] = {}
    for item in selected_message_targets:
        if ":" not in item:
            continue
        dex_name, target_id = item.rsplit(":", 1)
        targets_by_dex.setdefault(dex_name, set()).add(target_id)
    needs_dex = bool(clone_package_name) or strip_debug or normalize_dex or bool(targets_by_dex) or (patch_ads and bool(detected_ids))
    if needs_dex and not tool_status["clean_ready"]:
        raise RuntimeError("DEX bileşenleri hazır değil. ‘Eksik bileşenleri hazırla’ düğmesini kullan.")
    if deobfuscate_resources and not tool_status["resource_tool"]:
        raise RuntimeError("RES kaynak düzenleme bileşeni hazır değil. ‘Eksik bileşenleri hazırla’ düğmesini kullan.")
    if optimize_apk and not tools.zipalign:
        raise RuntimeError("APK optimizasyonu için zipalign bileşeni hazır değil. ‘Eksik bileşenleri hazırla’ düğmesini kullan.")
    needs_manifest = bool(patch_ads and mode in {"balanced", "deep"} and report["manifest_hits"])
    if (needs_manifest or clone_package_name) and not tool_status["manifest_tool"]:
        raise RuntimeError("Doğrudan manifest bileşeni hazır değil. ‘Eksik bileşenleri hazırla’ düğmesini kullan.")
    if not tool_status["signer"]:
        raise RuntimeError("APK imzalama bileşeni hazır değil. ‘Eksik bileşenleri hazırla’ düğmesini kullan.")

    output_dir.mkdir(parents=True, exist_ok=True)
    log: list[str] = []
    started = time.time()
    notify = progress or (lambda _message, _percent: None)
    dex_replacements: dict[str, Path] = {}
    dex_changes: list[dict] = []
    totals: dict = {
        "changed_files": 0,
        "void_patches": 0,
        "boolean_patches": 0,
        "callback_patches": 0,
        "message_patches": 0,
        "debug_directives_removed": 0,
        "clone_strings_changed": 0,
        "risky_calls": [],
    }

    with _temporary_directory(prefix="apkcleaner-") as temp_name:
        temp = Path(temp_name)
        manifest_result = {"removed": [], "count": 0, "skipped": True, "clone_changes": [], "clone_warnings": [], "authority_changes": {}}
        manifest_output = temp / "AndroidManifest-patched.bin"
        clone_strings: dict[str, str] = {}
        if clone_package_name:
            notify("Klonun paket kimliği hazırlanıyor", 10)
            manifest_source = temp / "AndroidManifest-original.bin"
            with zipfile.ZipFile(apk_path) as archive:
                manifest_source.write_bytes(archive.read("AndroidManifest.xml"))
            manifest_result = patch_manifest_binary(
                manifest_source, manifest_output, tools, detected_ids if needs_manifest else set(), log,
                clone_package_name=clone_package_name,
            )
            manifest_result["skipped"] = False
            clone_strings = {original_package_name: clone_package_name, **manifest_result["authority_changes"]}
        dex_names = [
            row["name"] for row in report["dex"]
            if clone_package_name or strip_debug or normalize_dex or row["name"] in targets_by_dex or (patch_ads and row["networks"])
        ]
        if dex_names:
            notify("DEX dosyaları hazırlanıyor", 12)
            inputs: dict[str, Path] = {}
            with zipfile.ZipFile(apk_path) as archive:
                for dex_name in dex_names:
                    dex_in = temp / f"input-{Path(dex_name).name}"
                    dex_in.write_bytes(archive.read(dex_name))
                    inputs[dex_name] = dex_in
            termux = "com.termux" in os.environ.get("PREFIX", "")
            android = os.environ.get("APK_CLEANER_ANDROID") == "1"
            # Her DEX, hem Python hem DexLib2 tarafında belleğe alınır. Android'de
            # iki büyük DEX'i aynı anda işlemek düşük bellekli cihazları düşürebilir.
            worker_limit = 1 if android else (3 if termux else 4)
            worker_count = max(1, min(len(dex_names), worker_limit, max(1, (os.cpu_count() or 2) // 2)))
            with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="dex") as pool:
                futures = {
                    pool.submit(
                        _process_one_dex, name, inputs[name], temp, tools,
                        detected_ids if patch_ads else set(), mode, strip_debug, normalize_dex,
                        targets_by_dex.get(name, set()), clone_strings,
                    ): name
                    for name in dex_names
                }
                for completed, future in enumerate(as_completed(futures), 1):
                    dex_name, dex_out, patch, dex_log = future.result()
                    dex_replacements[dex_name] = dex_out
                    before = {"size": inputs[dex_name].stat().st_size, "sha256": sha256(inputs[dex_name])}
                    after = {"size": dex_out.stat().st_size, "sha256": sha256(dex_out)}
                    dex_changes.append({
                        "file": dex_name,
                        "before": before,
                        "after": after,
                        "changed": before["sha256"] != after["sha256"],
                        "operations": {key: patch[key] for key in (
                            "void_patches", "boolean_patches", "callback_patches",
                            "message_patches", "debug_directives_removed", "clone_strings_changed",
                        )},
                        "normalized": bool(normalize_dex),
                    })
                    log.extend(dex_log)
                    for key in ("changed_files", "void_patches", "boolean_patches", "callback_patches", "message_patches", "debug_directives_removed", "clone_strings_changed"):
                        totals[key] += patch[key]
                    totals["risky_calls"].extend(patch["risky_calls"])
                    notify(f"{dex_name} işlendi ({completed}/{len(dex_names)})", 20 + int(37 * completed / len(dex_names)))

        remove_files = deep_removals(apk_path, detected_ids) if patch_ads and mode == "deep" else set()
        archive_replacements = dict(dex_replacements)
        if clone_package_name:
            archive_replacements["AndroidManifest.xml"] = manifest_output

        layout_result = {"hidden": [], "changes": [], "count": 0, "changed_files": 0, "archive_entries": [], "skipped": True}
        unsigned = apk_path
        # Yalnızca gerçekten aday kayıt taşıyan paketlerde XML katmanını aç.
        # DEX dosyaları bu aşamada ham kopyalanır; metin ara biçimine dönüştürülmez.
        should_patch_manifest = needs_manifest and not clone_package_name
        # Binary AXML string havuzu, hızlı arşiv taramasında her zaman görünmez.
        # Doğrulanmış bir reklam SDK'sı varsa XML katmanını ilk çalıştırmada açıp
        # gerçek öğe ağacında denetle; ikinci yama gerektiren eski önkoşulu kaldır.
        should_patch_layouts = bool(
            patch_ads and detected_ids and mode in {"balanced", "deep"} and tools.apkeditor
        )
        if should_patch_manifest:
            notify("Manifest reklam kayıtları doğrudan temizleniyor", 70)
            manifest_source = temp / "AndroidManifest-original.bin"
            manifest_output = temp / "AndroidManifest-patched.bin"
            with zipfile.ZipFile(apk_path) as archive:
                manifest_source.write_bytes(archive.read("AndroidManifest.xml"))
            manifest_result = patch_manifest_binary(
                manifest_source, manifest_output, tools, detected_ids, log
            )
            manifest_result["skipped"] = False
            if manifest_result["count"]:
                archive_replacements["AndroidManifest.xml"] = manifest_output

        if archive_replacements or remove_files:
            # DEX, manifest ve kesin dosya kaldırmalarını önce tek arşiv geçişinde
            # birleştir. Kaynak katmanı sonraki adımda bu güncel paket üzerinden
            # işlendiği için daha önce yapılan değişiklikler korunur.
            notify("Temel değişiklikler APK'ya yazılıyor", 78)
            staged = temp / "staged.apk"
            rewrite_apk(apk_path, staged, archive_replacements, remove_files)
            unsigned = staged

        # Eski istemcilerin gönderdiği normalize_resources isteği, sorunlu
        # -fix-types yolunu yeniden açmaz. RES korumasını kaldırma ise kullanıcının
        # istediği yalın APKEditor x -i ... -o ... komutuyla ayrı yürütülür.
        resource_result = {
            "requested": bool(deobfuscate_resources or normalize_resources),
            "applied": False,
            "skipped": False,
            "legacy_fix_types_skipped": bool(normalize_resources),
            "engine": None,
        }
        if deobfuscate_resources:
            # APKEditor'ün yalın `x` işlemi kaynak tablosunu ve binary XML'leri
            # birlikte düzenler. Özgün public.xml'i yeniden vermek korumalı/sayısal
            # adları çıktıya geri taşıdığı için özellikle kullanılmaz.
            notify("RES kaynak koruması kaldırılıyor", 82)
            refactored = temp / "resources-refactored.apk"
            run_checked(
                [
                    tools.java,
                    "-jar",
                    str(tools.apkeditor),
                    "x",
                    "-i",
                    str(unsigned),
                    "-o",
                    str(refactored),
                ],
                log,
            )
            if not refactored.is_file():
                raise RuntimeError("RES kaynak düzenleme aracı çıktı üretmedi.")
            # APKEditor'ün yalın `x` çıktısını olduğu gibi kullan. Manifesti ya da
            # diğer binary XML dosyalarını ayrıca yedekleyip geri yazma; kaynak
            # düzenleme aracının paket genelindeki doğal dönüşümünü koru.
            unsigned = refactored
            resource_result.update({
                "applied": True,
                "engine": "APKEditor x",
                "resource_names_preserved": True,
            })
        elif normalize_resources:
            resource_result.update({
                "skipped": True,
                "reason": "Riskli -fix-types isteği kaynak kimliklerini korumak için yok sayıldı.",
            })

        # Reklam alanlarını RES çözümünden sonra denetle. Böylece korumalı kaynak
        # adları ilk çalıştırmada görünür hâle gelir ve 0dp + gone düzenlemesi aynı
        # işlem içinde uygulanabilir.
        if should_patch_layouts:
            notify("XML reklam alanları temizleniyor", 86)
            decoded = temp / "decoded"
            run_checked(
                [
                    tools.java,
                    "-jar",
                    str(tools.apkeditor),
                    "d",
                    "-i",
                    str(unsigned),
                    "-o",
                    str(decoded),
                    "-t",
                    "xml",
                    "-dex",
                    "-keep-res-path",
                ],
                log,
            )
            layout_result = patch_ad_layouts(decoded, detected_ids, mode)
            changed_entries = list(layout_result.get("archive_entries", []))
            if changed_entries:
                rebuilt = temp / "xml-rebuilt.apk"
                run_checked([tools.java, "-jar", str(tools.apkeditor), "b", "-i", str(decoded), "-o", str(rebuilt)], log)
                entry_replacements: dict[str, Path] = {}
                with zipfile.ZipFile(rebuilt) as rebuilt_archive:
                    rebuilt_names = set(rebuilt_archive.namelist())
                    for index, entry in enumerate(dict.fromkeys(changed_entries)):
                        if entry not in rebuilt_names:
                            continue
                        replacement = temp / f"xml-entry-{index}.bin"
                        replacement.write_bytes(rebuilt_archive.read(entry))
                        entry_replacements[entry] = replacement
                if entry_replacements:
                    xml_staged = temp / "xml-staged.apk"
                    rewrite_apk(unsigned, xml_staged, entry_replacements, set())
                    unsigned = xml_staged

        notify("APK imzalanıyor", 92)
        stem = Path(source_name or apk_path.name).stem
        has_optional_changes = bool(
            strip_debug or normalize_dex or optimize_apk or deobfuscate_resources
            or normalize_resources or selected_message_targets
        )
        if clone_package_name:
            output_name = f"{stem}-clone{'-clean-' + mode if patch_ads else ''}.apk"
        elif split_merged and not patch_ads and not has_optional_changes:
            output_name = f"{stem}-universal.apk"
        elif patch_ads:
            output_name = f"{stem}-clean-{mode}.apk"
        elif has_optional_changes:
            output_name = f"{stem}-processed.apk"
        else:
            output_name = f"{stem}-processed.apk"
        output_apk = output_dir / output_name
        signed, sign_warning = sign_apk(unsigned, output_apk, tools, log, optimize=optimize_apk)
        actual_output = output_apk if signed else output_apk.with_suffix(".unsigned.apk")
        if not actual_output.is_file():
            detail = sign_warning or "APK imzalama aşaması çıktı dosyası üretmedi."
            raise RuntimeError(detail)
        if not signed:
            raise RuntimeError(sign_warning or "İmzasız APK kullanıcıya sunulamaz.")
        notify("Çıktının bütünlüğü ve imzası doğrulanıyor", 96)
        verification = verify_output_apk(apk_path, actual_output, tools, log, removed_files=remove_files, expected_package_name=clone_package_name)

    with zipfile.ZipFile(apk_path) as before_archive, zipfile.ZipFile(actual_output) as after_archive:
        before_names = set(before_archive.namelist())
        after_names = set(after_archive.namelist())
        manifest_change = {
            "file": "AndroidManifest.xml",
            "before": _entry_fingerprint(before_archive, "AndroidManifest.xml"),
            "after": _entry_fingerprint(after_archive, "AndroidManifest.xml"),
            "removed": manifest_result["removed"],
        }
        manifest_change["changed"] = manifest_change["before"]["sha256"] != manifest_change["after"]["sha256"]
        xml_changes = []
        for name in layout_result.get("archive_entries", []):
            if name not in after_names:
                raise RuntimeError(f"Çıktı doğrulanamadı: düzenlenen XML dosyası eksik ({name}).")
            xml_changes.append({
                "file": name,
                "before": _entry_fingerprint(before_archive, name) if name in before_names else None,
                "after": _entry_fingerprint(after_archive, name),
                "fields": [item for item in layout_result.get("changes", []) if item["file"] == name],
            })
        for row in dex_changes:
            # The signed package, not a temporary intermediate, is the report's
            # authoritative after-state (resource tools can rewrite ZIP entries).
            row["after"] = _entry_fingerprint(after_archive, row["file"])
            row["changed"] = row["before"]["sha256"] != row["after"]["sha256"]
        changes = {
            "baseline": "Birleştirilmiş APK" if split_merged else "Kaynak APK",
            "dex": sorted(dex_changes, key=lambda row: row["file"]),
            "manifest": manifest_change,
            "xml": xml_changes,
            "removed_files": sorted(remove_files),
        }

    result = {
        **report,
        "filename": source_name or report["filename"],
        "mode": mode,
        "operation": "clone" if clone_package_name else ("patch" if patch_ads or has_optional_changes else "convert"),
        "clone": {"original_package": original_package_name, "new_package": clone_package_name,
                  "changes": manifest_result.get("clone_changes", []),
                  "warnings": manifest_result.get("clone_warnings", []),
                  "dex_strings_changed": totals["clone_strings_changed"]} if clone_package_name else None,
        "split_merged": split_merged,
        "split_components": split_details or {},
        "strip_debug": strip_debug,
        "normalize_dex": normalize_dex,
        "optimized": bool(optimize_apk and signed),
        "deobfuscate_resources": deobfuscate_resources,
        "resources": resource_result,
        "patches": totals,
        "startup_calls_removed": selected_startup_calls,
        "manifest": manifest_result,
        "layouts": layout_result,
        "removed_files": sorted(remove_files),
        "changes": changes,
        "verification": verification,
        "signed": signed,
        "sign_warning": sign_warning,
        "output": actual_output.name,
        "output_sha256": sha256(actual_output),
        "duration_seconds": round(time.time() - started, 2),
        "analysis_reused": analysis_report is not None,
        "log": log[-300:],
    }
    (output_dir / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    profile_labels = {"safe": "Güvenli", "balanced": "Dengeli", "deep": "Gelişmiş"}
    lines = [
        "APK CLEANER STUDIO RAPORU",
        f"Dosya: {result['filename']}",
        f"İşlem: {'APK klonlama' if clone_package_name else 'reklam temizleme' if patch_ads else 'APK dönüştürme/iyileştirme'}",
        *([f"Özgün paket adı: {original_package_name}", f"Klon paket adı: {clone_package_name}",
           f"DEX paket/sağlayıcı sabiti: {totals['clone_strings_changed']}"] if clone_package_name else []),
        f"Temizlik profili: {profile_labels.get(mode, mode)}",
        f"Split paket birleştirildi: {'evet' if split_merged else 'hayır'}",
        *([f"Doğrulanan split bileşeni: {split_details.get('module_count', 0)}"] if split_merged and split_details else []),
        *[f"- Seçilen split modülü: {item}" for item in (split_details or {}).get("selected_modules", [])],
        f"Tespit edilen reklam ağı: {report['network_count']}",
        f"Sonuç döndürmeyen (void) çağrı yamaları: {totals['void_patches']}",
        f"Mantıksal (boolean) değer yamaları: {totals['boolean_patches']}",
        f"Reklam yükleme geri çağrısı yamaları: {totals['callback_patches']}",
        f"Kullanıcı tarafından seçilen başlangıç çağrısı yamaları: {totals['message_patches']}",
        *[f"- {item['owner_class']} -> {item['owner_method']}(): {item['target_class']} -> {item['target_method']}() ({item['dex']})" for item in selected_startup_calls],
        f"Yerinde değiştirilen DEX dosyası: {totals['changed_files']}",
        f"Silinen DEX hata ayıklama yönergesi: {totals['debug_directives_removed']}",
        f"DEX yapısı yeniden düzenlendi: {'evet' if normalize_dex else 'hayır'}",
        f"Manifest kaydı: {manifest_result['count']}",
        f"XML'de gizlenen reklam alanı: {layout_result['count']}",
        f"Kurulum kaynağı ve bütünlük denetimi: {len(report['install_source_checks'])}",
        f"Silinen kesin kalıntı: {len(remove_files)}",
        f"RES kaynak koruması kaldırıldı: {'evet' if resource_result['applied'] else 'hayır'}",
        f"APK optimizasyonu (ZIP hizalaması): {'uygulandı' if result['optimized'] else 'uygulanmadı'}",
        f"İmzalı: {'evet' if signed else 'hayır'}",
        f"Çıktı doğrulaması: {'geçti' if verification['passed'] else 'başarısız'} (ZIP CRC, manifest, DEX, imza)",
        f"İmza doğrulayıcısı: {verification['signature_tool']}",
        "",
        f"ÖNCE / SONRA ({changes['baseline']})",
        "DEX dosyaları:",
        *[
            f"- {item['file']}: {item['before']['size']} -> {item['after']['size']} bayt; "
            f"SHA-256 {item['before']['sha256']} -> {item['after']['sha256']}; "
            f"void={item['operations']['void_patches']}, boolean={item['operations']['boolean_patches']}, "
            f"callback={item['operations']['callback_patches']}, başlangıç={item['operations']['message_patches']}, "
            f"debug={item['operations']['debug_directives_removed']}"
            for item in changes["dex"]
        ],
        f"Manifest SHA-256: {manifest_change['before']['sha256']} -> {manifest_change['after']['sha256']}",
        *[f"- Kaldırılan manifest kaydı: {item}" for item in manifest_result["removed"]],
        *[f"- Klon manifest değişikliği: {item}" for item in manifest_result.get("clone_changes", [])],
        *[f"- Klon uyumluluk uyarısı: {item}" for item in manifest_result.get("clone_warnings", [])],
        "XML alanları:",
        *[
            f"- {item['file']}: {item['view']} | "
            f"genişlik {item['before']['width'] or 'belirtilmemiş'} -> 0dp, "
            f"yükseklik {item['before']['height'] or 'belirtilmemiş'} -> 0dp, "
            f"görünürlük {item['before']['visibility'] or 'varsayılan'} -> gone"
            for item in layout_result.get("changes", [])
        ],
        *[f"- {item['file']}: SHA-256 {item['before']['sha256'] if item['before'] else 'yok'} -> {item['after']['sha256']}" for item in xml_changes],
        *[f"- Kaldırılan dosya: {item}" for item in changes["removed_files"]],
        "",
        "Tespitler:",
        *[f"- {item['label']}: {item['references']} referans" for item in report["detections"]],
        "",
        "Uygulama içi mesaj adayları (otomatik değiştirilmedi):",
        *[
            f"- {item['label']}: {item['references']} referans"
            for item in report.get("message_ui_candidates", [])
        ],
        "",
        "Kurulum kaynağı ve bütünlük bulguları (otomatik değiştirilmedi):",
        *[f"- {item}" for item in report.get("install_source_checks", [])],
        "",
        "Riskli olduğu için otomatik değiştirilmemiş çağrılar:",
        *[f"- {item}" for item in totals["risky_calls"]],
    ]
    (output_dir / "report.txt").write_text("\n".join(lines), encoding="utf-8")
    notify("Tamamlandı", 100)
    return result


def clean_apk(
    apk_path: Path,
    output_dir: Path,
    mode: str = "balanced",
    progress: Callable[[str, int], None] | None = None,
) -> dict:
    return process_apk(apk_path, output_dir, mode, progress)
