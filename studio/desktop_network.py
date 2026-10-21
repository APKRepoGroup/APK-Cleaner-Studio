"""Opt-in LAN listener, separate from the native window's loopback origin."""
from __future__ import annotations

import ipaddress
import socket
import ssl
import threading
from urllib.parse import urlsplit


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

    def state(self):
        with self.lock:
            active = self.enabled.is_set()
            return {"enabled": active, "url": self.address if active else "",
                    "secure_url": self.address.replace("http:", "https:", 1) if active else ""}

    def set_enabled(self, enabled):
        with self.lock:
            if enabled == self.enabled.is_set():
                return self.state()
            if enabled:
                if self.tools.closing.is_set():
                    raise ValueError("Uygulama kapatılırken yerel ağ erişimi açılamaz.")
                address = self.runtime.local_network_ip()
                if not address or not private_address(address) or ipaddress.ip_address(address).is_loopback:
                    raise ValueError("Yerel ağ adresi bulunamadı. Wi-Fi veya Ethernet bağlantısını kontrol edin.")
                cert, key, _root, _trusted = self.runtime.ensure_local_tls(
                    self.runtime.DATA_ROOT / "tls", {"localhost", socket.gethostname()}, {address, "127.0.0.1"},
                    trust_windows=False)
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.minimum_version = ssl.TLSVersion.TLSv1_2
                context.load_cert_chain(certfile=cert, keyfile=key)
                self.enabled = threading.Event()
                listener = self.runtime.StudioServer(("0.0.0.0", self.port), self.handler(address), context)
                self.address = f"http://{address}:{listener.server_port}/"
                self.http = listener
                self.enabled.set()
                self.thread = threading.Thread(target=listener.serve_forever, name="desktop-lan", daemon=True)
                try:
                    self.thread.start()
                except Exception:
                    self.enabled.clear()
                    listener.server_close()
                    self.http = self.thread = None
                    raise
            else:
                self.enabled.clear()
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

            def do_GET(self):
                if not self.request_origin_allowed():
                    self.send_json({"error": "Bu yerel ağ isteğine izin verilmiyor."}, 403)
                    return
                super().do_GET()

            def do_POST(self):
                if not self.request_origin_allowed():
                    self.send_json({"error": "Yerel ağ erişimi kapalı veya bu isteğe izin verilmiyor."}, 403)
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
