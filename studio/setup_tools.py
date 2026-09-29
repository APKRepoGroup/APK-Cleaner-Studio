from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from engine import DATA_ROOT, RUNTIME, TOOLS, Toolchain

USER_AGENT = "APK-Cleaner-Studio/0.6.3-dev.2"
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_RUNTIME_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_RUNTIME_EXPANDED_BYTES = 3 * 1024 * 1024 * 1024
MAX_RUNTIME_ENTRY_BYTES = 1024 * 1024 * 1024
MAX_RUNTIME_ENTRIES = 100_000


def _require_https(url: str) -> None:
    parsed = urllib.parse.urlparse(str(url))
    if parsed.scheme != "https" or not parsed.netloc:
        raise RuntimeError("Yalnızca HTTPS indirmelerine izin verilir.")


def _safe_target(root: Path, name: str) -> Path:
    normalized = str(name or "").replace("\\", "/")
    if not normalized or normalized.startswith("/") or "\x00" in normalized:
        raise RuntimeError("Arşiv güvenli olmayan bir dosya yolu içeriyor.")
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." or ":" in part for part in parts):
        raise RuntimeError("Arşiv güvenli olmayan bir dosya yolu içeriyor.")
    target = root.joinpath(*parts).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise RuntimeError("Arşiv hedef klasörün dışına çıkmaya çalışıyor.") from exc
    return target


def _safe_unpack_archive(archive_path: Path, destination: Path) -> None:
    total = 0
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_RUNTIME_ENTRIES:
                raise RuntimeError("Java arşivinde çok fazla dosya bulunuyor.")
            for item in entries:
                mode = (item.external_attr >> 16) & 0xFFFF
                if (mode & 0o170000) == 0o120000:
                    raise RuntimeError("Java arşivi sembolik bağlantı içeriyor.")
                if item.file_size > MAX_RUNTIME_ENTRY_BYTES:
                    raise RuntimeError("Java arşivindeki bir dosya boyut sınırını aşıyor.")
                total += item.file_size
                if total > MAX_RUNTIME_EXPANDED_BYTES:
                    raise RuntimeError("Java arşivi açılmış boyut sınırını aşıyor.")
                target = _safe_target(destination, item.filename)
                if item.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                permissions = mode & 0o777
                if permissions:
                    target.chmod(permissions)
        return

    try:
        archive = tarfile.open(archive_path, mode="r:*")
    except tarfile.TarError as exc:
        raise RuntimeError("Java çalışma ortamı arşivi tanınmıyor.") from exc
    with archive:
        entries = archive.getmembers()
        if len(entries) > MAX_RUNTIME_ENTRIES:
            raise RuntimeError("Java arşivinde çok fazla dosya bulunuyor.")
        for item in entries:
            if item.issym() or item.islnk() or item.isdev() or item.isfifo():
                raise RuntimeError("Java arşivi güvenli olmayan bağlantı veya aygıt girdisi içeriyor.")
            if item.size > MAX_RUNTIME_ENTRY_BYTES:
                raise RuntimeError("Java arşivindeki bir dosya boyut sınırını aşıyor.")
            total += item.size
            if total > MAX_RUNTIME_EXPANDED_BYTES:
                raise RuntimeError("Java arşivi açılmış boyut sınırını aşıyor.")
            target = _safe_target(destination, item.name)
            if item.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not item.isfile():
                continue
            source = archive.extractfile(item)
            if source is None:
                raise RuntimeError("Java arşivindeki dosya okunamadı.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            target.chmod(item.mode & 0o777)


def download(url: str, destination: Path, expected_sha256: str | None = None) -> None:
    _require_https(url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    written = 0
    try:
        with urllib.request.urlopen(request, timeout=180) as response, temp.open("wb") as output:
            _require_https(response.geturl() if hasattr(response, "geturl") else url)
            declared = int(getattr(response, "headers", {}).get("Content-Length") or 0)
            if declared > MAX_RUNTIME_ARCHIVE_BYTES:
                raise RuntimeError("İndirilen dosya boyut sınırını aşıyor.")
            while chunk := response.read(1024 * 1024):
                written += len(chunk)
                if written > MAX_RUNTIME_ARCHIVE_BYTES:
                    raise RuntimeError("İndirilen dosya boyut sınırını aşıyor.")
                digest.update(chunk)
                output.write(chunk)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    if expected_sha256 and digest.hexdigest().lower() != expected_sha256.lower():
        temp.unlink(missing_ok=True)
        raise RuntimeError("İndirilen dosyanın SHA-256 doğrulaması başarısız oldu.")
    temp.replace(destination)


def _temurin_package() -> tuple[str, str, str]:
    os_name = "windows" if os.name == "nt" else "linux"
    machine = platform.machine().lower()
    architecture = "aarch64" if machine in {"arm64", "aarch64"} else "x64"
    query = urllib.parse.urlencode({
        "architecture": architecture,
        "image_type": "jre",
        "os": os_name,
        "vendor": "eclipse",
    })
    request = urllib.request.Request(
        f"https://api.adoptium.net/v3/assets/latest/17/hotspot?{query}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        _require_https(response.geturl() if hasattr(response, "geturl") else request.full_url)
        raw = response.read(MAX_METADATA_BYTES + 1)
    if len(raw) > MAX_METADATA_BYTES:
        raise RuntimeError("Temurin paket bilgisi boyut sınırını aşıyor.")
    assets = json.loads(raw.decode("utf-8"))
    if not isinstance(assets, list) or not assets:
        raise RuntimeError("Bu platform için Temurin 17 JRE paketi bulunamadı.")
    package = assets[0]["binary"]["package"]
    link, checksum, name = str(package["link"]), str(package["checksum"]), str(package["name"])
    _require_https(link)
    if not re.fullmatch(r"[a-fA-F0-9]{64}", checksum):
        raise RuntimeError("Temurin paket özeti geçersiz.")
    return link, checksum, Path(name).name


def install_portable_java() -> str:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    if "com.termux" in os.environ.get("PREFIX", ""):
        failures: list[str] = []
        for package in ("openjdk-25", "openjdk-21"):
            process = subprocess.run(
                ["pkg", "install", "-y", package],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            if process.returncode == 0:
                return package
            failures.append((process.stdout or f"{package} kurulamadı")[-300:])
        raise RuntimeError("Termux Java kurulumu başarısız oldu: " + " | ".join(failures))

    url, checksum, filename = _temurin_package()
    suffix = ".zip" if filename.lower().endswith(".zip") else ".tar.gz"
    archive = DATA_ROOT / f"temurin-17{suffix}"
    download(url, archive, checksum)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="java-install-", dir=DATA_ROOT) as temp_name:
        extracted = Path(temp_name) / "extracted"
        extracted.mkdir()
        _safe_unpack_archive(archive, extracted)
        java_name = "java.exe" if os.name == "nt" else "java"
        candidates = sorted(extracted.rglob(java_name))
        candidates = [path for path in candidates if path.parent.name == "bin"]
        if not candidates:
            raise RuntimeError("Temurin paketi içinde Java çalıştırıcısı bulunamadı.")
        source_root = candidates[0].parent.parent
        destination = RUNTIME / "temurin-17"
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source_root, destination)
    archive.unlink(missing_ok=True)
    return "Temurin 17 JRE"


def install() -> dict:
    TOOLS.mkdir(parents=True, exist_ok=True)
    installed: list[str] = []
    errors: list[str] = []

    if os.environ.get("APK_CLEANER_ANDROID") == "1":
        status = Toolchain.detect().status()
        return {
            "installed": ["Gömülü Android motor bileşenleri"],
            "errors": [],
            "toolchain": status,
            "ready": status["fully_ready"],
        }

    if "com.termux" in os.environ.get("PREFIX", "") and not Toolchain.detect().zipalign:
        try:
            process = subprocess.run(
                ["pkg", "install", "-y", "aapt"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            if process.returncode:
                raise RuntimeError((process.stdout or "Termux aapt kurulumu başarısız oldu")[-600:])
            installed.append("aapt / zipalign")
        except Exception as exc:
            errors.append(f"zipalign: {exc}")

    if not Toolchain.detect().java:
        try:
            installed.append(install_portable_java())
        except Exception as exc:
            errors.append(f"Java: {exc}")

    if not Toolchain.detect().apkeditor:
        errors.append("APKEditor.jar: doğrulanmış gömülü bileşen eksik; uygulama paketini güvenilir kaynaktan yeniden kur.")

    if not Toolchain.detect().uber_signer:
        errors.append("APK imzalayıcı: doğrulanmış gömülü bileşen eksik; uygulama paketini güvenilir kaynaktan yeniden kur.")

    status = Toolchain.detect().status()
    return {
        "installed": installed,
        "errors": errors,
        "toolchain": status,
        "ready": status["fully_ready"],
    }


if __name__ == "__main__":
    print(json.dumps(install(), ensure_ascii=False, indent=2))
