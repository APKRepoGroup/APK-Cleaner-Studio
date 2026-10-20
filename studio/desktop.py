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


def handler_for(runtime, tools):
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
                self.send_text(source, "text/html", html=True)
            elif path == "/desktop-window.css":
                self.send_text((ROOT / "desktop/desktop.css").read_text(encoding="utf-8"), "text/css")
            elif path == "/boot.js":
                source = (runtime.WEB / "boot.js").read_text(encoding="utf-8")
                guard = 'if (location.protocol !== "http:" || document.documentElement.dataset.embedded === "android") return;'
                if source.count(guard) != 1:
                    self.send_error(500)
                    return
                self.send_text(source.replace(guard, 'return; // Native loopback window needs no LAN TLS probe.', 1), "text/javascript")
            elif path == "/local-ca.crt":
                self.send_error(404)
            else:
                super().do_GET()  # Includes the real update, history and output APIs.

        def do_POST(self):
            if not self.request_origin_allowed():
                self.send_json({"error": "Bu istek uygulama oturumuna ait değil."}, 403)
            elif tools.closing.is_set():
                self.send_json({"error": "Uygulama güvenli biçimde kapatılıyor."}, 503)
            else:
                super().do_POST()  # Setup and verified updates remain enabled.
    return DesktopHandler


class DesktopHost:
    def __init__(self, runtime, engine, port=8080):
        self.runtime, self.engine = runtime, engine
        self.tools = OwnedTools()
        self.original_subprocess = engine.subprocess
        self.http = ThreadingHTTPServer(("127.0.0.1", port), handler_for(runtime, self.tools))
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
        self.engine.subprocess = self.tools
        self.runtime._ACTIVE_SERVER = self.http
        self.thread.start()
        self.started = True

    def busy(self):
        with self.runtime._ACTIVE_JOBS_LOCK:
            return bool(self.runtime._ACTIVE_JOBS or self.runtime._SCANNING_JOBS)

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
    parser.add_argument("--port", type=int, default=8080)
    # Keep compatibility with existing Windows shortcuts, without opening a browser.
    parser.add_argument("--open", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-open", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    host = None
    status_path = None
    mutex = None
    try:
        if os.name == "nt":
            kernel = ctypes.windll.kernel32
            kernel.CreateMutexW.restype = ctypes.c_void_p
            mutex = kernel.CreateMutexW(None, False, "Local\\APKCleanerStudio.Desktop")
            if not mutex:
                raise OSError("Uygulama oturumu oluşturulamadı.")
            if kernel.GetLastError() == 183:
                ctypes.windll.user32.MessageBoxW(None, "APK Cleaner Studio zaten açık. Açık uygulama penceresini kullanın.", TITLE, 0x40)
                return 0
        import engine
        logs = engine.DATA_ROOT / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", force=True,
                            handlers=[RotatingFileHandler(logs / "desktop.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")])
        sys.stdout = sys.stderr = LogStream()
        import webview
        import server
        host = DesktopHost(server, engine, args.port)
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

        def before_show():
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
        if mutex:
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(mutex))


if __name__ == "__main__":
    raise SystemExit(main())
