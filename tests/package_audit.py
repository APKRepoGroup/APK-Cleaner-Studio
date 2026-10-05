"""Audit the distributable Windows and Termux release-candidate artifacts."""

from __future__ import annotations

import json
import hashlib
import os
import signal
import socket
import ssl
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.6.3-dev.4"
EXE = ROOT / "outputs" / f"APK-Cleaner-Studio-v{VERSION}-Windows.exe"
TERMUX = ROOT / "outputs" / f"APK-Cleaner-Studio-v{VERSION}-Termux.zip"


def release_build_snapshot(root: Path = ROOT) -> dict | None:
    """Keep tested packages immutable when commit links finalize after building."""
    path = root / "release-assets" / f"v{VERSION}" / "package-manifest.json"
    if not path.is_file():
        return None
    snapshot = json.loads(path.read_text(encoding="utf-8"))
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


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def fetch(url: str) -> dict:
    context = ssl._create_unverified_context() if url.startswith("https:") else None
    with urllib.request.urlopen(url, timeout=5, context=context) as response:
        if response.status != 200:
            raise RuntimeError(f"Beklenmeyen API durumu: {response.status}")
        return json.loads(response.read())


def fetch_text(url: str) -> str:
    context = ssl._create_unverified_context() if url.startswith("https:") else None
    with urllib.request.urlopen(url, timeout=5, context=context) as response:
        if response.status != 200:
            raise RuntimeError(f"Beklenmeyen dosya durumu: {response.status}")
        return response.read().decode("utf-8")


def audit_termux() -> dict:
    snapshot = release_build_snapshot()
    forbidden_suffixes = (".pyc", ".pem", ".key", ".part", ".tmp")
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
        for relative in (
            "studio/server.py", "studio/engine.py", "studio/setup_tools.py", "studio/package_icon.py",
            "studio/package_info.py", "studio/app_appearance.py", "studio/web/index.html",
            "studio/web/app.js", "studio/web/boot.js", "studio/web/boot.css",
            "studio/web/theme.css", "studio/web/ui-runtime.js",
            "studio/tools/direct-dex-patcher.jar", "studio/tools/binary-xml-patcher.jar",
            "install-termux.sh", "start-termux.sh", "README.md", "README-TR.md", "README-TERMUX.md",
            "RELEASE-NOTES-v0.6.3-dev.4.md", "VERSION.txt",
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
    if EXE.read_bytes()[:2] != b"MZ":
        raise RuntimeError("Windows çıktısı geçerli PE imzası taşımıyor.")
    port = free_port()
    command = [str(EXE), "--host", "127.0.0.1", "--port", str(port), "--no-open", "--no-trust-prompt"]
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    # Test the packaged app without touching the user's live Studio data.
    audit_data = tempfile.TemporaryDirectory(prefix="apk-cleaner-package-audit-")
    environment = os.environ.copy()
    environment["LOCALAPPDATA"] = audit_data.name
    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=flags,
        )
    except Exception:
        audit_data.cleanup()
        raise
    started = time.perf_counter()
    try:
        deadline = time.monotonic() + 35
        while True:
            try:
                http = fetch(f"http://127.0.0.1:{port}/api/status")
                https = fetch(f"https://127.0.0.1:{port}/api/status")
                break
            except Exception:
                if process.poll() is not None:
                    raise RuntimeError(process.stdout.read() if process.stdout else "EXE erken kapandı.")
                if time.monotonic() > deadline:
                    raise RuntimeError("EXE zamanında API yanıtı vermedi.")
                time.sleep(0.15)
        if http["version"] != VERSION or https["version"] != VERSION:
            raise RuntimeError("EXE API sürümü paket adıyla eşleşmiyor.")
        expected_channel = "dev" if "-dev." in VERSION else "stable"
        if http.get("channel") != expected_channel or https.get("channel") != expected_channel:
            raise RuntimeError(f"EXE, API üzerinde {expected_channel} kanalını raporlamıyor.")
        if not http["toolchain"]["fully_ready"]:
            raise RuntimeError(f"EXE içindeki araç zinciri eksik: {http['toolchain']}")
        app_js = fetch_text(f"http://127.0.0.1:{port}/app.js")
        theme_css = fetch_text(f"http://127.0.0.1:{port}/theme.css")
        for name in ("index.html", "app.js", "boot.js", "boot.css", "theme.css", "ui-runtime.js"):
            shipped = fetch_text(f"http://127.0.0.1:{port}/{name}")
            if shipped != (ROOT / "studio" / "web" / name).read_text(encoding="utf-8"):
                raise RuntimeError(f"Windows arayüz kaynağı güncel değil: {name}")
        if "}, 510);" not in app_js or "opacity .51s" not in theme_css:
            raise RuntimeError("Windows EXE güncel başlık animasyonunu içermiyor.")
        return {
            "size": EXE.stat().st_size,
            "startup_seconds": round(time.perf_counter() - started, 2),
            "http": True,
            "https": True,
            "toolchain_fully_ready": True,
        }
    finally:
        try:
            if process.poll() is None and hasattr(signal, "CTRL_BREAK_EVENT"):
                process.send_signal(signal.CTRL_BREAK_EVENT)
            elif process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            if process.poll() is None:
                raise RuntimeError("Windows EXE süreci kapanmadı.")
            # Tek dosyalı PyInstaller başlatıcısının alt çalışma süreci de aynı
            # konsol olayını almalı; port dinlenmeye devam ediyorsa kapanış eksiktir.
            time.sleep(0.4)
            with socket.socket() as probe:
                probe.settimeout(0.5)
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    raise RuntimeError("Windows EXE alt süreci kapanıştan sonra portu dinlemeye devam ediyor.")
        finally:
            audit_data.cleanup()


def main() -> int:
    summary = {"version": VERSION, "termux": audit_termux(), "windows": audit_windows()}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
