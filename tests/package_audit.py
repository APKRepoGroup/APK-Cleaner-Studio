"""Audit the distributable Windows and Termux release-candidate artifacts."""

from __future__ import annotations

import json
import hashlib
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from local_artifact_runtime import local_open, local_package_server

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging"))
from build_termux import WINDOWS_SHELL_FILES
from release_integrity import verify_release
VERSION = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]
EXE = ROOT / "outputs" / f"APK-Cleaner-Studio-v{VERSION}-Windows.exe"
TERMUX = ROOT / "outputs" / f"APK-Cleaner-Studio-v{VERSION}-Termux.zip"


def release_build_snapshot(root: Path = ROOT) -> dict | None:
    """Keep tested packages immutable when commit links finalize after building."""
    path = root / "release-assets" / f"v{VERSION}" / "package-manifest.json"
    if not path.is_file():
        return None
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    if snapshot.get("schema") == 1:
        return verify_release(root, VERSION)
    if snapshot.get("version") != VERSION:
        raise RuntimeError("Dağıtım kayıt sürümü eşleşmiyor.")
    for platform, extension in (("Android", "apk"), ("Windows", "exe"), ("Termux", "zip")):
        row = snapshot["artifacts"][platform]
        expected_name = f"APK-Cleaner-Studio-v{VERSION}-{platform}.{extension}"
        if row["filename"] != expected_name:
            raise RuntimeError("Dağıtım kayıt dosya adı eşleşmiyor.")
        artifact = root / "outputs" / expected_name
        if artifact.stat().st_size != row["size_bytes"] or hashlib.sha256(artifact.read_bytes()).hexdigest() != row["sha256"]:
            raise RuntimeError(f"Test edilen dağıtım dosyası değişmiş: {expected_name}")
    return snapshot


def audit_termux() -> dict:
    snapshot = release_build_snapshot()
    forbidden_suffixes = (".pyc", ".pem", ".key", ".part", ".tmp", ".new")
    forbidden_credentials = {"signing.properties", "apk-repo.jks", "apk-cleaner-studio-release.p12"}
    allowed_pkcs12 = {"studio/tools/output-signing.p12"}
    with zipfile.ZipFile(TERMUX) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Termux ZIP CRC denetiminden geçmedi.")
        names = archive.namelist()
        leaked = [
            name for name in names
            if "__pycache__" in name
            or name.startswith("studio/jobs/")
            or name.endswith(forbidden_suffixes)
            or name in {"studio/blocked-clients.json", "studio/client-labels.json"}
            or Path(name).name.lower() in forbidden_credentials
            or name.lower().endswith((".jks", ".keystore"))
            or (name.lower().endswith((".p12", ".pfx")) and name not in allowed_pkcs12)
        ]
        if leaked:
            raise RuntimeError(f"Termux paketinde çalışma verisi bulundu: {leaked[:5]}")
        shell_files = [name for name in names if name.startswith("studio/desktop/")
                       or name.removeprefix("studio/") in WINDOWS_SHELL_FILES]
        if shell_files:
            raise RuntimeError(f"Termux paketinde Windows'a özel pencere dosyaları bulundu: {shell_files[:5]}")
        for relative in (
            "studio/server.py", "studio/engine.py", "studio/setup_tools.py", "studio/package_icon.py",
            "studio/package_info.py", "studio/app_appearance.py", "studio/web/index.html",
            "studio/web/app.js", "studio/web/boot.js", "studio/web/boot.css",
            "studio/web/theme.css", "studio/web/ui-runtime.js",
            "studio/web/icons/patreon.svg",
            "studio/tools/direct-dex-patcher.jar", "studio/tools/binary-xml-patcher.jar",
            "install-termux.sh", "start-termux.sh", "README.md", "README-TR.md", "README-TERMUX.md",
            f"RELEASE-NOTES-v{VERSION}.md", "VERSION.txt",
        ):
            source = ROOT / relative
            if snapshot and relative == snapshot["release_notes_at_build"]["filename"]:
                expected = snapshot["release_notes_at_build"]["sha256"]
                if hashlib.sha256(archive.read(relative)).hexdigest() != expected:
                    raise RuntimeError("Termux paketinin derleme anındaki sürüm notları değişmiş.")
                continue
            if archive.read(relative) != source.read_bytes():
                raise RuntimeError(f"Termux paketi güncel kaynakla eşleşmiyor: {relative}")
        if VERSION.encode() not in archive.read("VERSION.txt"):
            raise RuntimeError("Termux sürüm bilgisi güncel değil.")
        combined = b"\n".join(archive.read(name) for name in ("README.md", "README-TR.md", "README-TERMUX.md", "VERSION.txt"))
        for stale in (b"0.5.3", b"development / test"):
            if stale in combined:
                raise RuntimeError(f"Termux paketinde eski sürüm metni bulundu: {stale.decode()}")
        return {"entries": len(names), "size": TERMUX.stat().st_size, "leaked_runtime_files": 0,
                "immutable_build_snapshot_verified": snapshot is not None}


def audit_windows() -> dict:
    with EXE.open("rb") as artifact:
        if artifact.read(2) != b"MZ":
            raise RuntimeError("Windows çıktısı geçerli PE imzası taşımıyor.")
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="apk-cleaner-package-audit-", ignore_cleanup_errors=True) as folder:
        with local_package_server([str(EXE)], folder, native=True) as (base, status):
            expected_channel = "dev" if "-dev." in VERSION else "stable"
            if status["version"] != VERSION or status.get("channel") != expected_channel:
                raise RuntimeError("EXE sürümü veya kanalı paket adıyla eşleşmiyor.")
            if not status["toolchain"]["fully_ready"]:
                raise RuntimeError(f"EXE araç zinciri hazır değil: {status['toolchain']}")
            with local_open(base + "/api/desktop/network") as reply:
                if json.load(reply)["enabled"]:
                    raise RuntimeError("Windows EXE, yerel ağı varsayılan olarak açık başlattı.")
            with local_open(base + "/") as reply:
                if b'data-desktop-native="true"' not in reply.read():
                    raise RuntimeError("Windows EXE, yerel pencere arayüzünü sunmadı.")
            for name in ("index.html", "app.js", "boot.css", "theme.css", "ui-runtime.js",
                         "favicon.svg", "favicon-16.svg", "favicon.ico", "icons/patreon.svg"):
                with local_open(base + "/" + name) as reply:
                    if reply.read() != (ROOT / "studio" / "web" / name).read_bytes():
                        raise RuntimeError(f"Windows arayüz kaynağı güncel değil: {name}")
            with local_open(base + "/boot.js") as reply:
                if b"Native loopback window needs no LAN TLS probe." not in reply.read():
                    raise RuntimeError("Windows başlatıcısının yerel bağlantı ayarı bulunamadı.")
            return {"size": EXE.stat().st_size, "startup_seconds": round(time.perf_counter() - started, 2),
                    "native_loopback": True, "lan_enabled": False, "toolchain_fully_ready": True}


def main() -> int:
    verify_release()
    summary = {"version": VERSION, "termux": audit_termux(), "windows": audit_windows()}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
