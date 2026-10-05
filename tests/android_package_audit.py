"""Security audit for the signed Android release artifact."""

from __future__ import annotations

import os
import re
import subprocess
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.6.3-dev.4"
APK = ROOT / "outputs" / f"APK-Cleaner-Studio-v{VERSION}-Android.apk"
SIGNING_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "APKCleanerStudio" / "release-signing"


def android_sdk() -> Path:
    properties = ROOT / "android" / "local.properties"
    for line in properties.read_text(encoding="ascii").splitlines():
        if line.startswith("sdk.dir="):
            return Path(line.removeprefix("sdk.dir=").replace("\\:", ":").replace("\\\\", "\\"))
    raise RuntimeError("Android SDK yolu bulunamadı.")


def latest_tool(name: str) -> Path:
    matches = sorted((android_sdk() / "build-tools").glob(f"*/{name}"), reverse=True)
    if not matches:
        raise RuntimeError(f"Android aracı bulunamadı: {name}")
    return matches[0]


def manifest_text() -> str:
    result = subprocess.run(
        [str(latest_tool("aapt2.exe")), "dump", "xmltree", str(APK), "--file", "AndroidManifest.xml"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout


def assert_release_credentials_absent(apk_bytes: bytes) -> None:
    properties = SIGNING_DIR / "signing.properties"
    if not properties.is_file():
        raise RuntimeError("Haricî Release imza yapılandırması bulunamadı.")
    secrets: list[bytes] = []
    for line in properties.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if key in {"storePassword", "keyPassword"} and len(value) >= 4:
            secrets.append(value.encode("utf-8"))
    if not secrets:
        raise RuntimeError("Release parola alanları doğrulanamadı.")
    if any(secret in apk_bytes for secret in secrets):
        raise RuntimeError("Release imza parolası APK içine sızmış.")


def main() -> int:
    if not APK.is_file() or APK.read_bytes()[:2] != b"PK":
        raise RuntimeError("Android APK bulunamadı veya ZIP başlığı geçersiz.")
    raw = APK.read_bytes()
    with zipfile.ZipFile(APK) as archive:
        corrupt = archive.testzip()
        if corrupt:
            raise RuntimeError(f"APK CRC denetimi başarısız: {corrupt}")
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise RuntimeError("APK içinde yinelenen ZIP girdisi bulundu.")
        allowed_pkcs12 = {"assets/output-signing.p12"}
        allowed_public_certificates = {"assets/chaquopy/cacert.pem"}
        forbidden = [
            name
            for name in names
            if Path(name).name.lower() in {
                "signing.properties",
                "apk-repo.jks",
                "apk-cleaner-studio-release.p12",
            }
            or name.lower().endswith((".jks", ".keystore", ".key"))
            or (name.lower().endswith(".pem") and name not in allowed_public_certificates)
            or (name.lower().endswith((".p12", ".pfx")) and name not in allowed_pkcs12)
        ]
        if forbidden:
            raise RuntimeError(f"APK içinde Release kimlik bilgisi bulundu: {forbidden[:5]}")
        if not any(name.startswith("classes") and name.endswith(".dex") for name in names):
            raise RuntimeError("APK içinde DEX kodu bulunamadı.")

    assert_release_credentials_absent(raw)
    manifest = manifest_text()
    required = (
        'package="com.apkrepo.apkcleanerstudio"',
        'versionCode(0x0101021b)=6304',
        'versionName(0x0101021c)="0.6.3-dev.4"',
        'targetSdkVersion(0x01010270)=37',
        'allowBackup(0x01010280)=false',
        'usesCleartextTraffic(0x010104ec)=false',
        'name(0x01010003)="com.apkcleaner.studio.MainActivity"',
        'name(0x01010003)="com.apkcleaner.studio.LauncherActivity"',
        'name(0x01010003)="com.apkcleaner.studio.EngineService"',
        'name(0x01010003)="com.apkcleaner.studio.ApkFileProvider"',
    )
    missing = [value for value in required if value not in manifest]
    if missing:
        raise RuntimeError(f"Manifest güvenlik beklentileri eksik: {missing}")
    if "debuggable(0x0101000f)=true" in manifest or "sharedUserId" in manifest:
        raise RuntimeError("Release manifestinde güvensiz debug/paylaşılan kullanıcı ayarı bulundu.")
    if len(re.findall(r"exported\(0x01010010\)=true", manifest)) != 1:
        raise RuntimeError("Launcher dışında dışa aktarılmış Android bileşeni bulundu.")

    signer = subprocess.run(
        [str(latest_tool("apksigner.bat")), "verify", "--verbose", str(APK)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout
    if "Verified using v2 scheme (APK Signature Scheme v2): true" not in signer:
        raise RuntimeError("APK v2 imzası doğrulanamadı.")
    if "Verified using v3 scheme (APK Signature Scheme v3): true" not in signer:
        raise RuntimeError("APK v3 imzası doğrulanamadı.")

    print(
        f"Android paket denetimi geçti: {len(names)} girdi, "
        "tek dışa açık Launcher bileşeni, yedek/cleartext/debug kapalı, v2/v3 imza geçerli."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
