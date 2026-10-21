"""Windows desktop entry point. The browser/Termux server remains independent."""
from __future__ import annotations

import argparse
import ctypes
from http.server import ThreadingHTTPServer
import io
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import sys
import threading
from urllib.parse import urlsplit
import webbrowser

TITLE = "APK Cleaner Studio"
ROOT = Path(__file__).resolve().parent


def internal_url(url, origin):
    if url == "about:blank":
        return True
    try:
        candidate, expected = urlsplit(url), urlsplit(origin)
        return (candidate.scheme == expected.scheme == "http"
                and candidate.hostname == expected.hostname == "127.0.0.1"
                and candidate.port == expected.port
                and not candidate.username and not candidate.password)
    except ValueError:
        return False


def external_url(url):
    try:
        parsed = urlsplit(url)
        return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password
    except ValueError:
        return False


class OwnedTools:
    """Hide and track engine children without altering subprocess globally."""
    def __init__(self):
        self.closing = threading.Event()
        self.lock = threading.Lock()
        self.processes = set()
        self.analyses = 0

    def __getattr__(self, name):
        return getattr(subprocess, name)

    def Popen(self, *args, **kwargs):
        with self.lock:
            if self.closing.is_set():
                raise InterruptedError("Uygulama kapatıldığı için işlem durduruldu.")
            if os.name == "nt":
                kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
            process = subprocess.Popen(*args, **kwargs)
            self.processes = {item for item in self.processes if item.poll() is None}
            self.processes.add(process)
            return process

    def begin_close(self):
        with self.lock:
            self.closing.set()

    def begin_analysis(self):
        with self.lock:
            if self.closing.is_set():
                return False
            self.analyses += 1
            return True

    def end_analysis(self):
        with self.lock:
            self.analyses -= 1

    def is_analyzing(self):
        with self.lock:
            return self.analyses > 0

    def stop(self):
        self.begin_close()
        with self.lock:
            owned = list(self.processes)
        for process in owned:
            if process.poll() is None:
                try:
                    process.terminate()
                except OSError:
                    pass
        for process in owned:
            if process.poll() is None:
                try:
                    process.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)


def handler_for(runtime, tools, network=None):
    class DesktopHandler(runtime.StudioHandler):
        def log_message(self, fmt, *args):
            logging.getLogger("desktop.http").info(fmt, *args)

        def request_origin_allowed(self):
            try:
                host = urlsplit("//" + self.headers.get("Host", ""))
                valid = host.hostname == "127.0.0.1" and host.port == self.server.server_port
                return valid and super().request_origin_allowed()
            except ValueError:
                return False

        def security_headers(self, *, html=False):
            super().security_headers(html=html)
            if html:
                self.send_header("Content-Security-Policy", "connect-src 'self'; object-src 'none'; frame-src 'none'")

        def send_text(self, source, content_type, *, html=False):
            body = source.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.security_headers(html=html)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self.request_origin_allowed():
                self.send_error(403)
                return
            path = urlsplit(self.path).path
            if path == "/":
                source = (runtime.WEB / "index.html").read_text(encoding="utf-8")
                source = source.replace('<html lang="tr"', '<html data-desktop-native="true" lang="tr"', 1)
                source = source.replace("</head>", '<link rel="stylesheet" href="/desktop-window.css"></head>', 1)
                source = source.replace('<section id="clientCard"',
                                        (ROOT / "desktop/network.html").read_text(encoding="utf-8") + '<section id="clientCard"', 1)
                source = source.replace("</body>", '<script src="/desktop-network.js" defer></script></body>', 1)
                self.send_text(source, "text/html", html=True)
            elif path == "/desktop-window.css":
                self.send_text((ROOT / "desktop/desktop.css").read_text(encoding="utf-8"), "text/css")
            elif path == "/desktop-network.js":
                self.send_text((ROOT / "desktop/network.js").read_text(encoding="utf-8"), "text/javascript")
            elif path == "/api/desktop/network" and network is not None:
                self.send_json(network.state())
            elif path == "/boot.js":
                source = (runtime.WEB / "boot.js").read_text(encoding="utf-8")
                guard = 'if (location.protocol !== "http:" || document.documentElement.dataset.embedded === "android") return;'
                if source.count(guard) != 1:
                    self.send_error(500)
                    return
                self.send_text(source.replace(guard, 'return; // Native loopback window needs no LAN TLS probe.', 1), "text/javascript")
            elif path == "/local-ca.crt":
                if network is not None and network.state()["enabled"]:
                    self.send_file(runtime.LOCAL_CA_PATH, "apk-cleaner-local-ca.crt", "application/x-x509-ca-cert")
                else:
                    self.send_error(404)
            else:
                super().do_GET()  # Includes the real update, history and output APIs.

        def do_POST(self):
            # Read the tiny control payload even when rejecting its origin.
            # Otherwise Windows may reset an HTTP/1.0 connection with unread
            # request bytes before the client can receive our Turkish error.
            control = urlsplit(self.path).path == "/api/desktop/network" and network is not None
            payload = None
            if control:
                try:
                    payload = self.read_body_json()
                except (ValueError, UnicodeError):
                    self.send_json({"error": "Yerel ağ seçimi geçersiz."}, 400)
                    return
            if not self.request_origin_allowed():
                self.send_json({"error": "Bu istek uygulama oturumuna ait değil."}, 403)
            elif tools.closing.is_set():
                self.send_json({"error": "Uygulama güvenli biçimde kapatılıyor."}, 503)
            elif control:
                # Only a same-origin native request may expose the LAN listener.
                if self.headers.get("Origin") != f"http://127.0.0.1:{self.server.server_port}":
                    self.send_json({"error": "Yerel ağ ayarı yalnızca uygulama penceresinden değiştirilebilir."}, 403)
                    return
                try:
                    if not isinstance(payload, dict) or type(payload.get("enabled")) is not bool:
                        raise ValueError("Yerel ağ seçimi geçersiz.")
                    self.send_json(network.set_enabled(payload["enabled"]))
                except ValueError as exc:
                    self.send_json({"error": str(exc)}, 400)
                except Exception:
                    logging.exception("Yerel ağ erişimi değiştirilemedi")
                    self.send_json({"error": "Yerel ağ erişimi açılamadı. Ağ bağlantısını ve bağlantı noktasının başka bir uygulamada kullanılmadığını kontrol edin."}, 503)
            elif urlsplit(self.path).path == "/api/analyze":
                if not tools.begin_analysis():
                    self.send_json({"error": "Uygulama güvenli biçimde kapatılıyor."}, 503)
                    return
                try:
                    super().do_POST()
                finally:
                    tools.end_analysis()
            else:
                super().do_POST()  # Setup and verified updates remain enabled.
    return DesktopHandler


class DesktopHost:
    def __init__(self, runtime, engine, port=0, lan_port=8080):
        self.runtime, self.engine = runtime, engine
        self.tools = OwnedTools()
        from desktop_network import LocalNetwork
        self.network = LocalNetwork(runtime, self.tools, lan_port)
        self.original_subprocess = engine.subprocess
        self.http = ThreadingHTTPServer(("127.0.0.1", port), handler_for(runtime, self.tools, self.network))
        self.http.daemon_threads = True
        self.server_stopped = threading.Event()
        self.thread = threading.Thread(target=self.serve, name="desktop-http", daemon=True)
        self.url = f"http://127.0.0.1:{self.http.server_port}/"
        self.stopped = False
        self.started = False

    def serve(self):
        try:
            self.http.serve_forever()
        finally:
            self.server_stopped.set()

    def start(self):
        self.runtime.JOBS.mkdir(parents=True, exist_ok=True)
        self.runtime.cleanup_stale_jobs()
        self.runtime.reconcile_interrupted_jobs()
        self.runtime.load_client_settings()
        self.engine.subprocess = self.tools
        self.runtime._ACTIVE_SERVER = self.http
        self.thread.start()
        self.started = True

    def busy(self):
        with self.runtime._ACTIVE_JOBS_LOCK:
            active = bool(self.runtime._ACTIVE_JOBS or self.runtime._SCANNING_JOBS)
        return active or self.tools.is_analyzing()

    def accept_close(self, confirm):
        if self.busy() and not confirm():
            return False
        self.tools.begin_close()
        return True

    def watch_shutdown(self, window):
        # Automatic updater shuts down HTTP after its response; also release
        # the native window so its helper can replace and restart the EXE.
        self.server_stopped.wait()
        if not self.stopped:
            window.destroy()

    def stop(self):
        if self.stopped:
            return
        self.stopped = True
        self.tools.begin_close()
        with self.runtime._ACTIVE_JOBS_LOCK:
            for event in self.runtime._JOB_CANCEL_EVENTS.values():
                event.set()
        try:
            self.network.close()
            self.engine.terminate_active_tools()
            self.tools.stop()
        finally:
            if self.started:
                self.http.shutdown()
                self.thread.join(timeout=3)
            self.http.server_close()
            self.runtime._ACTIVE_SERVER = None
            self.engine.subprocess = self.original_subprocess


class LogStream(io.TextIOBase):
    def write(self, text):
        if text.strip():
            logging.getLogger("desktop.output").info(text.rstrip())
        return len(text)

    def flush(self):
        for handler in logging.getLogger().handlers:
            handler.flush()


def main():
    parser = argparse.ArgumentParser(description="APK Cleaner Studio Windows uygulaması")
    # A stable internal origin preserves WebView theme/profile localStorage.
    # Keep it separate so LAN can own port 8080 without restarting the window.
    parser.add_argument("--port", type=int, default=8081, help="Uygulama içi bağlantı noktası")
    parser.add_argument("--lan-port", type=int, default=8080, help="İsteğe bağlı yerel ağ bağlantı noktası")
    # Keep compatibility with existing Windows shortcuts, without opening a browser.
    parser.add_argument("--open", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-open", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    host = None
    status_path = None
    instance = None
    try:
        import engine
        if os.name == "nt":
            from windows_shell import InstanceGate
            instance = InstanceGate(engine.DATA_ROOT / "logs/desktop-session.json", TITLE)
            if instance.existing:
                if not instance.request_activation():
                    ctypes.windll.user32.MessageBoxW(None, "Açık uygulama penceresine ulaşılamadı. Uygulamayı kapatıp yeniden deneyin.", TITLE, 0x40)
                return 0
        logs = engine.DATA_ROOT / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", force=True,
                            handlers=[RotatingFileHandler(logs / "desktop.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")])
        sys.stdout = sys.stderr = LogStream()
        import webview
        import server
        host = DesktopHost(server, engine, args.port, lan_port=args.lan_port)
        host.start()
        status_path = logs / "desktop-session.json"
        status = {"pid": os.getpid(), "url": host.url, "version": server.VERSION, "state": "starting"}

        def save_status(state):
            status["state"] = state
            status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

        save_status("starting")
        webview.settings.update({"ALLOW_DOWNLOADS": True, "ALLOW_FILE_URLS": False,
                                 "OPEN_EXTERNAL_LINKS_IN_BROWSER": False, "REMOTE_DEBUGGING_PORT": None})
        window = webview.create_window(TITLE, host.url, width=1200, height=860, min_size=(760, 600),
                                       background_color="#0d1515", text_select=True)
        event_handlers = []
        shell_integrations = []

        def before_show():
            try:
                from windows_shell import WindowsShell
                shell_integrations.append(WindowsShell(window.native, server, engine.DATA_ROOT / "desktop-window.json", instance,
                                                       analyzing=host.tools.is_analyzing))
            except Exception:
                logging.exception("Pencere tercihleri uygulanamadı")
            control = window.native.webview

            def navigating(sender, event):
                if not internal_url(str(event.Uri), host.url):
                    event.Cancel = True

            def ready(sender, event):
                core = control.CoreWebView2
                if core is not None:
                    def new_window(sender, event):
                        event.Handled = True
                        url = str(event.Uri)
                        if external_url(url):
                            webbrowser.open(url)  # Only an explicit external-link click.
                    core.NewWindowRequested += new_window
                    event_handlers.append(new_window)
            control.NavigationStarting += navigating
            control.CoreWebView2InitializationCompleted += ready
            event_handlers.extend([navigating, ready])

        window.events.before_show += before_show
        window.events.closing += lambda: host.accept_close(lambda: window.create_confirmation_dialog(
            "Uygulama kapatılsın mı?",
            "Devam eden işlem durdurulacak. Tamamlanmamış çıktı kullanılamaz; orijinal paket korunur."))
        window.events.loaded += lambda: save_status("ready")
        threading.Thread(target=host.watch_shutdown, args=(window,), daemon=True, name="desktop-update-close").start()
        icon = ROOT / "desktop/favicon.ico"
        if not icon.is_file():
            icon = ROOT.parent / "public/favicon.ico"
        webview.start(gui="edgechromium", debug=False, private_mode=False,
                      storage_path=str(engine.DATA_ROOT / "desktop-webview"), icon=str(icon),
                      localization={"global.ok": "Tamam", "global.cancel": "Vazgeç", "global.quit": "Çıkış",
                                    "global.saveFile": "Dosyayı kaydet", "windows.fileFilter.allFiles": "Tüm dosyalar"})
        return 0
    except Exception:
        logging.exception("Windows uygulaması başlatılamadı")
        if os.name == "nt":
            ctypes.windll.user32.MessageBoxW(None,
                "Uygulama başlatılamadı. Başka bir APK Cleaner Studio oturumu açıksa kapatıp yeniden deneyin.\n"
                "Microsoft Edge WebView2 Runtime ve .NET Framework 4.8 bileşenlerinin kurulu olduğunu kontrol edin.\n"
                "Ayrıntılar uygulamanın logs/desktop.log dosyasına kaydedilir.", TITLE, 0x10)
        return 1
    finally:
        if host is not None:
            host.stop()
        if status_path is not None and 'save_status' in locals():
            save_status("stopped")
        if instance:
            instance.close()


if __name__ == "__main__":
    raise SystemExit(main())
