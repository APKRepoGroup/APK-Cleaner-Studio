from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from engine import DATA_ROOT, ROOT

GITHUB_OWNER = "APKRepoGroup"
GITHUB_REPOSITORY = "APK-Cleaner-Studio"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPOSITORY}/releases/latest"
GITHUB_RELEASES_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPOSITORY}/releases?per_page=30"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPOSITORY}/releases/latest"
VERSION_PATTERN = re.compile(r"^(?P<stable>\d+\.\d+\.\d+)(?:-dev\.(?P<dev>\d+))?$")
RELEASE_NAME = re.compile(
    r"^APK-Cleaner-(?:Studio|Manager)-v(?P<version>\d+\.\d+\.\d+(?:-dev\.\d+)?)-Windows\.exe$",
    re.IGNORECASE,
)
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
USER_AGENT = "APK-Cleaner-Studio-Updater/2.0"
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_ASSET_BYTES = 750 * 1024 * 1024


def version_tuple(value: str) -> tuple[int, int, int, int, int]:
    match = VERSION_PATTERN.fullmatch(value.strip().removeprefix("v"))
    if not match:
        raise ValueError("Geçersiz sürüm numarası.")
    major, minor, patch = (int(part) for part in match.group("stable").split("."))
    dev = match.group("dev")
    # Aynı numaradaki kararlı sürüm, bütün geliştirme derlemelerinden yenidir.
    return major, minor, patch, 1 if dev is None else 0, int(dev or 0)


def _channel_config() -> dict:
    for path in (DATA_ROOT / "update-channel.json", ROOT / "update-channel.json"):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            continue
    return {}


def manifest_url() -> str | None:
    value = os.environ.get("APK_CLEANER_UPDATE_URL") or _channel_config().get("manifest_url") or GITHUB_API_URL
    parsed = urllib.parse.urlparse(str(value))
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    return str(value)


def platform_key() -> str:
    if os.environ.get("APK_CLEANER_ANDROID") == "1":
        return "android"
    if os.name == "nt":
        return "windows"
    return "termux"


def install_mode() -> str:
    platform = platform_key()
    if platform == "android":
        return "android"
    if platform == "windows" and getattr(sys, "frozen", False):
        return "windows"
    if platform == "termux" and (ROOT.parent / "start-termux.sh").is_file():
        return "termux"
    return "manual"


def _asset_name(version: str, platform: str | None = None) -> str:
    platform = platform or platform_key()
    suffix = {"android": "Android.apk", "windows": "Windows.exe", "termux": "Termux.zip"}[platform]
    return f"APK-Cleaner-Studio-v{version}-{suffix}"


def _trusted_github_asset_url(value: str, filename: str) -> bool:
    parsed = urllib.parse.urlparse(str(value))
    prefix = f"/{GITHUB_OWNER}/{GITHUB_REPOSITORY}/releases/download/"
    return (
        parsed.scheme == "https"
        and parsed.hostname == "github.com"
        and parsed.path.startswith(prefix)
        and urllib.parse.unquote(parsed.path.rsplit("/", 1)[-1]) == filename
        and not parsed.username
        and not parsed.password
    )


def _trusted_download_redirect(value: str) -> bool:
    parsed = urllib.parse.urlparse(str(value))
    hostname = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (
        hostname == "github.com"
        or hostname.endswith(".githubusercontent.com")
        or hostname.endswith(".githubassets.com")
    )


def find_local_update(current_version: str, search_dir: Path | None = None) -> dict | None:
    if search_dir is None:
        if not (getattr(sys, "frozen", False) and os.name == "nt"):
            return None
        search_dir = Path(sys.executable).resolve().parent
    current = version_tuple(current_version)
    current_is_dev = "-dev." in current_version
    current_core = current[:3]
    candidates: list[tuple[tuple[int, int, int, int, int], str, Path]] = []
    release_files = {
        *search_dir.glob("APK-Cleaner-Studio-v*-Windows.exe"),
        *search_dir.glob("APK-Cleaner-Manager-v*-Windows.exe"),
    }
    for path in release_files:
        match = RELEASE_NAME.fullmatch(path.name)
        if not match:
            continue
        version = match.group("version")
        if "-dev." in version and not current_is_dev:
            continue
        parsed = version_tuple(version)
        if "-dev." in version and parsed[:3] != current_core:
            continue
        if parsed > current:
            candidates.append((parsed, version, path))
    if not candidates:
        return None
    _, version, path = max(candidates, key=lambda item: item[0])
    return {
        "available": True,
        "latest_version": version,
        "source": "local",
        "filename": path.name,
        "notes": "Yeni sürüm cihazınızda hazır. Güncellemeyi uygulamak için sürüm dosyasını açın.",
        "release_notes": "",
        "download_url": None,
        "release_url": GITHUB_RELEASES_URL,
        "sha256": None,
        "automatic": False,
        "install_mode": "manual",
    }


def _read_json_response(url: str) -> dict | list:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json, application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        final = response.geturl() if hasattr(response, "geturl") else url
        parsed = urllib.parse.urlparse(final)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Güncelleme kaydı güvenli olmayan bir adrese yönlendirildi.")
        headers = getattr(response, "headers", {})
        declared = int(headers.get("Content-Length") or 0)
        if declared > MAX_MANIFEST_BYTES:
            raise ValueError("Güncelleme kaydı boyut sınırını aşıyor.")
        raw = response.read(MAX_MANIFEST_BYTES + 1)
        if len(raw) > MAX_MANIFEST_BYTES:
            raise ValueError("Güncelleme kaydı boyut sınırını aşıyor.")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, (dict, list)):
        raise ValueError("Güncelleme kaydı beklenen JSON biçiminde değil.")
    return payload


def _github_update(payload: dict, current_version: str, *, allow_prerelease: bool = False) -> dict | None:
    if payload.get("draft"):
        return None
    tag = str(payload.get("tag_name") or "").strip()
    latest = tag.removeprefix("v")
    match = VERSION_PATTERN.fullmatch(latest)
    if not match:
        return None
    is_dev = match.group("dev") is not None
    is_prerelease = bool(payload.get("prerelease"))
    # GitHub işaretinin sürüm etiketiyle uyuşması zorunludur. Kararlı kanal hiçbir
    # koşulda dev etiketini; dev kanalı da yanlışlıkla kararlı işaretlenmiş bir
    # dev paketini kabul etmez.
    if is_dev and (not allow_prerelease or not is_prerelease):
        return None
    if not is_dev and is_prerelease:
        return None
    if version_tuple(latest) <= version_tuple(current_version):
        return None
    filename = _asset_name(latest)
    asset = next(
        (item for item in payload.get("assets", []) if isinstance(item, dict) and item.get("name") == filename),
        None,
    )
    if not asset or asset.get("state") not in (None, "uploaded"):
        raise ValueError(f"{filename} GitHub sürümünde bulunamadı.")
    download_url = str(asset.get("browser_download_url") or "")
    if not _trusted_github_asset_url(download_url, filename):
        raise ValueError("Platform paketi beklenen GitHub adresinde değil.")
    size = int(asset.get("size") or 0)
    if size <= 0 or size > MAX_ASSET_BYTES:
        raise ValueError("Platform paketinin boyutu güvenli sınırların dışında.")
    digest = str(asset.get("digest") or "").lower()
    sha256 = digest.split(":", 1)[1] if digest.startswith("sha256:") else ""
    if sha256 and not SHA256_PATTERN.fullmatch(sha256):
        raise ValueError("GitHub paket özeti geçersiz.")
    release_url = str(payload.get("html_url") or GITHUB_RELEASES_URL)
    release = urllib.parse.urlparse(release_url)
    if release.scheme != "https" or release.hostname != "github.com":
        release_url = GITHUB_RELEASES_URL
    mode = install_mode()
    return {
        "available": True,
        "latest_version": latest,
        "source": "github",
        "filename": filename,
        "notes": (
            "Yeni test sürümü kullanıma hazır. Güncelleme notlarına aşağıdan ulaşabilirsiniz."
            if is_dev else "Yeni sürüm kullanıma hazır. Güncelleme notlarına aşağıdan ulaşabilirsiniz."
        ),
        "release_notes": str(payload.get("body") or "")[:32000],
        "published_at": payload.get("published_at"),
        "download_url": download_url,
        "release_url": release_url,
        "sha256": sha256 or None,
        "size": size,
        "automatic": bool(sha256) and mode != "manual",
        "install_mode": mode,
        "release_channel": "dev" if is_dev else "stable",
    }


def _github_release_list_update(payload: list, current_version: str) -> dict | None:
    allow_prerelease = "-dev." in current_version
    current_core = version_tuple(current_version)[:3]
    candidates = [
        update
        for item in payload
        if isinstance(item, dict)
        for update in (_github_update(item, current_version, allow_prerelease=allow_prerelease),)
        if update is not None
        and (update.get("release_channel") != "dev" or version_tuple(update["latest_version"])[:3] == current_core)
    ]
    return max(candidates, key=lambda item: version_tuple(item["latest_version"])) if candidates else None


def _legacy_update(payload: dict, current_version: str) -> dict | None:
    latest = str(payload.get("version", ""))
    latest_parsed = version_tuple(latest)
    current_parsed = version_tuple(current_version)
    if "-dev." in latest and ("-dev." not in current_version or latest_parsed[:3] != current_parsed[:3]):
        return None
    if latest_parsed <= current_parsed:
        return None
    platform = platform_key()
    platform_url = payload.get(f"{platform}_url")
    download_url = str(platform_url or payload.get("download_url") or "")
    filename = str(payload.get("filename") or _asset_name(latest, platform))
    if download_url and not _trusted_github_asset_url(download_url, filename):
        download_url = ""
    sha256 = str(payload.get("sha256") or "").lower()
    if not SHA256_PATTERN.fullmatch(sha256):
        sha256 = ""
    mode = install_mode()
    return {
        "available": True,
        "latest_version": latest,
        "source": "remote",
        "filename": filename,
        "notes": (
            "Yeni test sürümü kullanıma hazır. Güncelleme notlarına aşağıdan ulaşabilirsiniz."
            if "-dev." in latest else "Yeni sürüm kullanıma hazır. Güncelleme notlarına aşağıdan ulaşabilirsiniz."
        ),
        "release_notes": str(payload.get("release_notes") or payload.get("notes") or "")[:32000],
        "published_at": payload.get("published_at"),
        "download_url": download_url or None,
        "release_url": GITHUB_RELEASES_URL,
        "sha256": sha256 or None,
        "size": int(payload.get("size") or 0),
        "automatic": bool(download_url and sha256) and mode != "manual",
        "install_mode": mode,
    }


def fetch_remote_update(current_version: str, url: str) -> dict | None:
    payload = _read_json_response(url)
    if isinstance(payload, list):
        return _github_release_list_update(payload, current_version)
    if "tag_name" in payload or "assets" in payload:
        return _github_update(payload, current_version, allow_prerelease="-dev." in current_version)
    return _legacy_update(payload, current_version)


def check_for_updates(current_version: str) -> dict:
    local = find_local_update(current_version)
    url = manifest_url()
    remote = None
    warning = None
    if url:
        try:
            request_url = GITHUB_RELEASES_API_URL if "-dev." in current_version and url == GITHUB_API_URL else url
            remote = fetch_remote_update(current_version, request_url)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            warning = f"Güncelleme kanalı şu anda kontrol edilemedi: {exc}"
    updates = [item for item in (local, remote) if item]
    selected = max(
        updates,
        key=lambda item: (version_tuple(item["latest_version"]), bool(item.get("automatic")), item.get("source") == "github"),
    ) if updates else None
    return {
        "current_version": current_version,
        "available": bool(selected),
        "configured": bool(url),
        "update": selected,
        "warning": warning,
        "channel": "dev" if "-dev." in current_version else "stable",
    }


def _download_verified_asset(update: dict) -> Path:
    filename = str(update.get("filename") or "")
    address = str(update.get("download_url") or "")
    expected = str(update.get("sha256") or "").lower()
    expected_size = int(update.get("size") or 0)
    if not filename or not _trusted_github_asset_url(address, filename):
        raise ValueError("Güncelleme paketi güvenilir GitHub adresinden gelmiyor.")
    if not SHA256_PATTERN.fullmatch(expected):
        raise ValueError("Otomatik güncelleme için SHA-256 doğrulaması bulunmuyor.")
    update_dir = DATA_ROOT / "updates"
    update_dir.mkdir(parents=True, exist_ok=True)
    destination = update_dir / filename
    temporary = update_dir / f".{filename}.{uuid.uuid4().hex}.part"
    digest = hashlib.sha256()
    request = urllib.request.Request(address, headers={"User-Agent": USER_AGENT, "Accept": "application/octet-stream"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            final = response.geturl() if hasattr(response, "geturl") else address
            if not _trusted_download_redirect(final):
                raise ValueError("Güncelleme paketi güvenilir olmayan bir adrese yönlendirildi.")
            declared = int(getattr(response, "headers", {}).get("Content-Length") or 0)
            if declared > MAX_ASSET_BYTES:
                raise ValueError("Güncelleme paketi boyut sınırını aşıyor.")
            total = 0
            with temporary.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_ASSET_BYTES:
                        raise ValueError("Güncelleme paketi boyut sınırını aşıyor.")
                    digest.update(chunk)
                    output.write(chunk)
        if expected_size and total != expected_size:
            raise ValueError("İndirilen güncelleme paketinin boyutu GitHub kaydıyla eşleşmiyor.")
        if digest.hexdigest().lower() != expected:
            raise ValueError("İndirilen güncelleme paketinin SHA-256 doğrulaması başarısız oldu.")
        temporary.replace(destination)
        return destination
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _stage_windows_update(update: dict) -> dict:
    if not (os.name == "nt" and getattr(sys, "frozen", False)):
        return {"status": "manual", "url": update.get("download_url") or update.get("release_url")}
    package = _download_verified_asset(update)
    current = Path(sys.executable).resolve()
    # Taşınabilir EXE'nin adı sürüm numarası içerse bile aynı yolu güncelle.
    # Böylece masaüstü kısayolu veya kullanıcının sabitlediği yol bozulmaz.
    destination = current
    helper = DATA_ROOT / "updates" / f"apply-{uuid.uuid4().hex}.ps1"
    helper.write_text(
        "param([int]$ParentPid,[string]$Source,[string]$Destination,[string]$Expected)\n"
        "$ErrorActionPreference='Stop'\n"
        "Wait-Process -Id $ParentPid -ErrorAction SilentlyContinue\n"
        "$actual=(Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash.ToLowerInvariant()\n"
        "if($actual -ne $Expected.ToLowerInvariant()){exit 2}\n"
        "Move-Item -LiteralPath $Source -Destination $Destination -Force\n"
        "Start-Process -FilePath $Destination\n"
        "Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue\n",
        encoding="utf-8-sig",
    )
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [
            "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-WindowStyle", "Hidden", "-File", str(helper), str(os.getpid()), str(package),
            str(destination), str(update["sha256"]),
        ],
        close_fds=True,
        creationflags=creation_flags,
    )
    return {"status": "restarting", "version": update["latest_version"], "shutdown": True}


def _stage_termux_update(update: dict) -> dict:
    installation = ROOT.parent.resolve()
    if not (installation / "start-termux.sh").is_file():
        return {"status": "manual", "url": update.get("download_url") or update.get("release_url")}
    package = _download_verified_asset(update)
    manifest = installation / ".apk-cleaner-update.json"
    payload = {
        "version": update["latest_version"],
        "archive": str(package.resolve()),
        "sha256": update["sha256"],
        "created_at": int(time.time()),
    }
    temporary = manifest.with_suffix(".json.part")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(manifest)
    return {"status": "restarting", "version": update["latest_version"], "shutdown": True}


def stage_update(current_version: str) -> dict:
    result = check_for_updates(current_version)
    update = result.get("update")
    if not result.get("available") or not isinstance(update, dict):
        raise ValueError("Kurulabilecek yeni bir sürüm bulunmuyor.")
    if not update.get("automatic"):
        return {"status": "manual", "url": update.get("download_url") or update.get("release_url")}
    mode = update.get("install_mode")
    if mode == "windows":
        return _stage_windows_update(update)
    if mode == "termux":
        return _stage_termux_update(update)
    return {"status": "native", "update": update}
