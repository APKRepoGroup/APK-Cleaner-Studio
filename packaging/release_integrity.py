"""Prepare/verify final package checksums without building or publishing anything."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = (("Android", "apk"), ("Windows", "exe"), ("Termux", "zip"))


def fingerprint(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"Dağıtım dosyası bulunamadı veya bağlantı içeriyor: {path.name}")
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise RuntimeError(f"Dosya doğrulama sırasında değişti: {path.name}")
    if before.st_size == 0:
        raise RuntimeError(f"Dağıtım dosyası boş: {path.name}")
    return {"filename": path.name, "size_bytes": after.st_size, "sha256": digest.hexdigest()}


def release_paths(root: Path, version: str | None = None) -> tuple[str, Path, Path]:
    if version is None:
        version = json.loads((root / "package.json").read_text(encoding="utf-8"))["version"]
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+(?:-dev\.\d+)?", version):
        raise RuntimeError("Dağıtım sürümü geçersiz.")
    return (version, root / "release-assets" / f"v{version}" / "package-manifest.json",
            root / "outputs" / f"SHA256-v{version}.txt")


def checksum_bytes(artifacts: dict) -> bytes:
    return "".join(f"{artifacts[platform]['sha256'].upper()}  {artifacts[platform]['filename']}\n"
                   for platform, _ in PLATFORMS).encode("utf-8")


def verify_release(root: Path = ROOT, version: str | None = None) -> dict:
    version, manifest_path, checksum_path = release_paths(root, version)
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise RuntimeError("Final dağıtım kaydı eksik; önce release_integrity.py prepare çalıştırılmalı.")
    try:
        snapshot = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(snapshot, dict) or snapshot.get("schema") != 1 or snapshot.get("version") != version:
            raise ValueError("schema/version")
        artifacts = snapshot["artifacts"]
        if set(artifacts) != {platform for platform, _ in PLATFORMS}:
            raise ValueError("platforms")
        for platform, extension in PLATFORMS:
            expected_name = f"APK-Cleaner-Studio-v{version}-{platform}.{extension}"
            row = artifacts[platform]
            if row["filename"] != expected_name:
                raise ValueError("filename")
            actual = fingerprint(root / "outputs" / expected_name)
            if actual != row:
                raise RuntimeError(f"Test edilen dağıtım dosyası değişmiş: {expected_name}")
        if checksum_path.is_symlink() or not checksum_path.is_file() or checksum_path.read_bytes() != checksum_bytes(artifacts):
            raise RuntimeError("SHA-256 listesi son dağıtım dosyalarıyla eşleşmiyor.")
        if fingerprint(checksum_path) != snapshot["checksum_file"]:
            raise RuntimeError("SHA-256 dosyası dağıtım kaydıyla eşleşmiyor.")
        notes = snapshot["release_notes_at_build"]
        if notes["filename"] != f"RELEASE-NOTES-v{version}.md" or not re.fullmatch(r"[a-f0-9]{64}", notes["sha256"]):
            raise ValueError("notes")
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("Final dağıtım kaydı geçersiz veya sürüm/dosya adları eşleşmiyor.") from error
    return snapshot


def prepare_release(root: Path = ROOT, version: str | None = None, *, refresh: bool = False) -> dict:
    version, manifest_path, checksum_path = release_paths(root, version)
    if manifest_path.exists() and not refresh:
        # Never silently legitimize a package changed after the tested snapshot.
        return verify_release(root, version)
    if manifest_path.is_symlink() or checksum_path.is_symlink():
        raise RuntimeError("Dağıtım kayıt hedefi bağlantı içeriyor.")
    artifacts = {platform: fingerprint(root / "outputs" / f"APK-Cleaner-Studio-v{version}-{platform}.{extension}")
                 for platform, extension in PLATFORMS}
    notes = fingerprint(root / f"RELEASE-NOTES-v{version}.md")
    payload = checksum_bytes(artifacts)
    # Compute everything before replacing generated metadata; packages are read-only.
    snapshot = {"schema": 1, "version": version, "artifacts": artifacts,
                "checksum_file": {"filename": checksum_path.name, "size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()},
                "release_notes_at_build": {"filename": notes["filename"], "sha256": notes["sha256"]}}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    checksum_path.write_bytes(payload)
    manifest_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # A concurrent/replaced package must fail the final check, not receive approval.
    return verify_release(root, version)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "verify"))
    parser.add_argument("--refresh", action="store_true", help="Yalnızca yeniden test edilen paketler için mevcut kaydı yenile")
    args = parser.parse_args()
    if args.refresh and args.action != "prepare":
        parser.error("--refresh yalnızca prepare ile kullanılabilir.")
    try:
        snapshot = prepare_release(refresh=args.refresh) if args.action == "prepare" else verify_release()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Doğrulama başarısız: {error}")
        return 1
    print(f"v{snapshot['version']}: üç paket, SHA-256 listesi ve dağıtım kaydı eşleşiyor. Yayın yapılmadı.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
