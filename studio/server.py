from __future__ import annotations

import argparse
import atexit
import ctypes
import hashlib
import ipaddress
import json
import mimetypes
import os
import re
import shutil
import socket
import ssl
import sys
import textwrap
import tempfile
import threading
import time
import traceback
import uuid
import webbrowser
from email import policy
from email.message import Message
from email.parser import BytesParser
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from engine import (
    DATA_ROOT,
    ENGINE_VERSION,
    SPLIT_PACKAGES,
    SUPPORTED_PACKAGES,
    Toolchain,
    inspect_apk,
    inspect_split_package,
    inspect_split_components,
    inspect_startup_calls,
    merge_split_package,
    process_apk,
    reset_tool_cancellation,
    terminate_active_tools,
)
from setup_tools import install as install_tools
from updater import check_for_updates, stage_update
from device_catalog import DeviceCatalog


_JSON_WRITE_LOCK = threading.Lock()
ANDROID_RUNTIME = os.environ.get("APK_CLEANER_ANDROID") == "1"
if not ANDROID_RUNTIME:
    from local_tls import ensure_local_tls, root_is_trusted_on_windows, trust_root_on_windows

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
JOBS = DATA_ROOT / "jobs"
CLIENT_LABELS_PATH = DATA_ROOT / "client-labels.json"
CLIENT_BLOCKLIST_PATH = DATA_ROOT / "blocked-clients.json"
DEVICE_CATALOG_CACHE = DATA_ROOT / "device-catalog.json"
LOCAL_CA_PATH = DATA_ROOT / "tls" / "local-root-ca.crt"
MAX_UPLOAD = 1024 * 1024 * 1024 + 1024 * 1024  # 1 GB package plus multipart framing
UPLOAD_CHUNK_SIZE = 1024 * 1024
JOB_RETENTION_SECONDS = 14 * 24 * 60 * 60
MAX_JOB_DIRECTORIES = 100
MAX_OWNER_JOBS = 25
MAX_JOB_STORAGE_BYTES = 4 * 1024 * 1024 * 1024
JOB_ID = re.compile(r"^[a-f0-9]{32}$")
VERSION = "0.6.3-dev.3"
RELEASE_CHANNEL = "dev"
DEFAULT_HOST = "0.0.0.0"
CONSOLE_COLUMNS = 110
CONSOLE_ROWS = 30
CONSOLE_WIDTH = 106
PANEL_INDENT = "  "
_ICON_HANDLES: tuple[int | None, int | None] = (None, None)
_ACTIVE_SERVER: ThreadingHTTPServer | None = None
_CONSOLE_CLOSE_HANDLER = None
_BROWSER_TIMER: threading.Timer | None = None
_ANSI_ENABLED = False
_CLIENTS: dict[str, dict] = {}
_CLIENTS_LOCK = threading.Lock()
_CLIENT_LABELS: dict[str, str] = {}
_BLOCKED_CLIENTS: set[str] = set()
_ACTIVE_JOBS: set[str] = set()
_SCANNING_JOBS: set[str] = set()
_JOB_CANCEL_EVENTS: dict[str, threading.Event] = {}
_JOB_THREADS: dict[str, int] = {}
_ACTIVE_JOBS_LOCK = threading.Lock()
_ANALYZE_SLOTS = threading.BoundedSemaphore(2)
_PUBLIC_ORIGIN_LOCK = threading.Lock()
_PUBLIC_HTTPS_ORIGIN = ""
_DEVICE_CATALOG = DeviceCatalog(DEVICE_CATALOG_CACHE)
# Bağlantısı kesilen cihazı kısa süre görünür tut; ardından oturum listesinden kaldır.
CLIENT_RETENTION_SECONDS = 5 * 60
CLIENT_LIMIT = 32
CLIENT_ONLINE_SECONDS = 25
TRUSTED_PUBLIC_SUFFIXES = (".keenetic.link",)
UA_CLIENT_HINTS = "Sec-CH-UA-Model, Sec-CH-UA-Platform, Sec-CH-UA-Platform-Version, Sec-CH-UA-Mobile, Sec-CH-UA-Form-Factors"
CLIENT_COOKIE_NAME = "apk_cleaner_client_id"


def localized_error_message(error: BaseException) -> str:
    raw = str(error.args[0]) if isinstance(error, KeyError) and error.args else str(error or "")
    match = re.fullmatch(r"There is no item named (['\"])(.+)\1 in the archive", raw)
    if match:
        return f'APK arşivinde beklenen dosya bulunamadı: "{match.group(2)}".'
    translations = (
        (r"no space left|disk (?:is )?full|not enough space", "İşlem için yeterli boş depolama alanı yok."),
        (r"outofmemory|out of memory|cannot allocate memory|memoryerror", "İşlem için yeterli kullanılabilir bellek yok."),
        (r"permission denied|access.*denied|operation not permitted", "İşlem için gereken dosyaya erişim izni yok."),
        (r"no such file|file not found|cannot find.*file", "İşlem için gereken dosya bulunamadı."),
        (r"not a zip file|badzipfile|bad crc|corrupt.*archive|invalid.*zip", "Paket arşivi bozuk veya desteklenen biçimde değil."),
        (r"certificate verify failed|ssl.*error|tls.*error", "Güvenli bağlantının sertifikası doğrulanamadı."),
        (r"timed? out|timeout|time.?out", "İşlem zaman aşımına uğradı. Bağlantıyı ve işlem durumunu kontrol et."),
        (r"connection refused|connection reset|failed to fetch|network.*error|urlopen error|name.*not known", "Bağlantı kurulamadı. Ağ bağlantısını ve yerel işlem motorunu kontrol et."),
        (r"unexpected token|json.*(?:decode|parse)|invalid json", "İşlem yanıtı okunamadı veya geçerli biçimde değil."),
    )
    for pattern, translated in translations:
        if re.search(pattern, raw, re.IGNORECASE):
            return translated
    if isinstance(error, MemoryError):
        return "İşlem için yeterli kullanılabilir bellek yok."
    if isinstance(error, PermissionError):
        return "İşlem için gereken dosyaya erişim izni yok."
    if isinstance(error, FileNotFoundError):
        return "İşlem için gereken dosya bulunamadı."
    # Do not expose an English tool suffix after an authored Turkish explanation.
    message = raw.splitlines()[0].strip() if raw else ""
    def is_turkish(text):
        return bool(re.search(r"[çğıöşüÇĞİÖŞÜ]", text) or re.search(
            r"\b(?:bilinmeyen|temizlik|paket|dosya|yerel|hata|kurulum|profil|rapor|klon|kaynak|iptal)\b", text.lower()))
    if re.search(r"(?:^|\s)(?:error|exception|failed|unable|cannot|invalid|unsupported|unexpected)\b|java\.[\w.]+", message, re.IGNORECASE):
        prefix = message.split(":", 1)[0].strip()
        return prefix + "." if is_turkish(prefix) else "İşlem bileşeni beklenmeyen bir hata nedeniyle tamamlanamadı."
    return message if is_turkish(message) else "İşlem beklenmeyen bir hata nedeniyle tamamlanamadı."


def public_error(error: BaseException, *, translate: bool = True) -> str:
    """Return a useful API error without disclosing local filesystem layout."""
    message = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+", " ", localized_error_message(error) if translate else str(error or "")).strip()
    for sensitive in sorted(
        {str(DATA_ROOT), str(ROOT.parent), str(Path.home()), tempfile.gettempdir()},
        key=len,
        reverse=True,
    ):
        if sensitive:
            message = re.sub(re.escape(sensitive), "[yerel-dizin]", message, flags=re.IGNORECASE)
    return message[:1000] or "İşlem güvenli biçimde tamamlanamadı."


def diagnostic_error(error: BaseException, *, identifiers: tuple[str, ...] = (), translate: bool = True) -> str:
    """Keep the error summary, not raw logs, credentials or private identifiers."""
    raw = localized_error_message(error) if translate else str(error or "")
    # Extra lines can contain a tool's command, log or Java traceback.
    message = next((line.strip() for line in raw.splitlines() if line.strip()), "")[:4096]
    for identifier in sorted(set(identifiers), key=len, reverse=True):
        if identifier:
            message = re.sub(re.escape(identifier), "[paket-bilgisi]", message, flags=re.IGNORECASE)
    # Remove secrets before path/URL cleanup, including quoted values with spaces.
    value = r'''(?:pass:)?(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;]+)'''
    message = re.sub(
        r"(?i)(--(?:ks-pass|key-pass|password|token|secret|api-key)\s+|"
        r"\b(?:password|passwd|token|secret|api[_-]?key|authorization|ks-pass|key-pass)\s*[:=]\s*)"
        + r"(?:Bearer\s+)?" + value,
        r"\1[gizli-bilgi]", message,
    )
    message = re.sub(r"(?i)\bpass:" + value, "[gizli-bilgi]", message)
    message = re.sub(r"(?i)https?://[^\s<>\"']+", "[adres]", message)
    # Quoted paths can contain spaces; unquoted paths stop at whitespace.
    message = re.sub(r'''(["'])(?:[A-Za-z]:[\\/]|/|\\\\)[^"'\r\n]*\1''', "[yerel-dosya]", message)
    message = re.sub(r'''(?<![\w])(?:[A-Za-z]:[\\/]|\\\\)[^\s<>"']+''', "[yerel-dosya]", message)
    message = re.sub(r'''(?<![\w])/(?:[^\s<>"']+)''', "[yerel-dosya]", message)
    message = re.sub(r"(?i)\b[\w.-]+\.(?:apk|apks|apkm|xapk|jks|keystore|p12|pfx)\b", "[paket-dosyası]", message)
    message = public_error(RuntimeError(message), translate=translate)
    match = re.search(r"başarısız oldu \((-?\d{1,3})\)", raw)
    if match:
        message += f" · Gömülü araç çıkış kodu: {match.group(1)}"
    return message[:1200]


def failure_diagnostic(error: BaseException, *, analysis: dict | None = None, payload: dict | None = None) -> dict:
    frames = traceback.extract_tb(error.__traceback__)[-12:]
    analysis = analysis or {}
    payload = payload or {}
    operation = str(payload.get("operation", "patch"))
    profile = str(payload.get("profile", "balanced"))
    return {
        "kind": type(error).__name__[:80],
        "technical_message": diagnostic_error(error, identifiers=tuple(
            value for value in (analysis.get("filename"), analysis.get("package_name"), payload.get("clone_package_name"))
            if isinstance(value, str) and value
        ), translate=False),
        "message": diagnostic_error(error, identifiers=tuple(
            value for value in (analysis.get("filename"), analysis.get("package_name"), payload.get("clone_package_name"))
            if isinstance(value, str) and value
        )),
        "operation": operation if operation in {"patch", "convert", "clone"} else "unknown",
        "profile": profile if profile in {"safe", "balanced", "deep"} else "unknown",
        "frames": [f"{Path(frame.filename).name}:{frame.lineno} · {frame.name[:80]}" for frame in frames],
    }


def diagnostic_report(job: Path | None, include_identifiers: bool = False) -> str:
    lines = [
        "APK Cleaner Studio · Hata raporu", "",
        f"Sürüm: {VERSION} ({RELEASE_CHANNEL})",
        f"Platform: {'Android' if ANDROID_RUNTIME else 'Windows / Termux'}",
        "Not: Ham araç günlüğü, imzalama bilgileri ve yerel dosya yolları eklenmez.",
    ]
    if job is not None:
        state = read_json(job / "state.json")
        analysis = read_json(job / "analysis.json")
        details = read_json(job / "diagnostic.json")
        lines.extend(["", "İşlem", f"Durum: {state.get('status', 'bilinmiyor')}"])
        if include_identifiers:
            lines.append(f"Dosya adı: {str(analysis.get('filename') or 'bilinmiyor')[:160]}")
            lines.append(f"Paket adı: {str(analysis.get('package_name') or 'bilinmiyor')[:160]}")
        if details:
            operations = {"patch": "Yama", "convert": "Dönüştürme / iyileştirme", "clone": "Klonlama"}
            profiles = {"safe": "Güvenli (safe)", "balanced": "Dengeli (balanced)", "deep": "Derin / Gelişmiş (deep)"}
            if "operation" in details:
                lines.append(f"İşlem türü: {operations.get(details['operation'], 'bilinmiyor')}")
            if "profile" in details:
                lines.append(f"Temizlik profili: {profiles.get(details['profile'], 'bilinmiyor')}")
            kinds = {"KeyError": "Eksik kayıt", "RuntimeError": "İşlem hatası", "ValueError": "Geçersiz işlem verisi",
                     "OSError": "Dosya veya sistem hatası", "FileNotFoundError": "Eksik dosya", "PermissionError": "Erişim izni hatası",
                     "MemoryError": "Yetersiz bellek", "TimeoutError": "Zaman aşımı", "BadZipFile": "Bozuk paket arşivi"}
            lines.extend([f"Hata türü: {kinds.get(details.get('kind'), 'İşlem hatası')}",
                          f"Açıklama: {details.get('message', 'bilinmiyor')}"])
            frames = details.get("frames")
            if isinstance(frames, list) and frames:
                lines.extend(["Çağrı konumu:", *(f"  {frame}" for frame in frames[:12] if isinstance(frame, str))])
        elif state.get("status") == "error":
            lines.append("Ayrıntılı kayıt bu işlem için bulunmuyor; eski sürümde oluşturulmuş olabilir.")
    native = DATA_ROOT / "diagnostic-native.txt"
    if ANDROID_RUNTIME and native.is_file():
        # This file contains only our own event code and class/method frames;
        # never include Android logcat or arbitrary exception messages.
        lines.extend(["", "Android uygulama olayı", native.read_text(encoding="utf-8", errors="replace")[:3000].strip()])
    if job is None and not (ANDROID_RUNTIME and native.is_file()):
        lines.extend(["", "Kaydedilmiş bir hata bulunamadı."])
    return "\n".join(lines).strip() + "\n"


def trusted_public_hostname(hostname: str) -> bool:
    """Accept a generic Keenetic reverse-proxy hostname without storing a private URL."""
    value = str(hostname or "").strip().lower().rstrip(".")
    return bool(value) and any(value.endswith(suffix) and value != suffix[1:] for suffix in TRUSTED_PUBLIC_SUFFIXES)


def trusted_proxy_request(peer_address: str, headers) -> bool:
    """Trust forwarding headers only from a private peer targeting our known proxy suffix."""
    try:
        peer = ipaddress.ip_address(peer_address)
    except ValueError:
        return False
    forwarded_host = str(headers.get("X-Forwarded-Host", "")).split(",", 1)[0].strip()
    hostname = (urlparse("//" + forwarded_host).hostname or "").lower()
    configured: set[str] = set()
    for value in os.environ.get("APK_CLEANER_TRUSTED_PROXY", "").split(","):
        try:
            configured.add(ipaddress.ip_address(value.strip()).compressed)
        except ValueError:
            continue
    peer_allowed = peer.is_loopback or peer.compressed in configured
    return bool(peer_allowed and trusted_public_hostname(hostname))


def observe_public_origin(peer_address: str, headers) -> str:
    """Remember a verified HTTPS reverse-proxy origin for optional LAN upgrades."""
    global _PUBLIC_HTTPS_ORIGIN
    try:
        peer = ipaddress.ip_address(peer_address)
    except ValueError:
        return ""
    if not (peer.is_private or peer.is_loopback):
        return ""
    forwarded_host = str(headers.get("X-Forwarded-Host", "")).split(",", 1)[0].strip()
    host_value = forwarded_host or str(headers.get("Host", "")).strip()
    hostname = (urlparse("//" + host_value).hostname or "").lower()
    if not trusted_public_hostname(hostname):
        return ""
    forwarded_proto = str(headers.get("X-Forwarded-Proto", "")).split(",", 1)[0].strip().lower()
    if forwarded_proto and forwarded_proto != "https":
        return ""
    origin = f"https://{hostname}/"
    with _PUBLIC_ORIGIN_LOCK:
        _PUBLIC_HTTPS_ORIGIN = origin
    return origin


def public_https_target(headers, raw_path: str) -> str:
    """Upgrade only the configured public reverse-proxy host from HTTP to HTTPS."""
    forwarded_proto = str(headers.get("X-Forwarded-Proto", "")).split(",", 1)[0].strip().lower()
    if forwarded_proto != "http":
        return ""
    forwarded_host = str(headers.get("X-Forwarded-Host", "")).split(",", 1)[0].strip()
    host_value = forwarded_host or str(headers.get("Host", "")).strip()
    hostname = (urlparse("//" + host_value).hostname or "").lower()
    if not trusted_public_hostname(hostname):
        return ""
    path = raw_path if raw_path.startswith("/") else "/"
    return f"https://{hostname}{path}"


def lan_https_target(peer_address: str, headers, raw_path: str) -> str:
    """Send this machine's local HTTP clients to its locally learned HTTPS origin."""
    if not _PUBLIC_HTTPS_ORIGIN:
        return ""
    try:
        peer = ipaddress.ip_address(peer_address)
    except ValueError:
        return ""
    if not (peer.is_private or peer.is_loopback):
        return ""
    forwarded_proto = str(headers.get("X-Forwarded-Proto", "")).split(",", 1)[0].strip().lower()
    if forwarded_proto == "https":
        return ""
    host_value = str(headers.get("Host", "")).strip()
    hostname = (urlparse("//" + host_value).hostname or "").lower()
    if trusted_public_hostname(hostname):
        return ""
    try:
        host_address = ipaddress.ip_address(hostname)
    except ValueError:
        return ""
    if not (host_address.is_private or host_address.is_loopback or host_address.is_link_local):
        return ""
    path = raw_path if raw_path.startswith("/") else "/"
    return f"{_PUBLIC_HTTPS_ORIGIN.rstrip('/')}{path}"


def preferred_browser_url(local_url: str) -> str:
    """Keep public configuration device-local while preferring HTTPS when available."""
    return _PUBLIC_HTTPS_ORIGIN or local_url


def direct_https_target(is_secure: bool, headers, raw_path: str) -> str:
    """Upgrade a direct local HTTP request on the mixed-protocol port to HTTPS."""
    if is_secure:
        return ""
    forwarded_proto = str(headers.get("X-Forwarded-Proto", "")).split(",", 1)[0].strip().lower()
    if forwarded_proto == "https":
        return ""
    host_value = str(headers.get("Host", "")).strip()
    if not host_value or not re.fullmatch(r"[A-Za-z0-9.\-:\[\]]+", host_value):
        return ""
    parsed = urlparse("//" + host_value)
    hostname = (parsed.hostname or "").lower()
    allowed = hostname == "localhost" or trusted_public_hostname(hostname)
    if not allowed:
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            return ""
        allowed = address.is_private or address.is_loopback or address.is_link_local
    if not allowed:
        return ""
    path = raw_path if raw_path.startswith("/") else "/"
    return f"https://{host_value}{path}"


def configure_console() -> None:
    """Configure UTF-8 output, a 110x30 window, title, and embedded icon."""
    global _ANSI_ENABLED, _ICON_HANDLES
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except (AttributeError, ValueError):
        pass
    if os.name != "nt":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleTitleW(f"APK Cleaner Studio · v{VERSION}")

        class Coord(ctypes.Structure):
            _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short)]

        class SmallRect(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_short),
                ("top", ctypes.c_short),
                ("right", ctypes.c_short),
                ("bottom", ctypes.c_short),
            ]

        kernel32.GetStdHandle.restype = ctypes.c_void_p
        output_handle = kernel32.GetStdHandle(-11)
        if output_handle:
            kernel32.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
            kernel32.SetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            console_mode = ctypes.c_uint()
            if kernel32.GetConsoleMode(output_handle, ctypes.byref(console_mode)):
                _ANSI_ENABLED = bool(kernel32.SetConsoleMode(output_handle, console_mode.value | 0x0004))
            kernel32.SetConsoleWindowInfo.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.POINTER(SmallRect)]
            kernel32.SetConsoleScreenBufferSize.argtypes = [ctypes.c_void_p, Coord]
            compact = SmallRect(0, 0, 1, 1)
            target = SmallRect(0, 0, CONSOLE_COLUMNS - 1, CONSOLE_ROWS - 1)
            kernel32.SetConsoleWindowInfo(output_handle, True, ctypes.byref(compact))
            kernel32.SetConsoleScreenBufferSize(output_handle, Coord(CONSOLE_COLUMNS, CONSOLE_ROWS))
            kernel32.SetConsoleWindowInfo(output_handle, True, ctypes.byref(target))

        if not getattr(sys, "frozen", False):
            return
        kernel32.GetConsoleWindow.restype = ctypes.c_void_p
        window = kernel32.GetConsoleWindow()
        if not window:
            return
        large_icon = ctypes.c_void_p()
        small_icon = ctypes.c_void_p()
        shell32 = ctypes.windll.shell32
        shell32.ExtractIconExW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_uint,
        ]
        shell32.ExtractIconExW.restype = ctypes.c_uint
        if shell32.ExtractIconExW(sys.executable, 0, ctypes.byref(large_icon), ctypes.byref(small_icon), 1):
            user32 = ctypes.windll.user32
            user32.SendMessageW(window, 0x0080, 1, large_icon.value)
            user32.SendMessageW(window, 0x0080, 0, small_icon.value)
            _ICON_HANDLES = (large_icon.value, small_icon.value)
    except (AttributeError, OSError):
        pass


def console_row(label: str = "", value: str = "") -> str:
    content = f"  {label:<17}{value}" if label else (f"  {value}" if value else "")
    return f"│{content[:CONSOLE_WIDTH - 2]:<{CONSOLE_WIDTH - 2}}│"


def console_spread_row(left: str, right: str) -> str:
    available = CONSOLE_WIDTH - 2
    gap = max(1, available - len(left) - len(right))
    content = f"{left}{' ' * gap}{right}"[:available]
    return f"│{content:<{available}}│"


def console_split_row(left: str = "", right: str = "") -> str:
    available = CONSOLE_WIDTH - 3
    left_width = available // 2
    right_width = available - left_width
    return f"│{left[:left_width]:<{left_width}}│{right[:right_width]:<{right_width}}│"


def is_termux_console() -> bool:
    prefix = os.environ.get("PREFIX", "")
    return bool(os.environ.get("TERMUX_VERSION") or "com.termux" in prefix)


def compact_console_width() -> int:
    return max(36, min(68, shutil.get_terminal_size(fallback=(52, 30)).columns))


def compact_console_rows(label: str, *values: str, width: int | None = None) -> list[str]:
    target = width or compact_console_width()
    inner = target - 4
    rows = [f"│  {label:<{inner}}│"]
    for value in values:
        wrapped = textwrap.wrap(value, width=inner, break_long_words=False, break_on_hyphens=False) or [""]
        rows.extend(f"│  {line:<{inner}}│" for line in wrapped)
    return rows


def print_compact_startup_panel(url: str, network_url: str | None) -> None:
    width = compact_console_width()
    inner = width - 2
    rule = "━" * inner

    def rows(label: str, *values: str) -> list[str]:
        output = [f" {label}"[:width]]
        for value in values:
            wrapped = textwrap.wrap(value, width=inner - 2, break_long_words=False, break_on_hyphens=False) or [""]
            output.extend(f"   {line}"[:width] for line in wrapped)
        return output

    lines = [
        "",
        " APK CLEANER STUDIO",
        f" LOCAL SESSION  /  v{VERSION}",
        f" {rule}",
        " ●  YEREL MOTOR HAZIR",
        "",
        *rows("YEREL ARAYÜZ", url),
        *rows("YEREL AĞ ERİŞİMİ", network_url or "Yerel ağ adresi algılanamadı."),
        "",
        f" {rule}",
        *rows("İŞ AKIŞI", "1  Paketi seç", "2  İşlemi yapılandır", "3  Yerel motoru çalıştır", "4  Çıktıyı indir"),
        "",
        *rows("GİZLİLİK", "Paketler yalnızca bu cihazda işlenir."),
        f" {rule}",
        " ✓  OTURUM HAZIR  /  Ctrl+C ile güvenli kapatma"[:width],
    ]
    print("\n".join(colorize_console_line(line) for line in lines), flush=True)


def local_network_ip() -> str | None:
    candidates: list[str] = []
    try:
        candidates.extend(item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            candidates.insert(0, probe.getsockname()[0])
    except OSError:
        pass
    for candidate in candidates:
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if address.version == 4 and address.is_private and not address.is_loopback and not address.is_link_local:
            return candidate
    return None


def colorize_console_line(line: str) -> str:
    if not _ANSI_ENABLED or os.environ.get("NO_COLOR") is not None:
        return line
    reset = "\033[0m"
    if line.strip() and set(line.strip()) <= {"━", "─"}:
        return f"\033[2;38;2;91;108;102m{line}{reset}"
    styles = {
        "APK CLEANER STUDIO": "\033[1;38;2;217;255;67m",
        "●  YEREL MOTOR HAZIR": "\033[1;38;2;72;213;168m",
        "✓  OTURUM HAZIR": "\033[1;38;2;72;213;168m",
        "LOCAL SESSION": "\033[2;38;2;152;167;161m",
        f"v{VERSION}": "\033[2;38;2;152;167;161m",
        "ENGINE": "\033[1;38;2;207;218;213m",
        "YEREL ARAYÜZ": "\033[1;38;2;152;167;161m",
        "YEREL AĞ ERİŞİMİ": "\033[1;38;2;152;167;161m",
        "İŞ AKIŞI": "\033[1;38;2;152;167;161m",
        "GİZLİLİK": "\033[1;38;2;152;167;161m",
        "KAPATMA": "\033[1;38;2;152;167;161m",
        "01": "\033[1;38;2;217;255;67m",
        "02": "\033[1;38;2;217;255;67m",
        "03": "\033[1;38;2;217;255;67m",
        "04": "\033[1;38;2;217;255;67m",
    }
    tokens = sorted(styles, key=len, reverse=True)
    pattern = re.compile(r"https?://[^\s│]+|" + "|".join(re.escape(token) for token in tokens))

    def paint(match: re.Match) -> str:
        text = match.group(0)
        color = "\033[1;38;2;104;195;255m" if text.startswith(("http://", "https://")) else styles[text]
        return f"{color}{text}{reset}"

    return pattern.sub(paint, line)


def print_startup_panel(url: str, browser_will_open: bool, network_url: str | None = None) -> None:
    if is_termux_console():
        print_compact_startup_panel(url, network_url)
        return
    rule = "━" * (CONSOLE_WIDTH - 4)
    browser_status = (
        "✓  OTURUM HAZIR  ·  Tarayıcı açılıyor; arayüz birkaç saniye içinde kullanılabilir."
        if browser_will_open
        else "✓  OTURUM HAZIR  ·  Web arayüzü bağlantı üzerinden kullanılabilir."
    )
    network = network_url or "Yerel ağ adresi algılanamadı."
    lines = [
        "",
        "APK CLEANER STUDIO",
        f"LOCAL SESSION  /  v{VERSION}  /  ENGINE {ENGINE_VERSION}",
        rule,
        "●  YEREL MOTOR HAZIR",
        "Yerel Android paket işleme ve dönüştürme merkezi",
        "",
        "01  YEREL ARAYÜZ",
        f"    {url}",
        "",
        "02  YEREL AĞ ERİŞİMİ",
        f"    {network}",
        "    Güvenlik duvarı sorarsa yalnızca “Özel ağlar” erişimine izin ver.",
        "",
        rule,
        "İŞ AKIŞI",
        "01 Paketi seç  ───  02 Yapılandır  ───  03 İşlemi uygula  ───  04 Çıktıyı indir",
        rule,
        browser_status,
        "GİZLİLİK  /  Paketler yalnızca bu cihazda işlenir.",
        "KAPATMA   /  Ctrl+C veya pencerenin kapatma düğmesi.",
    ]
    print("\n".join(PANEL_INDENT + colorize_console_line(line[:CONSOLE_WIDTH]) for line in lines), flush=True)


def print_startup_error(port: int, error: OSError) -> None:
    occupied = getattr(error, "winerror", None) == 10048 or getattr(error, "errno", None) in {48, 98}
    reason = f"{port} numaralı bağlantı noktası başka bir program tarafından kullanılıyor." if occupied else public_error(error)
    if is_termux_console():
        width = compact_console_width()
        rule = "━" * (width - 2)

        def mobile_rows(label: str, value: str) -> list[str]:
            wrapped = textwrap.wrap(value, width=width - 4, break_long_words=False, break_on_hyphens=False) or [""]
            return [f" {label}", *(f"   {line}" for line in wrapped)]

        lines = [
            "",
            " APK CLEANER STUDIO  ·  BAŞLATILAMADI",
            f" {rule}",
            *mobile_rows("NEDEN", reason),
            "",
            *mobile_rows("ÇÖZÜM", "Çalışan eski oturum kapatıldıktan sonra yeniden dene."),
            f" {rule}",
        ]
        print("\n".join(colorize_console_line(line[:width]) for line in lines), flush=True)
        return
    border = "─" * (CONSOLE_WIDTH - 2)
    print("\n".join(PANEL_INDENT + line for line in [
        f"╭{border}╮",
        console_row("BAŞLATILAMADI", "APK Cleaner Studio açılamadı."),
        console_row("NEDEN", reason),
        console_row("ÖNERİ", "Açık olan eski sürümü kapatıp yeniden dene."),
        f"╰{border}╯",
    ]), flush=True)


def _shutdown_windows_runtime() -> None:
    """Finish owned work and then leave no frozen child process behind."""
    try:
        timer = _BROWSER_TIMER
        if timer is not None:
            timer.cancel()
        terminate_active_tools()
        server = _ACTIVE_SERVER
        if server is not None:
            server.shutdown()
            server.server_close()
    finally:
        # A console CLOSE event gives applications only a short grace period.
        # PyInstaller one-file also has a supervising process, so an explicit
        # process exit is required after cleanup to prevent a child from
        # lingering in Task Manager.
        os._exit(0)


def install_shutdown_manager() -> None:
    """Ensure closing the console also stops the HTTP host and Java tools."""
    global _CONSOLE_CLOSE_HANDLER
    atexit.register(terminate_active_tools)
    if os.name != "nt":
        return
    try:
        handler_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

        @handler_type
        def console_handler(event: int) -> bool:
            # CTRL+C / CTRL+BREAK, pencereyi kapatma, oturum kapatma ve sistem
            # kapanışının tamamı aynı sahipli süreç temizliğinden geçer.
            if event not in {0, 1, 2, 5, 6}:
                return False
            _shutdown_windows_runtime()
            return True

        if ctypes.windll.kernel32.SetConsoleCtrlHandler(console_handler, True):
            _CONSOLE_CLOSE_HANDLER = console_handler
    except (AttributeError, OSError):
        pass


def request_local_https_trust(root_path: Path, allow_prompt: bool) -> bool:
    """Ask before extending the current Windows user's trusted root store."""
    if os.name != "nt":
        return False
    if root_is_trusted_on_windows(root_path):
        return True
    if not allow_prompt:
        return False
    message = (
        "APK Cleaner Studio, 127.0.0.1 ve yerel ağ adreslerini HTTPS ile açmak için bu bilgisayara özel "
        "bir yerel sertifika oluşturdu.\n\n"
        "Sertifikayı yalnızca mevcut Windows kullanıcısı için güvenilir yapmak ister misin? "
        "Özel anahtar bu cihazdan çıkmaz."
    )
    try:
        answer = ctypes.windll.user32.MessageBoxW(None, message, "APK Cleaner Studio · Yerel HTTPS", 0x24)
    except (AttributeError, OSError):
        return False
    return answer == 6 and trust_root_on_windows(root_path)


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = True
    # Varsayılan HTTPServer kuyruğu yalnızca 5 bağlantıdır. Tarayıcıların durum,
    # geçmiş ve varlık isteklerini aynı anda açtığı yerel ağ kullanımında kısa
    # bağlantı darbelerini reddetmeden karşıla; çalışan iş parçacığı sayısını
    # değiştirmez, yalnızca kabul edilmeyi bekleyen soketlere alan sağlar.
    request_queue_size = 128

    def __init__(self, server_address, handler_class, tls_context: ssl.SSLContext):
        self.tls_context = tls_context
        super().__init__(server_address, handler_class)

    def get_request(self):
        connection, address = self.socket.accept()
        connection.settimeout(10)
        try:
            first = connection.recv(1, socket.MSG_PEEK)
            if first and first[0] == 0x16:
                connection = self.tls_context.wrap_socket(connection, server_side=True)
            connection.settimeout(None)
            return connection, address
        except Exception:
            connection.close()
            raise


def write_json(path: Path, payload: dict) -> None:
    # Windows, başka bir iş parçacığı hedef dosyayı okurken replace çağrısını
    # reddedebilir. Okuma ve atomik yazma aynı kısa erişim kilidini paylaşır.
    with _JSON_WRITE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.parent.chmod(0o700)
        except OSError:
            pass
        # Her yazar için ayrı bir geçici dosya kullan. Böylece başarısız ya da
        # yarıda kesilmiş bir yazım başka bir güncellemenin taslağına dokunmaz.
        temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                temp.chmod(0o600)
            except OSError:
                pass
            temp.replace(path)
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass


def read_json(path: Path, fallback: dict | None = None) -> dict:
    with _JSON_WRITE_LOCK:
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return fallback or {}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return fallback or {}


def cleanup_stale_jobs(root: Path = JOBS, max_age_seconds: int = JOB_RETENTION_SECONDS) -> int:
    """Remove expired temporary jobs without touching recent user outputs."""
    if not root.is_dir():
        return 0
    cutoff = time.time() - max_age_seconds
    removed = 0
    for candidate in root.iterdir():
        try:
            if candidate.is_symlink():
                continue
            if candidate.is_file() and candidate.name.startswith(".upload-"):
                if candidate.stat().st_mtime < cutoff:
                    candidate.unlink()
                    removed += 1
                continue
            if not candidate.is_dir() or not JOB_ID.fullmatch(candidate.name):
                continue
            timestamps = [candidate.stat().st_mtime]
            for state_file in (candidate / "state.json", candidate / "analysis.json"):
                if state_file.is_file():
                    timestamps.append(state_file.stat().st_mtime)
            if max(timestamps) < cutoff:
                shutil.rmtree(candidate)
                removed += 1
        except OSError:
            continue
    return removed


def ensure_job_capacity(owner_id: str, root: Path = JOBS) -> None:
    """Bound persistent work data so an unauthenticated LAN client cannot exhaust the disk."""
    cleanup_stale_jobs(root)
    directories = [path for path in root.iterdir() if path.is_dir() and JOB_ID.fullmatch(path.name)] if root.is_dir() else []
    if len(directories) >= MAX_JOB_DIRECTORIES:
        raise ValueError("Yerel işlem alanı dolu. Eski işlemleri silip yeniden dene.")
    owner_jobs = 0
    total_size = 0
    for job in directories:
        if read_json(job / "analysis.json").get("owner_id") == owner_id:
            owner_jobs += 1
        for item in job.rglob("*"):
            try:
                if item.is_file():
                    total_size += item.stat().st_size
            except OSError:
                continue
            if total_size >= MAX_JOB_STORAGE_BYTES:
                raise ValueError("Yerel işlem alanı güvenli depolama sınırına ulaştı.")
    if owner_jobs >= MAX_OWNER_JOBS:
        raise ValueError("Bu cihaz için işlem sınırına ulaşıldı. Eski işlemleri silip yeniden dene.")


def _client_description(headers) -> str:
    user_agent = headers.get("User-Agent", "")
    brands = headers.get("Sec-CH-UA", "")
    platform_hint = headers.get("Sec-CH-UA-Platform", "").strip('"')
    lowered = user_agent.lower()
    platform = platform_hint or (
        "Android" if "android" in lowered else
        "iPhone" if "iphone" in lowered else
        "iPad" if "ipad" in lowered else
        "Windows" if "windows" in lowered else
        "macOS" if "macintosh" in lowered else
        "Linux" if "linux" in lowered else
        "Bilinmeyen cihaz"
    )
    browser_source = f"{brands} {user_agent}".lower()
    browser = (
        "Brave" if "brave" in browser_source else
        "Microsoft Edge" if any(token in lowered for token in ("edg/", "edga/", "edgios/")) else
        "Opera" if any(token in lowered for token in ("opr/", "opera")) else
        "Samsung Internet" if "samsungbrowser" in lowered else
        "Firefox" if any(token in lowered for token in ("firefox", "fxios")) else
        "Google Chrome" if any(token in lowered for token in ("chrome", "crios")) else
        "Safari" if "safari" in lowered else
        "Tarayıcı"
    )
    return f"{platform} · {browser}"


def _reported_browser(value: str) -> str:
    supported = {
        "brave": "Brave",
        "microsoft edge": "Microsoft Edge",
        "opera": "Opera",
        "samsung internet": "Samsung Internet",
        "firefox": "Firefox",
        "google chrome": "Google Chrome",
        "safari": "Safari",
    }
    return supported.get(_safe_device_text(value, 32).lower(), "")


def client_identity(address: str, headers, supplied_id: str | None = None) -> str:
    try:
        if ipaddress.ip_address(address).is_loopback:
            # Every 127.0.0.1/::1 request belongs to this computer. Browsers
            # keep HTTP and HTTPS storage separately and the early TLS probe
            # has no JavaScript header yet, so browser IDs must not split the
            # host into several apparent devices.
            host = _safe_device_text(socket.gethostname(), 80).casefold() or "localhost"
            return hashlib.sha256(f"local-host\0{host}".encode("utf-8")).hexdigest()[:24]
    except ValueError:
        pass
    cookie_id = ""
    try:
        cookies = SimpleCookie()
        cookies.load(headers.get("Cookie", ""))
        cookie_id = cookies[CLIENT_COOKIE_NAME].value if CLIENT_COOKIE_NAME in cookies else ""
    except (CookieError, KeyError):
        cookie_id = ""
    raw_id = supplied_id or headers.get("X-Client-ID", "") or cookie_id
    if re.fullmatch(r"[A-Za-z0-9._:-]{8,80}", raw_id):
        # Treat the browser value as one factor, not a portable bearer token.
        # A captured LAN header must not grant job access from another address.
        seed = f"client\0{address}\0{raw_id}"
    else:
        seed = f"fallback\0{address}\0{_client_description(headers)}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def _parsed_ip(value: str) -> str:
    candidate = str(value or "").strip().strip('"')
    if candidate.lower().startswith("for="):
        candidate = candidate[4:].strip().strip('"')
    if candidate.startswith("[") and "]" in candidate:
        candidate = candidate[1:candidate.index("]")]
    elif candidate.count(":") == 1 and candidate.rsplit(":", 1)[1].isdigit():
        candidate = candidate.rsplit(":", 1)[0]
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return ""
    if address.is_unspecified or address.is_multicast or address.is_loopback:
        return ""
    return address.compressed


def effective_client_address(peer_address: str, headers) -> str:
    """Honor proxy client-IP headers only when the immediate peer is a trusted local router/proxy."""
    try:
        peer = ipaddress.ip_address(peer_address)
    except ValueError:
        return peer_address
    if not (peer.is_private or peer.is_loopback) or not trusted_proxy_request(peer_address, headers):
        return peer.compressed

    forwarded_for = [_parsed_ip(value) for value in str(headers.get("X-Forwarded-For", "")).split(",")]
    forwarded_for = [value for value in forwarded_for if value]
    if forwarded_for:
        # Keenetic may append the actual address to a client-supplied chain. Work from
        # right to left and prefer the nearest public hop so a forged leftmost value wins nothing.
        for value in reversed(forwarded_for):
            if not ipaddress.ip_address(value).is_private:
                return value
        return forwarded_for[0]

    real_ip = _parsed_ip(headers.get("X-Real-IP", ""))
    if real_ip:
        return real_ip
    for header in ("X-Keenetic-Client-IP", "CF-Connecting-IP", "True-Client-IP", "X-Client-IP"):
        candidate = _parsed_ip(headers.get(header, ""))
        if candidate:
            return candidate
    for part in str(headers.get("Forwarded", "")).split(","):
        match = re.search(r"(?:^|;)\s*for=([^;]+)", part, re.IGNORECASE)
        candidate = _parsed_ip(match.group(1)) if match else ""
        if candidate:
            return candidate
    return peer.compressed


def _reported_public_ip(value: str) -> str:
    candidate = _parsed_ip(value)
    if not candidate:
        return ""
    address = ipaddress.ip_address(candidate)
    return candidate if address.version == 4 and address.is_global else ""


def _safe_device_text(value, limit: int = 80) -> str:
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or "")).strip()[:limit]


def _header_device_model(headers) -> str:
    value = _safe_device_text(headers.get("Sec-CH-UA-Model", ""))
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1].strip()
    return "" if value.lower() in {"", "unknown", "null"} else value


def _resolve_lan_hostname(client_id: str, address: str) -> None:
    try:
        hostname = _safe_device_text(socket.gethostbyaddr(address)[0].split(".", 1)[0], 48)
        if not hostname or hostname == address:
            return
        with _CLIENTS_LOCK:
            if client_id in _CLIENTS:
                _CLIENTS[client_id]["hostname"] = hostname
    except (OSError, UnicodeError):
        pass


def record_client(address: str, headers, now: float | None = None, details: dict | None = None) -> list[dict]:
    """Keep an in-memory LAN session list; only friendly labels and catalog updates persist."""
    timestamp = now or time.time()
    description = _client_description(headers)
    details = details or {}
    key = client_identity(address, headers, _safe_device_text(details.get("client_id")))
    try:
        local = ipaddress.ip_address(address).is_loopback
    except ValueError:
        local = False
    with _CLIENTS_LOCK:
        stale = [key for key, item in _CLIENTS.items() if key not in _BLOCKED_CLIENTS and timestamp - item["last_seen"] > CLIENT_RETENTION_SECONDS]
        for stale_key in stale:
            _CLIENTS.pop(stale_key, None)
        item = _CLIENTS.get(key)
        if item:
            item["last_seen"] = timestamp
            item["requests"] += 1
            item["address"] = address
            item["description"] = description
        else:
            _CLIENTS[key] = {
                "id": key,
                "address": address,
                "description": description,
                "first_seen": timestamp,
                "last_seen": timestamp,
                "requests": 1,
                "local": local,
            }
            if local:
                _CLIENTS[key]["hostname"] = _safe_device_text(socket.gethostname(), 48)
            elif ipaddress.ip_address(address).is_private:
                threading.Thread(target=_resolve_lan_hostname, args=(key, address), name="lan-hostname", daemon=True).start()
        model = _safe_device_text(details.get("model")) or _header_device_model(headers)
        if model:
            _CLIENTS[key]["model"] = model
        reported_browser = _reported_browser(details.get("browser", ""))
        if reported_browser:
            _CLIENTS[key]["reported_browser"] = reported_browser
        reported_public_ip = _reported_public_ip(details.get("public_ip", ""))
        if reported_public_ip and not local:
            _CLIENTS[key]["reported_public_ip"] = reported_public_ip
        if len(_CLIENTS) > CLIENT_LIMIT:
            for old_key, _item in sorted(_CLIENTS.items(), key=lambda pair: pair[1]["last_seen"])[:-CLIENT_LIMIT]:
                _CLIENTS.pop(old_key, None)
        requester = key
        rows = []
        for value in sorted(_CLIENTS.values(), key=lambda value: value["last_seen"], reverse=True):
            row = dict(value)
            row["address"] = row.get("reported_public_ip") or row["address"]
            platform = row["description"].split(" · ", 1)[0]
            if row.get("reported_browser"):
                row["description"] = f"{platform} · {row['reported_browser']}"
            resolved_name = _DEVICE_CATALOG.resolve(row.get("model", ""))
            row["model_name"] = resolved_name
            # A reverse proxy/router hostname describes the gateway, not the
            # public client behind it. Keep an explicit user label, but ignore
            # automatically resolved LAN hostnames once a public IP is known.
            automatic_hostname = None if row.get("reported_public_ip") else row.get("hostname")
            hidden_model_name = f"{platform} · cihaz adı alınamadı"
            generic_name = "Bu bilgisayar" if row["local"] else (hidden_model_name if platform in {"Android", "iPhone", "iPad"} else f"{platform} cihazı")
            row["display_name"] = _CLIENT_LABELS.get(row["id"]) or resolved_name or automatic_hostname or generic_name
            row["blocked"] = row["id"] in _BLOCKED_CLIENTS
            row["online"] = not row["blocked"] and timestamp - row["last_seen"] <= CLIENT_ONLINE_SECONDS
            row["can_rename"] = not row["blocked"] and (local or row["id"] == requester)
            row["can_manage"] = bool(local and not row["local"])
            rows.append(row)
        return rows if local else [row for row in rows if row["id"] == requester]


def set_client_label(target_id: str, label: str, requester_id: str, requester_is_local: bool) -> str:
    if not re.fullmatch(r"[a-f0-9]{24}", target_id):
        raise ValueError("Geçersiz cihaz kimliği.")
    if not requester_is_local and target_id != requester_id:
        raise PermissionError("Yalnızca kendi cihazını adlandırabilirsin.")
    cleaned = _safe_device_text(label, 48)
    if len(cleaned) < 2:
        raise ValueError("Cihaz adı en az 2 karakter olmalıdır.")
    with _CLIENTS_LOCK:
        _CLIENT_LABELS[target_id] = cleaned
        write_json(CLIENT_LABELS_PATH, _CLIENT_LABELS)
    return cleaned


def manage_client(target_id: str, action: str, requester_is_local: bool) -> None:
    if not requester_is_local:
        raise PermissionError("Cihaz yönetimi yalnızca ana bilgisayardan yapılabilir.")
    if not re.fullmatch(r"[a-f0-9]{24}", target_id):
        raise ValueError("Geçersiz cihaz kimliği.")
    if action not in {"block", "unblock", "deny", "delete"}:
        raise ValueError("Geçersiz cihaz yönetimi işlemi.")
    with _CLIENTS_LOCK:
        target = _CLIENTS.get(target_id)
        if target and target.get("local"):
            raise ValueError("Ana bilgisayar oturumu yönetim listesinden engellenemez.")
        if action == "block":
            if not target:
                raise ValueError("Cihaz oturumu bulunamadı.")
            _BLOCKED_CLIENTS.add(target_id)
            target.pop("access_requested_at", None)
        elif action == "unblock":
            _BLOCKED_CLIENTS.discard(target_id)
            if target:
                target.pop("access_requested_at", None)
        elif action == "deny":
            if target_id not in _BLOCKED_CLIENTS or not target:
                raise ValueError("Bekleyen erişim isteği bulunamadı.")
            target.pop("access_requested_at", None)
        else:
            _CLIENTS.pop(target_id, None)
            _BLOCKED_CLIENTS.discard(target_id)
        _persist_blocked_clients_locked()


def _persist_blocked_clients_locked() -> None:
    records = []
    for client_id in sorted(_BLOCKED_CLIENTS):
        item = _CLIENTS.get(client_id, {})
        record = {
            key: item[key]
            for key in (
                "id", "address", "description", "first_seen", "last_seen", "requests",
                "model", "hostname", "reported_public_ip", "reported_browser", "access_requested_at",
            )
            if key in item
        }
        record["id"] = client_id
        records.append(record)
    write_json(CLIENT_BLOCKLIST_PATH, {"clients": records})


def request_client_access(address: str, headers) -> None:
    client_id = client_identity(address, headers)
    now = time.time()
    with _CLIENTS_LOCK:
        if client_id not in _BLOCKED_CLIENTS:
            raise ValueError("Bu cihaz için etkin bir erişim engeli bulunmuyor.")
        item = _CLIENTS.setdefault(client_id, {
            "id": client_id,
            "address": address,
            "description": _client_description(headers),
            "first_seen": now,
            "last_seen": now,
            "requests": 0,
            "local": False,
        })
        item["address"] = address
        item["description"] = _client_description(headers)
        item["last_seen"] = now
        item["requests"] = int(item.get("requests", 0)) + 1
        item["access_requested_at"] = now
        _persist_blocked_clients_locked()


def record_blocked_client_details(address: str, headers, details: dict) -> None:
    """Refresh a blocked session's safe device metadata without exposing the session list."""
    client_id = client_identity(address, headers, _safe_device_text(details.get("client_id")))
    with _CLIENTS_LOCK:
        if client_id not in _BLOCKED_CLIENTS:
            raise ValueError("Bu cihaz için etkin bir erişim engeli bulunmuyor.")
    record_client(address, headers, details=details)
    with _CLIENTS_LOCK:
        _persist_blocked_clients_locked()


def job_visible_to(job: Path, requester_id: str, requester_is_local: bool) -> bool:
    if requester_is_local:
        return True
    analysis = read_json(job / "analysis.json")
    return bool(analysis.get("owner_id") and analysis.get("owner_id") == requester_id)


def list_job_history(requester_id: str, requester_is_local: bool, limit: int = 20) -> list[dict]:
    rows: list[dict] = []
    if not JOBS.is_dir():
        return rows
    for job in JOBS.iterdir():
        if not job.is_dir() or not JOB_ID.fullmatch(job.name) or not job_visible_to(job, requester_id, requester_is_local):
            continue
        analysis = read_json(job / "analysis.json")
        state = read_json(job / "state.json")
        if not analysis:
            continue
        result = read_json(job / "output" / "report.json")
        source_path = analysis.get("source_path")
        source = job / source_path if source_path else Path("missing")
        created_at = float(analysis.get("created_at") or (source.stat().st_mtime if source.is_file() else job.stat().st_mtime))
        updated_at = (job / "state.json").stat().st_mtime if (job / "state.json").is_file() else created_at
        output_name = result.get("output")
        output = job / "output" / output_name if output_name else Path("missing")
        rows.append({
            "job_id": job.name,
            "filename": analysis.get("filename", "paket.apk"),
            "source_type": analysis.get("source_type", "apk"),
            "size": analysis.get("size", 0),
            "status": state.get("status", "unknown"),
            "created_at": created_at,
            "updated_at": updated_at,
            "mode": result.get("mode"),
            "operation": result.get("operation"),
            "duration_seconds": result.get("duration_seconds"),
            "can_reuse": source.is_file(),
            "can_delete": state.get("status") not in {"analyzing", "working"},
            "has_report": (job / "output" / "report.txt").is_file(),
            "has_output": output.is_file(),
            "output_filename": output.name if output.is_file() else "",
        })
    rows.sort(key=lambda row: row["updated_at"], reverse=True)
    return rows[:limit]


def list_job_storage(requester_id: str, requester_is_local: bool) -> dict:
    """Summarize only visible, app-owned job files; never follow symlinks."""
    rows = []
    totals = {"source": 0, "output": 0, "working": 0}
    if not JOBS.is_dir():
        return {"jobs": rows, "totals": totals}
    with _ACTIVE_JOBS_LOCK:
        busy = _ACTIVE_JOBS | _SCANNING_JOBS
    for job in JOBS.iterdir():
        if job.is_symlink() or not job.is_dir() or not JOB_ID.fullmatch(job.name):
            continue
        if not job_visible_to(job, requester_id, requester_is_local):
            continue
        analysis = read_json(job / "analysis.json")
        if not analysis:
            continue
        source_name = analysis.get("source_path")
        source_name = source_name if isinstance(source_name, str) and Path(source_name).name == source_name else None
        sizes = {"source": 0, "output": 0, "working": 0}
        for item in job.rglob("*"):
            try:
                if item.is_symlink() or not item.is_file():
                    continue
                relative = item.relative_to(job)
                category = "output" if relative.parts[0] == "output" else "source" if relative.as_posix() == source_name else "working"
                sizes[category] += item.stat().st_size
            except OSError:
                continue
        for category, amount in sizes.items():
            totals[category] += amount
        state = read_json(job / "state.json")
        rows.append({"job_id": job.name, "filename": analysis.get("filename", "paket.apk"),
                     "sizes": sizes, "can_delete": job.name not in busy and state.get("status") not in {"analyzing", "working"}})
    rows.sort(key=lambda row: sum(row["sizes"].values()), reverse=True)
    return {"jobs": rows, "totals": totals}


def clone_job_for_reuse(job_id: str, requester_id: str, requester_is_local: bool) -> tuple[str, dict]:
    """Create a fresh ready job from history instead of reopening completed state/output."""
    if not JOB_ID.fullmatch(job_id):
        raise ValueError("Geçersiz iş kimliği.")
    original_job = JOBS / job_id
    if not original_job.is_dir():
        raise FileNotFoundError("İşlem kaydı bulunamadı.")
    if not job_visible_to(original_job, requester_id, requester_is_local):
        raise PermissionError("Bu işlem geçmişi bu cihaza ait değil.")
    analysis = read_json(original_job / "analysis.json")
    source_path = analysis.get("source_path")
    source = original_job / source_path if source_path else Path("missing")
    if not analysis or not source.is_file():
        raise FileNotFoundError("İşin kaynak paketi artık bulunmuyor.")

    new_job_id = uuid.uuid4().hex
    new_job = JOBS / new_job_id
    new_job.mkdir(parents=True, exist_ok=False)
    new_job.chmod(0o700)
    try:
        # Geçmiş çıktısını değil, kullanıcının yüklediği değişmemiş kaynak
        # paketini kopyala. Böylece önceki yama ve tamamlanmış state yeni
        # çalışmayı etkileyemez.
        cloned_source = new_job / source.name
        # copy2 eski Android dosyasının izin/zaman metadatasını da
        # taşıyordu. Bazı cihazlarda iş motorunun salt okunur bıraktığı
        # kaynak bu nedenle yeni işte PermissionError üretiyordu. Yalnızca
        # içeriği kopyala ve yeni işe ait, yazılabilir özel izinleri kur.
        try:
            shutil.copyfile(source, cloned_source)
        except PermissionError:
            source.chmod(source.stat().st_mode | 0o600)
            shutil.copyfile(source, cloned_source)
        cloned_source.chmod(0o600)
        cloned_analysis = dict(analysis)
        cloned_analysis.update({
            "source_path": cloned_source.name,
            "prepared_path": None if analysis.get("split_merged") else cloned_source.name,
            "owner_id": requester_id,
            "created_at": time.time(),
        })
        # Başlangıç çağrısı onayları özgün işin DEX konumlarına aittir.
        # Yeni işte kullanıcı yeniden karşılaştırma yapmadan taşınmamalıdır.
        cloned_analysis.pop("approved_message_targets", None)
        write_json(new_job / "analysis.json", cloned_analysis)
        write_json(new_job / "state.json", {
            "status": "ready", "message": "Geçmiş kaynak yeniden işlemeye hazır",
            "progress": 100, "filename": cloned_analysis.get("filename", source.name),
        })
    except Exception:
        shutil.rmtree(new_job, ignore_errors=True)
        raise
    return new_job_id, cloned_analysis


def delete_job_history(job_id: str, requester_id: str, requester_is_local: bool) -> None:
    if not JOB_ID.fullmatch(job_id):
        raise ValueError("Geçersiz işlem kimliği.")
    job = JOBS / job_id
    if job.is_symlink() or not job.is_dir():
        raise FileNotFoundError("İşlem kaydı bulunamadı.")
    if not job_visible_to(job, requester_id, requester_is_local):
        raise PermissionError("Bu işlem kaydını silme yetkin yok.")
    state = read_json(job / "state.json")
    if state.get("status") in {"analyzing", "working"}:
        raise ValueError("Devam eden işlem tamamlanmadan silinemez.")
    with _ACTIVE_JOBS_LOCK:
        if job_id in _SCANNING_JOBS:
            raise ValueError("Başlangıç çağrısı taraması tamamlanmadan işlem silinemez.")
        if job_id in _ACTIVE_JOBS:
            raise ValueError("Devam eden işlem tamamlanmadan silinemez.")
        shutil.rmtree(job)


class JobCancelled(RuntimeError):
    """Raised cooperatively when a user cancels an active APK operation."""


class JobProgressJournal:
    """Bounded engine events, retained between UI polls; not a raw tool log."""

    def __init__(self) -> None:
        self.started = time.monotonic()
        self.events: list[dict] = []
        self.sequence = 0

    def record(self, message: str, percent: int) -> list[dict]:
        message = str(message)[:500]
        percent = min(100, max(0, int(percent)))
        if not self.events or (self.events[-1]["message"], self.events[-1]["progress"]) != (message, percent):
            self.sequence += 1
            self.events.append({"id": self.sequence, "message": message, "progress": percent,
                                "elapsed_seconds": round(max(0, time.monotonic() - self.started), 1)})
            self.events = self.events[-120:]
        return list(self.events)


def cancel_clean_job(job_id: str, requester_id: str, requester_is_local: bool) -> bool:
    if not JOB_ID.fullmatch(job_id):
        raise ValueError("Geçersiz iş kimliği.")
    job = JOBS / job_id
    if not job.is_dir():
        raise FileNotFoundError("İşlem bulunamadı.")
    if not job_visible_to(job, requester_id, requester_is_local):
        raise PermissionError("Bu işlemi iptal etme yetkin yok.")
    with _ACTIVE_JOBS_LOCK:
        event = _JOB_CANCEL_EVENTS.get(job_id)
        thread_id = _JOB_THREADS.get(job_id)
        active = job_id in _ACTIVE_JOBS
        if event:
            event.set()
    if thread_id is not None:
        terminate_active_tools(thread_id)
    if active:
        current = read_json(job / "state.json")
        write_json(job / "state.json", {
            "status": "cancelling", "message": "İşlem güvenli biçimde durduruluyor",
            "progress": current.get("progress", 0), "filename": current.get("filename", "paket.apk"),
            "events": current.get("events", []),
        })
    return active


def _execute_clean_job(job_id: str, payload: dict) -> None:
    """Run a claimed APK job outside the HTTP request lifecycle."""
    job = JOBS / job_id
    analysis = read_json(job / "analysis.json")
    filename = analysis.get("filename", "paket.apk")
    last_stage = "İşlem seçenekleri denetleniyor"
    journal = JobProgressJournal()
    with _ACTIVE_JOBS_LOCK:
        cancel_event = _JOB_CANCEL_EVENTS.setdefault(job_id, threading.Event())
        _JOB_THREADS[job_id] = threading.get_ident()

    def progress(message: str, percent: int) -> None:
        nonlocal last_stage
        if cancel_event.is_set():
            raise JobCancelled("İşlem kullanıcı tarafından iptal edildi.")
        last_stage = message
        write_json(job / "state.json", {
            "status": "working", "message": message,
            "progress": min(99, max(0, int(percent))), "filename": filename,
            "events": journal.record(message, percent),
        })

    try:
        reset_tool_cancellation()
        mode = str(payload.get("profile", "balanced"))
        operation = str(payload.get("operation", "patch"))
        patch_ads = bool(payload.get("patch_ads", operation == "patch"))
        clone_package_name = payload.get("clone_package_name") if operation == "clone" else None
        if operation == "clone" and not isinstance(clone_package_name, str):
            raise ValueError("Klon için yeni paket adını gir.")
        strip_debug = bool(payload.get("strip_debug", False))
        normalize_dex = bool(payload.get("normalize_dex", False))
        restrict_store_updates = payload.get("restrict_store_updates", False)
        if not isinstance(restrict_store_updates, bool):
            raise ValueError("Play Store güncelleme seçeneği geçersiz.")
        optimize_apk = bool(payload.get("optimize_apk", False))
        deobfuscate_resources = bool(payload.get("deobfuscate_resources", False))
        normalize_resources = bool(payload.get("normalize_resources", False))
        message_targets = payload.get("message_targets") or []
        if not isinstance(message_targets, list) or len(message_targets) > 1000:
            raise ValueError("Uygulama içi mesaj seçimi geçersiz.")
        approved_message_targets = set(analysis.get("approved_message_targets") or [])
        if any(not isinstance(item, str) or item not in approved_message_targets for item in message_targets):
            raise ValueError("Başlangıç çağrısı seçimi güncel değil. Paketi yeniden tara.")
        split_selection = payload.get("split_selection")
        if operation not in {"patch", "convert", "clone"}:
            raise ValueError("Bilinmeyen işlem türü.")

        prepared_path = analysis.get("prepared_path")
        prepared = job / prepared_path if prepared_path else Path("missing")
        selected_split_rebuilt = False
        split_details: dict = {}
        if analysis.get("split_merged"):
            source_path = analysis.get("source_path")
            split_source = job / source_path if source_path else Path("missing")
            if not split_source.is_file():
                raise ValueError("Kaynak split paketi bulunamadı.")
            if split_selection is None:
                options = analysis.get("split_options") or {}
                split_selection = {
                    "abis": list(options.get("abis", [])),
                    "languages": [item.get("code") for item in options.get("languages", []) if item.get("code")],
                }
            prepared, selected_log = merge_split_package(
                split_source, job / "prepared-selected", progress, split_selection, details=split_details,
            )
            analysis["merge_log"] = selected_log[-100:]
            selected_split_rebuilt = True
        if not prepared.is_file():
            raise ValueError("Hazırlanan APK bulunamadı.")

        progress("Yerel işlem motoru hazırlanıyor", 4)
        original_source = job / analysis.get("source_path", prepared_path or "missing")
        result = process_apk(
            prepared,
            job / "output",
            mode,
            progress,
            patch_ads=patch_ads,
            strip_debug=strip_debug,
            normalize_dex=normalize_dex,
            restrict_store_updates=restrict_store_updates,
            optimize_apk=optimize_apk,
            deobfuscate_resources=deobfuscate_resources,
            normalize_resources=normalize_resources,
            source_name=filename,
            source_size_bytes=original_source.stat().st_size if original_source.is_file() else None,
            split_merged=bool(analysis.get("split_merged")),
            split_details=split_details,
            analysis_report=None if selected_split_rebuilt else {
                key: analysis[key]
                for key in (
                    "filename", "size", "sha256", "package_name", "app_icon", "suggested_clone_package_name", "dex", "dex_count", "detections",
                    "network_count", "manifest_hits", "layout_hits", "install_source_checks", "source_integrity_risk",
                    "message_ui_candidates", "message_ui_candidate_count", "requires_splits",
                    "suspicious_files", "toolchain", "warnings",
                )
                if key in analysis
            },
            message_targets=message_targets,
            clone_package_name=clone_package_name,
        )
        if cancel_event.is_set():
            raise JobCancelled("İşlem kullanıcı tarafından iptal edildi.")
        write_json(job / "state.json", {
            "status": "done", "message": "Çıktı APK hazır", "progress": 100,
            "filename": filename, "result": result,
            "events": journal.record("Çıktı APK hazır", 100),
        })
    except JobCancelled as exc:
        shutil.rmtree(job / "output", ignore_errors=True)
        shutil.rmtree(job / "prepared-selected", ignore_errors=True)
        write_json(job / "state.json", {
            "status": "cancelled", "message": str(exc), "progress": 0, "filename": filename,
            "events": journal.record("İşlem kullanıcı tarafından iptal edildi.", 0),
        })
    except Exception as exc:
        if cancel_event.is_set():
            shutil.rmtree(job / "output", ignore_errors=True)
            shutil.rmtree(job / "prepared-selected", ignore_errors=True)
            write_json(job / "state.json", {
                "status": "cancelled", "message": "İşlem kullanıcı tarafından iptal edildi.",
                "progress": 0, "filename": filename,
                "events": journal.record("İşlem kullanıcı tarafından iptal edildi.", 0),
            })
            return
        details = failure_diagnostic(exc, analysis=analysis, payload=payload)
        details["stage"] = diagnostic_error(RuntimeError(last_stage))
        try:
            write_json(job / "diagnostic.json", details)
        except OSError:
            pass  # Reporting must never mask the original job failure.
        write_json(job / "state.json", {
            "status": "error", "message": details["message"], "progress": 0, "filename": filename,
            "failure": {key: details[key] for key in ("message", "stage", "operation", "profile")},
            "events": journal.record(details["message"], 0),
        })
    finally:
        with _ACTIVE_JOBS_LOCK:
            _ACTIVE_JOBS.discard(job_id)
            _JOB_CANCEL_EVENTS.pop(job_id, None)
            _JOB_THREADS.pop(job_id, None)


def start_clean_job(job_id: str, payload: dict) -> tuple[str, dict | None]:
    """Claim once and return immediately so reverse-proxy timeouts cannot replay the engine."""
    if not JOB_ID.fullmatch(job_id):
        raise ValueError("Geçersiz iş kimliği.")
    job = JOBS / job_id
    analysis = read_json(job / "analysis.json")
    if not analysis:
        raise ValueError("İş analizi bulunamadı.")
    state = read_json(job / "state.json")
    with _ACTIVE_JOBS_LOCK:
        if _SCANNING_JOBS:
            raise ValueError("Başlangıç çağrısı taraması tamamlanana kadar bekle.")
        if job_id in _ACTIVE_JOBS:
            return "working", None
        if state.get("status") == "done":
            result = state.get("result") or read_json(job / "output" / "report.json")
            return "done", result or None
        _ACTIVE_JOBS.add(job_id)
        _JOB_CANCEL_EVENTS[job_id] = threading.Event()
        write_json(job / "state.json", {
            "status": "working", "message": "İşlem sıraya alındı", "progress": 2,
            "filename": analysis.get("filename", "paket.apk"),
        })
    try:
        threading.Thread(
            target=_execute_clean_job,
            args=(job_id, dict(payload)),
            name=f"apk-job-{job_id[:8]}",
            daemon=True,
        ).start()
    except Exception:
        with _ACTIVE_JOBS_LOCK:
            _ACTIVE_JOBS.discard(job_id)
            _JOB_CANCEL_EVENTS.pop(job_id, None)
        raise
    return "working", None


class StudioHandler(BaseHTTPRequestHandler):
    server_version = "APKCleanerStudio"
    sys_version = ""

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(30)

    def request_address(self) -> str:
        return effective_client_address(self.client_address[0], self.headers)

    def requester_is_local(self) -> bool:
        try:
            return ipaddress.ip_address(self.request_address()).is_loopback
        except ValueError:
            return False

    def trusted_local_proxy(self) -> bool:
        try:
            return trusted_proxy_request(self.client_address[0], self.headers)
        except (AttributeError, IndexError):
            return False

    def requester_id(self) -> str:
        return client_identity(self.request_address(), self.headers)

    def requester_is_blocked(self) -> bool:
        if self.requester_is_local():
            return False
        with _CLIENTS_LOCK:
            return self.requester_id() in _BLOCKED_CLIENTS

    def log_message(self, fmt: str, *args) -> None:
        try:
            status = int(args[0] if fmt.startswith("code") else args[1])
        except (IndexError, TypeError, ValueError):
            status = 0
        if status >= 400:
            print(f"  UYARI · HTTP {status} · {self.command} {self.path}", flush=True)

    def request_origin_allowed(self) -> bool:
        """Accept only this local/private host and same-origin browser mutations."""
        host_header = self.headers.get("Host", "")
        host = urlparse("//" + host_header).hostname
        if not host:
            return False
        if host.lower() != "localhost":
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                if not trusted_public_hostname(host) or not self.trusted_local_proxy():
                    return False
            else:
                if not (address.is_private or address.is_loopback or address.is_link_local):
                    return False
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"}:
            return False
        if parsed.netloc.lower() == host_header.lower():
            return True
        forwarded_host = str(self.headers.get("X-Forwarded-Host", "")).split(",", 1)[0].strip().lower()
        if self.trusted_local_proxy() and forwarded_host and parsed.netloc.lower() == forwarded_host:
            return True
        return False

    def security_headers(self, *, html: bool = False) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")
        if html:
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
                "connect-src 'self' https://api.ipify.org; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
            )

    def cors(self) -> None:
        self.send_header("Accept-CH", UA_CLIENT_HINTS)
        self.send_header("Permissions-Policy", "ch-ua-model=(self), ch-ua-platform-version=(self), ch-ua-high-entropy-values=(self)")
        origin = self.headers.get("Origin")
        if origin and self.request_origin_allowed():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Client-ID")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def redirect_secure_http(self) -> bool:
        # HTTP and HTTPS intentionally share the same port. LAN clients can
        # use HTTP without a certificate prompt; users who install the local
        # CA may choose HTTPS. Public reverse proxies keep their own scheme.
        return False

    def send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.security_headers()
        self.cors()
        self.end_headers()
        self.wfile.write(body)

    def send_diagnostic(self, report: str, download: bool) -> None:
        body = report.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if download:
            self.send_header("Content-Disposition", 'attachment; filename="apk-cleaner-hata-raporu.txt"')
        self.security_headers()
        self.cors()
        self.end_headers()
        self.wfile.write(body)

    def send_blocked_page(self) -> None:
        body = """<!doctype html><html lang=\"tr\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\"><meta name=\"color-scheme\" content=\"dark light\"><meta name=\"theme-color\" content=\"#07100d\"><title>Erişim engellendi · APK Cleaner Studio</title><style>*{box-sizing:border-box}html{font-family:system-ui,sans-serif;color-scheme:dark;background:#07100d;color:#eef5ef}body{min-height:100vh;min-height:100dvh;margin:0;display:grid;place-items:center;padding:max(20px,env(safe-area-inset-top)) max(20px,env(safe-area-inset-right)) max(20px,env(safe-area-inset-bottom)) max(20px,env(safe-area-inset-left));background:radial-gradient(circle at 50% 0,#10251d 0,#07100d 56%)}main{width:min(520px,100%);padding:clamp(28px,7vw,42px);border:1px solid #29463d;border-radius:24px;background:#0d1915;text-align:center;box-shadow:0 24px 80px #0008;overflow-wrap:anywhere}i{display:grid;place-items:center;width:58px;height:58px;margin:0 auto 20px;border-radius:18px;background:#251512;color:#ff7a61;font-size:28px;font-style:normal;font-weight:900}h1{margin:0 0 12px;font-size:clamp(26px,8vw,38px);line-height:1.12}p{margin:0;color:#a8b8b0;font-size:clamp(15px,4vw,17px);line-height:1.65}small{display:block;margin-top:18px;color:#63d9b2;font-size:clamp(13px,3.6vw,15px);line-height:1.55}form{margin-top:24px}button{width:100%;min-height:50px;border:1px solid #63d9b2;border-radius:14px;background:#63d9b2;color:#07100d;font:inherit;font-weight:850;cursor:pointer}@media(max-width:520px){body{place-items:stretch;align-content:center}main{border-radius:20px;padding:30px 22px}i{width:54px;height:54px;margin-bottom:18px}}@media(max-height:520px) and (orientation:landscape){body{padding:14px}main{padding:20px 28px}i{width:44px;height:44px;margin-bottom:10px;font-size:22px}h1{font-size:25px;margin-bottom:8px}small{margin-top:10px}form{margin-top:14px}}</style></head><body><main><i>!</i><h1>Erişim engellendi</h1><p>Bu cihazın APK Cleaner Studio arayüzüne erişimi ana makine tarafından engellendi.</p><small>Erişimin yeniden açılması için yöneticiye istek gönderebilirsin.</small><form method=\"post\" action=\"/api/access-request\"><button type=\"submit\">Yöneticiden erişim iste</button></form></main><script>(()=>{const identify=(async()=>{const d={model:\"\",platform:navigator.userAgentData?.platform||navigator.platform||\"\",mobile:Boolean(navigator.userAgentData?.mobile||/Android|iPhone|iPad|Mobile/i.test(navigator.userAgent)),browser:\"\"};try{if(navigator.userAgentData?.getHighEntropyValues){const v=await navigator.userAgentData.getHighEntropyValues([\"model\",\"platform\",\"platformVersion\",\"formFactors\"]);d.model=v.model||\"\";d.platform=v.platform||d.platform;d.mobile=Boolean(v.mobile??d.mobile);d.form_factors=Array.isArray(v.formFactors)?v.formFactors.slice(0,4):[]}}catch{}if(!d.model){const m=navigator.userAgent.match(/Android\\s[^;)]*;\\s*([^;)]+?)\\s+Build\\//i);if(m&&!/^(?:K|Mobile|Tablet|wv)$/i.test(m[1].trim()))d.model=m[1].trim()}try{if(await navigator.brave?.isBrave())d.browser=\"Brave\";else if(/Edg\\//.test(navigator.userAgent))d.browser=\"Microsoft Edge\";else if(/SamsungBrowser\\//.test(navigator.userAgent))d.browser=\"Samsung Internet\";else if(/Chrome\\//.test(navigator.userAgent))d.browser=\"Google Chrome\"}catch{}try{await fetch(\"/api/client/identify\",{method:\"POST\",headers:{\"Content-Type\":\"application/json\"},body:JSON.stringify(d)})}catch{}})();const f=document.querySelector(\"form\");f?.addEventListener(\"submit\",async e=>{e.preventDefault();await identify;f.submit()},{once:true})})()</script></body></html>""".encode("utf-8")
        self.send_response(HTTPStatus.FORBIDDEN)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'")
        self.send_header("Critical-CH", "Sec-CH-UA-Model")
        self.send_header("Vary", "Sec-CH-UA-Model")
        self.cors()
        self.end_headers()
        self.wfile.write(body)

    def send_access_request_page(self) -> None:
        body = """<!doctype html><html lang=\"tr\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\"><meta name=\"theme-color\" content=\"#07100d\"><title>İstek gönderildi · APK Cleaner Studio</title><style>*{box-sizing:border-box}html{font-family:system-ui,sans-serif;background:#07100d;color:#eef5ef}body{min-height:100dvh;margin:0;display:grid;place-items:center;padding:20px}main{width:min(500px,100%);padding:clamp(28px,7vw,42px);border:1px solid #29463d;border-radius:22px;background:#0d1915;text-align:center}i{display:grid;place-items:center;width:58px;height:58px;margin:0 auto 20px;border-radius:50%;background:#123429;color:#63d9b2;font-size:28px;font-style:normal}h1{margin:0 0 12px;font-size:clamp(25px,8vw,36px)}p{margin:0;color:#a8b8b0;line-height:1.65}small{display:block;margin-top:18px;color:#63d9b2}</style></head><body><main><i>✓</i><h1>İstek gönderildi</h1><p>Yöneticiye erişim isteğin iletildi. İzin verilirse bu sayfa otomatik olarak açılacak.</p><small>Bu sayfayı açık bırakabilirsin.</small></main><script>setInterval(async()=>{try{const r=await fetch('/api/status',{cache:'no-store'});if(r.status!==403)location.replace('/')}catch{}},5000)</script></body></html>""".encode("utf-8")
        self.send_response(HTTPStatus.ACCEPTED)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path, download_name: str | None = None, content_type: str | None = None) -> None:
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        mime = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.security_headers(html=path.name == "index.html")
        if path.name == "index.html":
            # On secure top-level loads, supporting browsers retry the first
            # navigation with the Android model hint instead of waiting for a
            # later visit. Browsers may still withhold it by privacy policy.
            self.send_header("Critical-CH", "Sec-CH-UA-Model")
            self.send_header("Vary", "Sec-CH-UA-Model")
        if download_name:
            fallback = re.sub(r"[^A-Za-z0-9._-]+", "_", download_name).strip("._") or "download.apk"
            encoded = quote(download_name, safe="")
            self.send_header("Content-Disposition", f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{encoded}')
        self.cors()
        self.end_headers()
        with path.open("rb") as handle:
            try:
                while chunk := handle.read(1024 * 1024):
                    self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                # Tarayıcı yenileme, sekme kapatma veya indirmeyi iptal etme
                # sırasında istemci soketi normal biçimde kapanabilir. Bu bir
                # sunucu/motor hatası değildir; konsola traceback yazdırma.
                return

    def do_OPTIONS(self) -> None:
        if not self.request_origin_allowed():
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.cors()
        self.end_headers()

    def do_GET(self) -> None:
        observe_public_origin(self.client_address[0], self.headers)
        if not self.request_origin_allowed():
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if self.redirect_secure_http():
            return
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if self.requester_is_blocked():
            if path.startswith("/api/"):
                self.send_json({"error": "Bu cihazın erişimi ana bilgisayar tarafından engellendi."}, HTTPStatus.FORBIDDEN)
            else:
                self.send_blocked_page()
            return
        if path == "/local-ca.crt":
            self.send_file(LOCAL_CA_PATH, "apk-cleaner-local-ca.crt", "application/x-x509-ca-cert")
            return
        if path == "/api/status":
            if parsed.query == "tls_probe=1":
                # boot.js only needs an HTTPS reachability answer. Recording
                # this credential-less cross-scheme probe would manufacture a
                # second local session before app.js can attach its identity.
                self.send_json({"ok": True, "tls": True})
                return
            clients = record_client(self.request_address(), self.headers)
            self.send_json({
                "ok": True,
                "version": VERSION,
                "channel": RELEASE_CHANNEL,
                "engine_version": ENGINE_VERSION,
                "platform": "android" if ANDROID_RUNTIME else "desktop",
                "secure_public_url": _PUBLIC_HTTPS_ORIGIN,
                "toolchain": Toolchain.detect().status(),
                "clients": clients,
            })
            return
        if path == "/api/update":
            result = check_for_updates(VERSION)
            if result.get("update") and not self.requester_is_local():
                result["update"] = {**result["update"], "automatic": False, "install_mode": "manual"}
            self.send_json(result)
            return

        requester_id = client_identity(self.request_address(), self.headers)
        requester_is_local = self.requester_is_local()
        if path == "/api/diagnostic":
            if not requester_is_local:
                self.send_json({"error": "Hata raporu yalnızca bu cihazda açılabilir."}, HTTPStatus.FORBIDDEN)
                return
            query = parse_qs(parsed.query)
            recent = next((row for row in list_job_history(requester_id, True, 100)
                           if row["status"] == "error"), None)
            job = JOBS / recent["job_id"] if recent else None
            self.send_diagnostic(diagnostic_report(job, query.get("identifiers") == ["1"]),
                                 query.get("download") == ["1"])
            return
        if path == "/api/history":
            self.send_json({"jobs": list_job_history(requester_id, requester_is_local)})
            return
        if path == "/api/storage":
            self.send_json(list_job_storage(requester_id, requester_is_local))
            return

        match = re.fullmatch(r"/api/jobs/([a-f0-9]{32})/(state|download|report|source|diagnostic)", path)
        if match:
            job_id, action = match.groups()
            job = JOBS / job_id
            if not job.is_dir():
                self.send_json({"error": "İş bulunamadı."}, 404)
                return
            requester_id = self.requester_id()
            requester_is_local = self.requester_is_local()
            if not job_visible_to(job, requester_id, requester_is_local):
                self.send_json({"error": "Bu işlem bu cihaza ait değil."}, HTTPStatus.FORBIDDEN)
                return
            if action == "state":
                self.send_json(read_json(job / "state.json", {"status": "unknown"}))
            elif action == "diagnostic":
                if not requester_is_local:
                    self.send_json({"error": "Hata raporu yalnızca bu cihazda açılabilir."}, HTTPStatus.FORBIDDEN)
                    return
                query = parse_qs(parsed.query)
                self.send_diagnostic(diagnostic_report(job, query.get("identifiers") == ["1"]),
                                     query.get("download") == ["1"])
            elif action == "report":
                self.send_file(job / "output" / "report.txt", "apk-cleaner-report.txt")
            elif action == "source":
                if not requester_is_local:
                    self.send_json({"error": "Özgün paket yalnızca yerel Android uygulamasından kurulabilir."}, HTTPStatus.FORBIDDEN)
                    return
                analysis = read_json(job / "analysis.json")
                if analysis.get("source_type") not in {"apks", "apkm", "xapk"}:
                    self.send_json({"error": "Doğrudan split kurulumu için APKS, APKM veya XAPK seç."}, 400)
                    return
                name = analysis.get("source_path")
                if not isinstance(name, str) or Path(name).name != name:
                    self.send_json({"error": "Özgün paket bulunamadı."}, 404)
                    return
                self.send_file(job / name, analysis.get("filename"), "application/zip")
            else:
                result = read_json(job / "output" / "report.json")
                name = result.get("output")
                self.send_file(job / "output" / name if name else Path("missing"), name)
            return

        relative = "index.html" if path in {"", "/"} else path.lstrip("/")
        candidate = (WEB / relative).resolve()
        try:
            candidate.relative_to(WEB.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        self.send_file(candidate)

    def receive_multipart_upload(self, job: Path) -> tuple[str, Path, str]:
        """Stream the single package field to disk instead of buffering up to 1 GB in RAM."""
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_UPLOAD:
            raise ValueError("Dosya boyutu geçersiz veya 1 GB sınırını aşıyor.")
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise ValueError("multipart/form-data bekleniyordu.")
        content_header = Message()
        content_header["Content-Type"] = content_type
        boundary_text = content_header.get_boundary()
        if not boundary_text or len(boundary_text) > 200:
            raise ValueError("Yükleme sınırı okunamadı.")
        try:
            boundary = boundary_text.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("Yükleme sınırı geçersiz.") from exc

        remaining = length

        def read_line(limit: int = 65536) -> bytes:
            nonlocal remaining
            if remaining <= 0:
                return b""
            line = self.rfile.readline(min(limit, remaining + 1))
            remaining -= len(line)
            if len(line) > limit:
                raise ValueError("Yükleme üst bilgisi çok uzun.")
            return line

        if read_line().rstrip(b"\r\n") != b"--" + boundary:
            raise ValueError("Yükleme başlangıcı geçersiz.")
        header_bytes = bytearray()
        while True:
            line = read_line()
            if not line:
                raise ValueError("Yükleme üst bilgisi eksik.")
            if line in {b"\r\n", b"\n"}:
                break
            header_bytes.extend(line)
            if len(header_bytes) > 65536:
                raise ValueError("Yükleme üst bilgisi çok uzun.")
        part = BytesParser(policy=policy.default).parsebytes(bytes(header_bytes) + b"\r\n")
        field_name = part.get_param("name", header="content-disposition")
        filename = Path((part.get_filename() or "").replace("\x00", "")).name
        if field_name not in {"package", "apk"} or not filename:
            raise ValueError("Yüklenecek paket alanı bulunamadı.")

        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_PACKAGES:
            raise ValueError("Lütfen .apk, .apks, .apkm veya .xapk dosyası seç.")
        destination = job / filename
        delimiter = b"\r\n--" + boundary
        tail_size = len(delimiter) + 4
        buffer = b""
        boundary_found = False
        digest = hashlib.sha256()
        try:
            with destination.open("xb") as output:
                while remaining > 0:
                    chunk = self.rfile.read(min(UPLOAD_CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    buffer += chunk
                    marker = buffer.find(delimiter)
                    if marker >= 0:
                        final_payload = buffer[:marker]
                        output.write(final_payload)
                        digest.update(final_payload)
                        boundary_found = True
                        break
                    if len(buffer) > tail_size:
                        payload = buffer[:-tail_size]
                        output.write(payload)
                        digest.update(payload)
                        buffer = buffer[-tail_size:]
            while remaining > 0:
                discarded = self.rfile.read(min(UPLOAD_CHUNK_SIZE, remaining))
                if not discarded:
                    break
                remaining -= len(discarded)
            if not boundary_found or destination.stat().st_size <= 0:
                raise ValueError("Yükleme tamamlanamadı.")
            destination.chmod(0o600)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return filename, destination, digest.hexdigest()

    def read_body_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 1024 * 1024:
            raise ValueError("JSON gövdesi geçersiz.")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_POST(self) -> None:
        observe_public_origin(self.client_address[0], self.headers)
        if not self.request_origin_allowed():
            self.send_json({"error": "Bu istek yerel oturuma ait değil."}, HTTPStatus.FORBIDDEN)
            return
        if self.redirect_secure_http():
            return
        path = urlparse(self.path).path
        if path == "/api/client/identify":
            try:
                if not self.requester_is_blocked():
                    raise ValueError("Bu cihaz için etkin bir erişim engeli bulunmuyor.")
                payload = self.read_body_json()
                record_blocked_client_details(self.request_address(), self.headers, payload)
                self.send_json({"ok": True})
            except Exception as exc:
                self.send_json({"error": public_error(exc)}, 400)
            return
        if path == "/api/access-request":
            try:
                request_client_access(self.request_address(), self.headers)
                self.send_access_request_page()
            except Exception as exc:
                self.send_json({"error": public_error(exc)}, 400)
            return
        if self.requester_is_blocked():
            self.send_json({"error": "Bu cihazın erişimi ana bilgisayar tarafından engellendi."}, HTTPStatus.FORBIDDEN)
            return
        analyze_slot = False
        analyze_job: Path | None = None
        try:
            reuse_match = re.fullmatch(r"/api/jobs/([a-f0-9]{32})/reuse", path)
            if reuse_match:
                try:
                    reused_job_id, analysis = clone_job_for_reuse(
                        reuse_match.group(1), self.requester_id(), self.requester_is_local()
                    )
                except PermissionError as exc:
                    self.send_json({"error": public_error(exc)}, HTTPStatus.FORBIDDEN)
                    return
                except FileNotFoundError as exc:
                    self.send_json({"error": public_error(exc)}, HTTPStatus.NOT_FOUND)
                    return
                self.send_json({"job_id": reused_job_id, "analysis": analysis})
                return

            message_match = re.fullmatch(r"/api/jobs/([a-f0-9]{32})/message-candidates", path)
            if message_match:
                job_id = message_match.group(1)
                job = JOBS / job_id
                analysis = read_json(job / "analysis.json")
                if not job_visible_to(job, self.requester_id(), self.requester_is_local()):
                    self.send_json({"error": "Bu işlem bu cihaza ait değil."}, HTTPStatus.FORBIDDEN)
                    return
                payload = self.read_body_json()
                with _ACTIVE_JOBS_LOCK:
                    if _SCANNING_JOBS or _ACTIVE_JOBS:
                        raise ValueError("Başka bir başlangıç taraması veya paket işlemi sürüyor; tamamlanmasını bekle.")
                    _SCANNING_JOBS.add(job_id)
                try:
                    reset_tool_cancellation()
                    prepared_path = analysis.get("prepared_path")
                    modified = job / prepared_path if prepared_path else Path("missing")
                    if analysis.get("split_merged"):
                        source = job / analysis["source_path"]
                        with tempfile.TemporaryDirectory(prefix="startup-scan-", dir=job) as temporary:
                            modified, _log = merge_split_package(source, Path(temporary), selection=payload.get("split_selection"))
                            candidates = inspect_startup_calls(modified)
                    else:
                        if not modified.is_file():
                            raise ValueError("İncelenecek APK bulunamadı. Paketi yeniden yükle.")
                        candidates = inspect_startup_calls(modified)
                    analysis["approved_message_targets"] = [item["id"] for item in candidates]
                    write_json(job / "analysis.json", analysis)
                finally:
                    with _ACTIVE_JOBS_LOCK:
                        _SCANNING_JOBS.discard(job_id)
                self.send_json({"candidates": candidates, "count": len(candidates)})
                return

            delete_match = re.fullmatch(r"/api/jobs/([a-f0-9]{32})/delete", path)
            if delete_match:
                requester_id = self.requester_id()
                requester_is_local = self.requester_is_local()
                delete_job_history(delete_match.group(1), requester_id, requester_is_local)
                self.send_json({"ok": True, "jobs": list_job_history(requester_id, requester_is_local)})
                return

            cancel_match = re.fullmatch(r"/api/jobs/([a-f0-9]{32})/cancel", path)
            if cancel_match:
                active = cancel_clean_job(cancel_match.group(1), self.requester_id(), self.requester_is_local())
                self.send_json({"ok": True, "active": active})
                return

            if path == "/api/client":
                payload = self.read_body_json()
                clients = record_client(self.request_address(), self.headers, details=payload)
                self.send_json({"clients": clients})
                return

            if path == "/api/client/name":
                payload = self.read_body_json()
                requester_id = client_identity(self.request_address(), self.headers, _safe_device_text(payload.get("client_id")))
                requester_is_local = self.requester_is_local()
                label = set_client_label(str(payload.get("target_id", "")), str(payload.get("name", "")), requester_id, requester_is_local)
                clients = record_client(self.request_address(), self.headers, details=payload)
                self.send_json({"ok": True, "name": label, "clients": clients})
                return

            if path == "/api/client/manage":
                payload = self.read_body_json()
                manage_client(str(payload.get("target_id", "")), str(payload.get("action", "")), self.requester_is_local())
                clients = record_client(self.request_address(), self.headers)
                self.send_json({"ok": True, "clients": clients})
                return

            if path == "/api/update/apply":
                if not self.requester_is_local():
                    self.send_json({"error": "Güncelleme yalnızca uygulamanın çalıştığı cihazdan başlatılabilir."}, HTTPStatus.FORBIDDEN)
                    return
                with _ACTIVE_JOBS_LOCK:
                    if _SCANNING_JOBS or _ACTIVE_JOBS:
                        raise ValueError("Güncellemeden önce devam eden paket işleminin tamamlanmasını bekle.")
                result = stage_update(VERSION)
                self.send_json(result)
                if result.get("shutdown"):
                    def stop_for_update() -> None:
                        server = _ACTIVE_SERVER
                        if server is not None:
                            server.shutdown()

                    timer = threading.Timer(0.8, stop_for_update)
                    timer.daemon = True
                    timer.start()
                return

            if path == "/api/setup":
                if not self.requester_is_local():
                    self.send_json({"error": "Araç kurulumu yalnızca ana bilgisayardan başlatılabilir."}, HTTPStatus.FORBIDDEN)
                    return
                self.send_json(install_tools())
                return

            if path == "/api/analyze":
                if not _ANALYZE_SLOTS.acquire(blocking=False):
                    self.send_json({"error": "Aynı anda çok fazla paket yükleniyor; devam eden yüklemeyi bekle."}, HTTPStatus.TOO_MANY_REQUESTS)
                    return
                analyze_slot = True
                owner_id = self.requester_id()
                ensure_job_capacity(owner_id)
                job_id = uuid.uuid4().hex
                job = JOBS / job_id
                job.mkdir(parents=True, exist_ok=False)
                job.chmod(0o700)
                analyze_job = job
                try:
                    filename, source, upload_sha256 = self.receive_multipart_upload(job)
                except Exception:
                    shutil.rmtree(job, ignore_errors=True)
                    raise
                suffix = source.suffix.lower()

                def prepare_progress(message: str, percent: int) -> None:
                    write_json(job / "state.json", {"status": "analyzing", "message": message, "progress": percent, "filename": filename})

                prepare_progress("Paket yerel olarak hazırlanıyor", 4)
                split_options = inspect_split_components(source) if suffix in SPLIT_PACKAGES else None
                merge_log: list[str] = []
                if suffix in SPLIT_PACKAGES:
                    prepare_progress("Split modülleri doğrudan taranıyor", 8)
                    report = inspect_split_package(source, split_options, prepare_progress, upload_sha256)
                    prepared = None
                else:
                    prepare_progress("APK güvenli biçimde taranıyor", 12)
                    report = inspect_apk(source, upload_sha256)
                    prepared = source
                report.update({
                    "filename": filename,
                    "source_type": suffix.lstrip("."),
                    "split_merged": suffix in SPLIT_PACKAGES,
                    "prepared_path": str(prepared.relative_to(job)) if prepared else None,
                    "merge_log": merge_log[-100:],
                    "split_options": split_options,
                    "source_path": str(source.relative_to(job)),
                    "owner_id": owner_id,
                    "created_at": time.time(),
                })
                write_json(job / "analysis.json", report)
                write_json(job / "state.json", {"status": "ready", "message": "Analiz tamamlandı", "progress": 100, "filename": filename})
                self.send_json({"job_id": job_id, "analysis": report})
                analyze_job = None
                return

            if path == "/api/clean":
                payload = self.read_body_json()
                job_id = str(payload.get("job_id", ""))
                operation = str(payload.get("operation", "patch"))
                if operation not in {"patch", "convert", "clone"}:
                    raise ValueError("Bilinmeyen işlem türü.")
                if not JOB_ID.fullmatch(job_id):
                    raise ValueError("Geçersiz iş kimliği.")
                job = JOBS / job_id
                analysis = read_json(job / "analysis.json")
                requester_id = client_identity(self.request_address(), self.headers)
                requester_is_local = self.requester_is_local()
                if not job_visible_to(job, requester_id, requester_is_local):
                    self.send_json({"error": "Bu işlem bu cihaza ait değil."}, HTTPStatus.FORBIDDEN)
                    return
                status, result = start_clean_job(job_id, payload)
                response = {"job_id": job_id, "status": status}
                if result:
                    response["result"] = result
                self.send_json(response, HTTPStatus.OK if status == "done" else HTTPStatus.ACCEPTED)
                return

            self.send_json({"error": "Bilinmeyen işlem."}, 404)
        except Exception as exc:
            if analyze_job is not None:
                shutil.rmtree(analyze_job, ignore_errors=True)
            self.send_json({"error": public_error(exc)}, 400)
        finally:
            if analyze_slot:
                _ANALYZE_SLOTS.release()


def serve(host: str, port: int, open_browser: bool, trust_prompt: bool = True, prefer_http: bool = False) -> None:
    global _ACTIVE_SERVER, _BROWSER_TIMER, _PUBLIC_HTTPS_ORIGIN
    JOBS.mkdir(parents=True, exist_ok=True)
    try:
        DATA_ROOT.chmod(0o700)
        JOBS.chmod(0o700)
    except OSError:
        pass
    cleanup_stale_jobs()
    # Public reverse-proxy origins are learned only for this process. A user's
    # private hostname is never loaded from or written to disk.
    _PUBLIC_HTTPS_ORIGIN = ""
    with _CLIENTS_LOCK:
        _CLIENT_LABELS.clear()
        _CLIENT_LABELS.update({str(key): str(value) for key, value in read_json(CLIENT_LABELS_PATH).items()})
        _BLOCKED_CLIENTS.clear()
        _CLIENTS.clear()
        blocklist = read_json(CLIENT_BLOCKLIST_PATH, {"clients": []})
        for entry in blocklist.get("clients", []):
            record = entry if isinstance(entry, dict) else {"id": str(entry)}
            client_id = str(record.get("id", ""))
            if not re.fullmatch(r"[a-f0-9]{24}", client_id):
                continue
            now = time.time()
            _BLOCKED_CLIENTS.add(client_id)
            _CLIENTS[client_id] = {
                "id": client_id,
                "address": _safe_device_text(record.get("address")) or "—",
                "description": _safe_device_text(record.get("description")) or "Engellenmiş cihaz · Tarayıcı",
                "first_seen": float(record.get("first_seen") or now),
                "last_seen": float(record.get("last_seen") or now),
                "requests": int(record.get("requests") or 0),
                "local": False,
                **{key: record[key] for key in ("model", "hostname", "reported_public_ip", "reported_browser", "access_requested_at") if record.get(key)},
            }
    lan_ip = None if ANDROID_RUNTIME else (local_network_ip() if host in {"0.0.0.0", "::"} else None)
    try:
        if ANDROID_RUNTIME:
            # Uygulama içindeki WebView yalnızca loopback üzerinden erişir. TLS
            # veya CA kurulumu burada ek güvenlik sağlamaz ve Android'de gereksiz
            # sertifika uyarılarına yol açar.
            server = ThreadingHTTPServer((host, port), StudioHandler)
            server.daemon_threads = True
            server.allow_reuse_address = True
            tls_trusted = True
        else:
            tls_addresses = {address for address in (lan_ip, host) if address and address not in {"0.0.0.0", "::"}}
            cert_path, key_path, root_path, tls_trusted = ensure_local_tls(
                DATA_ROOT / "tls",
                {"localhost", socket.gethostname()},
                tls_addresses,
                trust_windows=False,
            )
            if os.name == "nt" and not tls_trusted:
                tls_trusted = request_local_https_trust(root_path, trust_prompt)
            tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls_context.minimum_version = ssl.TLSVersion.TLSv1_2
            tls_context.load_cert_chain(certfile=cert_path, keyfile=key_path)
            server = StudioServer((host, port), StudioHandler, tls_context)
    except OSError as exc:
        print_startup_error(port, exc)
        raise SystemExit(1) from None
    _ACTIVE_SERVER = server
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    # Open through HTTP first. The page upgrades only after the browser has
    # successfully verified the local HTTPS certificate.
    scheme = "http"
    url = f"{scheme}://{display_host}:{port}/"
    network_url = f"http://{lan_ip}:{port}/" if lan_ip else None
    print_startup_panel(url, open_browser, network_url)
    if not ANDROID_RUNTIME and os.name == "nt" and not tls_trusted:
        print("  UYARI · Yerel HTTPS sertifikası güven deposuna eklenemedi; tarayıcı güven uyarısı gösterebilir.", flush=True)
    if open_browser:
        browser_url = preferred_browser_url(url)
        _BROWSER_TIMER = threading.Timer(0.8, lambda: webbrowser.open(browser_url))
        _BROWSER_TIMER.daemon = True
        _BROWSER_TIMER.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\n  APK Cleaner Studio güvenli biçimde kapatıldı. Görüşmek üzere.", flush=True)
    finally:
        _ACTIVE_SERVER = None
        if _BROWSER_TIMER is not None:
            _BROWSER_TIMER.cancel()
            _BROWSER_TIMER = None
        terminate_active_tools()
        server.server_close()


if __name__ == "__main__":
    configure_console()
    install_shutdown_manager()
    parser = argparse.ArgumentParser(description="APK Cleaner Studio yerel web sunucusu")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--open", dest="open_browser", action="store_true")
    parser.add_argument("--no-open", dest="open_browser", action="store_false")
    parser.add_argument("--no-trust-prompt", dest="trust_prompt", action="store_false")
    parser.add_argument("--prefer-http", action="store_true", help="Tarayıcıyı yerel HTTP adresiyle aç")
    parser.set_defaults(open_browser=bool(getattr(sys, "frozen", False)))
    args = parser.parse_args()
    serve(args.host, args.port, args.open_browser, args.trust_prompt, args.prefer_http)
