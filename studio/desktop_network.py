"""Opt-in LAN listener, separate from the native window's loopback origin."""
from __future__ import annotations

import ipaddress
import errno
import html
from http.cookies import SimpleCookie, CookieError
from pathlib import Path
import socket
import ssl
import threading
from urllib.parse import urlsplit, parse_qs
from desktop_pairing import Pairing, COOKIE


class NetworkError(ValueError):
    def __init__(self, code, message, status=503):
        super().__init__(message)
        self.code, self.status = code, status

    def payload(self):
        return {"error": str(self), "error_code": self.code}


def network_failure(error, stage, port):
    native = getattr(error, "winerror", None)
    code = getattr(error, "errno", None)
    if stage == "certificate":
        return NetworkError("certificate_unavailable", "Yerel HTTPS sertifikası hazırlanamadı. Uygulamanın veri klasöründeki yazma iznini ve sistem tarihini kontrol edin.")
    if native == 10048 or code == errno.EADDRINUSE:
        return NetworkError("port_in_use", f"{port} bağlantı noktası başka bir uygulama tarafından kullanılıyor. Bu portu kullanan uygulamayı kapatıp yeniden deneyin.", 409)
    if native == 10013 or code in {errno.EACCES, errno.EPERM}:
        return NetworkError("network_permission", "Yerel ağ bağlantısı için erişim izni verilmedi. Windows'un ağ erişim izinlerini ve bağlantı noktası kısıtlamalarını kontrol edin.", 403)
    if native in {10049, 10050, 10051} or code in {errno.EADDRNOTAVAIL, errno.ENETDOWN, errno.ENETUNREACH}:
        return NetworkError("network_unavailable", "Yerel ağ bağlantısı kullanılamıyor. Wi-Fi veya Ethernet bağlantısını kontrol edip yeniden deneyin.")
    return NetworkError("listener_unavailable", "Yerel ağ erişimi başlatılamadı. Uygulamayı yeniden açıp tekrar deneyin.")


def private_address(value):
    try:
        address = ipaddress.ip_address(value)
        return address.version == 4 and (address.is_private or address.is_loopback) and not (
            address.is_unspecified or address.is_multicast or address.is_reserved)
    except ValueError:
        return False


class LocalNetwork:
    def __init__(self, runtime, tools, port):
        self.runtime, self.tools, self.port = runtime, tools, port
        self.lock = threading.RLock()
        self.http = self.thread = None
        self.enabled = threading.Event()
        self.address = ""
        self.pairing = Pairing()

    def state(self):
        with self.lock:
            active = self.enabled.is_set()
            return {"enabled": active, "url": self.address if active else "",
                    "secure_url": self.address.replace("http:", "https:", 1) if active else "",
                    "pairing_code": self.pairing.current_code() if active else ""}

    def set_enabled(self, enabled):
        with self.lock:
            if enabled == self.enabled.is_set():
                return self.state()
            if enabled:
                if self.tools.closing.is_set():
                    raise NetworkError("app_closing", "Uygulama kapatılırken yerel ağ erişimi açılamaz.")
                if type(self.port) is not int or not 0 <= self.port <= 65535:
                    raise NetworkError("invalid_port", "Bağlantı noktası geçersiz. 1 ile 65535 arasında bir port kullanın.", 400)
                address = self.runtime.local_network_ip()
                if not address or not private_address(address) or ipaddress.ip_address(address).is_loopback:
                    raise NetworkError("network_address_missing", "Yerel ağ adresi bulunamadı. Wi-Fi veya Ethernet bağlantısını kontrol edin.", 400)
                try:
                    cert, key, _root, _trusted = self.runtime.ensure_local_tls(
                        self.runtime.DATA_ROOT / "tls", {"localhost", socket.gethostname()}, {address, "127.0.0.1"},
                        trust_windows=False)
                    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                    context.minimum_version = ssl.TLSVersion.TLSv1_2
                    context.load_cert_chain(certfile=cert, keyfile=key)
                except Exception as exc:
                    raise network_failure(exc, "certificate", self.port) from exc
                self.enabled = threading.Event()
                try:
                    listener = self.runtime.StudioServer(("0.0.0.0", self.port), self.handler(address), context)
                except OSError as exc:
                    raise network_failure(exc, "bind", self.port) from exc
                self.address = f"http://{address}:{listener.server_port}/"
                self.http = listener
                self.pairing.reset(True)
                self.enabled.set()
                self.thread = threading.Thread(target=listener.serve_forever, name="desktop-lan", daemon=True)
                try:
                    self.thread.start()
                except Exception as exc:
                    self.enabled.clear()
                    self.pairing.reset()
                    listener.server_close()
                    self.http = self.thread = None
                    raise network_failure(exc, "thread", self.port) from exc
            else:
                self.enabled.clear()
                self.pairing.reset()
                listener, thread = self.http, self.thread
                self.http = self.thread = None
                if listener:
                    listener.shutdown()
                    listener.server_close()
                    thread.join(timeout=3)
            return self.state()

    def handler(self, address):
        gate = self.enabled  # Reopening must never revive an old connection.
        runtime, tools = self.runtime, self.tools
        pairing = self.pairing

        class NetworkHandler(runtime.StudioHandler):
            def request_origin_allowed(self):
                try:
                    host = urlsplit("//" + self.headers.get("Host", ""))
                    return (gate.is_set() and not tools.closing.is_set()
                            and private_address(self.client_address[0])
                            and host.hostname in {address, "127.0.0.1", "localhost"}
                            and host.port == self.server.server_port and super().request_origin_allowed())
                except ValueError:
                    return False

            def request_address(self):
                # This listener is never a public reverse proxy. Forwarded IP
                # headers must not grant local-admin privileges to a LAN peer.
                return self.client_address[0]

            def requester_is_local(self):
                return False

            def trusted_local_proxy(self):
                return False

            def paired(self):
                try:
                    cookies = SimpleCookie()
                    cookies.load(self.headers.get("Cookie", ""))
                    token = cookies[COOKIE].value if COOKIE in cookies else ""
                    return pairing.authorize(token, self.client_address[0], self.headers.get("User-Agent", ""))
                except CookieError:
                    return False

            def discard_small_body(self):
                # A small unread body can turn a useful HTTP error into a TCP
                # reset on Windows. Never consume an unauthenticated upload.
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if 0 < length <= 8192:
                        self.rfile.read(length)
                except ValueError:
                    pass

            def pair_page(self, error="", status=200):
                source = (Path(__file__).resolve().parent / "desktop/pair.html").read_text(encoding="utf-8")
                body = source.replace("{{error}}", html.escape(error)).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                if status == 429:
                    self.send_header("Retry-After", "300")
                self.security_headers()
                self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
                self.end_headers()
                self.wfile.write(body)

            def pair_request(self):
                scheme = "https" if isinstance(self.connection, ssl.SSLSocket) else "http"
                if self.headers.get("Origin") != scheme + "://" + self.headers.get("Host", ""):
                    self.discard_small_body()
                    self.send_json({"error": "Eşleştirme isteği bu bağlantıya ait değil."}, 403)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 512:
                        raise ValueError()
                    data = parse_qs(self.rfile.read(length).decode("utf-8"), max_num_fields=4)
                    codes = data.get("code", [])
                    if len(codes) != 1:
                        raise ValueError()
                    outcome, token = pairing.pair(codes[0], self.client_address[0], self.headers.get("User-Agent", ""))
                except (ValueError, UnicodeError):
                    self.pair_page("6 haneli eşleştirme kodunu girin.", 400)
                    return
                if outcome != "ok":
                    message = {"invalid": "Kod doğrulanamadı. Bilgisayardaki güncel kodu kontrol edin.",
                               "limited": "Çok fazla deneme yapıldı. 5 dakika sonra yeniden deneyin.",
                               "full": "Oturum sınırına ulaşıldı. Bilgisayardan yerel ağ erişimini kapatıp yeniden açın."}[outcome]
                    self.pair_page(message, 429 if outcome in {"limited", "full"} else 403)
                    return
                self.send_response(303)
                self.send_header("Location", "/")
                self.send_header("Set-Cookie", f"{COOKIE}={token}; Path=/; Max-Age=28800; HttpOnly; SameSite=Strict" + ("; Secure" if scheme == "https" else ""))
                self.send_header("Content-Length", "0")
                self.security_headers()
                self.end_headers()

            def do_GET(self):
                if not self.request_origin_allowed():
                    self.send_json({"error": "Bu yerel ağ isteğine izin verilmiyor."}, 403)
                    return
                path = urlsplit(self.path).path
                if path != "/local-ca.crt" and not self.paired():
                    if path == "/":
                        self.pair_page()
                    else:
                        self.send_json({"error": "Bu cihazı önce bilgisayardaki kodla eşleştirin.", "pairing_required": True}, 401)
                    return
                super().do_GET()

            def do_POST(self):
                if not self.request_origin_allowed():
                    self.discard_small_body()
                    self.send_json({"error": "Yerel ağ erişimi kapalı veya bu isteğe izin verilmiyor."}, 403)
                    return
                if urlsplit(self.path).path == "/api/desktop/pair":
                    self.pair_request()
                    return
                if not self.paired():
                    self.discard_small_body()
                    self.send_json({"error": "Bu cihazı önce bilgisayardaki kodla eşleştirin.", "pairing_required": True}, 401)
                    return
                if urlsplit(self.path).path == "/api/analyze":
                    if not tools.begin_analysis():
                        self.send_json({"error": "Uygulama güvenli biçimde kapatılıyor."}, 503)
                        return
                    try:
                        super().do_POST()
                    finally:
                        tools.end_analysis()
                else:
                    super().do_POST()

        return NetworkHandler

    def close(self):
        self.set_enabled(False)
