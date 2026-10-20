"""Opt-in Windows window prototype. Existing console launchers stay unchanged."""
from __future__ import annotations

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

PROJECT = Path(__file__).resolve().parents[2]
WORK = PROJECT / ".codex-temp-dev6" / "windows-prototype"
DEPENDENCIES = PROJECT / ".codex-temp-dev6" / "desktop-deps"
TITLE = "APK Cleaner Studio — Windows Prototipi"
PORT = 18082


def internal_url(url: str, origin: str) -> bool:
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


class OwnedTools:
    """An engine-local subprocess adapter; never changes subprocess globally."""

    def __init__(self):
        self.closing = threading.Event()
        self.lock = threading.Lock()
        self.processes = set()

    def __getattr__(self, name):
        return getattr(subprocess, name)

    def Popen(self, *args, **kwargs):
        with self.lock:
            if self.closing.is_set():
                raise InterruptedError("Pencere kapatıldığı için işlem durduruldu.")
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
    class PrototypeHandler(runtime.StudioHandler):
        def log_message(self, fmt, *args):
            # A browser may probe HTTPS on this HTTP-only port before parsing
            # a request. Such a request does not necessarily have self.path.
            logging.getLogger("desktop.http").info(fmt, *args)

        def send_prototype_text(self, source, content_type, *, html=False):
            body = source.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.security_headers(html=html)
            self.end_headers()
            self.wfile.write(body)

        def request_origin_allowed(self):
            host = urlsplit("//" + self.headers.get("Host", ""))
            try:
                correct_host = host.hostname == "127.0.0.1" and host.port == self.server.server_port
            except ValueError:
                return False
            return correct_host and super().request_origin_allowed()

        def security_headers(self, *, html=False):
            super().security_headers(html=html)
            if html:
                # Restrict even the optional public-IP probe to this prototype.
                self.send_header("Content-Security-Policy", "connect-src 'self'; object-src 'none'; frame-src 'none'")

        def do_GET(self):
            if not self.request_origin_allowed():
                self.send_error(403)
                return
            path = urlsplit(self.path).path
            if path == "/api/update":
                self.send_json({"available": False, "prototype": True})
            elif path == "/":
                source = (runtime.WEB / "index.html").read_text(encoding="utf-8")
                self.send_prototype_text(source.replace("</head>", '<link rel="stylesheet" href="/desktop-prototype.css"></head>', 1), "text/html", html=True)
            elif path == "/desktop-prototype.css":
                self.send_prototype_text("#mobileHttpsBanner{display:none!important}", "text/css")
            elif path == "/boot.js":
                source = (runtime.WEB / "boot.js").read_text(encoding="utf-8")
                guard = 'if (location.protocol !== "http:" || document.documentElement.dataset.embedded === "android") return;'
                if source.count(guard) != 1:
                    self.send_error(500)
                    return
                # A native loopback-only window has no LAN certificate setup.
                # Only this prototype's response changes, never the source file.
                self.send_prototype_text(source.replace(guard, 'return; // No LAN HTTPS probe in the native prototype.', 1), "text/javascript")
            elif path == "/prototype/status":
                self.send_json({"prototype": True, "closing": tools.closing.is_set(), "version": runtime.VERSION})
            elif path == "/local-ca.crt":
                self.send_error(404)
            else:
                super().do_GET()

        def do_POST(self):
            if not self.request_origin_allowed():
                self.send_json({"error": "Bu istek prototip oturumuna ait değil."}, 403)
            elif tools.closing.is_set():
                self.send_json({"error": "Prototip güvenli biçimde kapatılıyor."}, 503)
            elif urlsplit(self.path).path in {"/api/update/apply", "/api/setup"}:
                self.send_json({"error": "Prototipte güncelleme ve bileşen indirmeleri kapalıdır."}, 409)
            else:
                super().do_POST()

    return PrototypeHandler


class PrototypeHost:
    def __init__(self, runtime, engine, port=PORT):
        self.runtime, self.engine = runtime, engine
        self.tools = OwnedTools()
        self.original_subprocess = engine.subprocess
        self.http = ThreadingHTTPServer(("127.0.0.1", port), handler_for(runtime, self.tools))
        self.http.daemon_threads = True
        self.thread = threading.Thread(target=self.http.serve_forever, name="desktop-prototype-http", daemon=True)
        self.url = f"http://127.0.0.1:{self.http.server_port}/"
        self.stopped = False
        self.started = False

    def start(self):
        self.runtime.JOBS.mkdir(parents=True, exist_ok=True)
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
            logging.getLogger("desktop.stdout").info(text.rstrip())
        return len(text)

    def flush(self):
        for handler in logging.getLogger().handlers:
            handler.flush()


def configure_environment():
    WORK.mkdir(parents=True, exist_ok=True)
    os.environ["APK_CLEANER_DATA_ROOT"] = str(WORK / "data")
    os.environ.pop("APK_CLEANER_ANDROID", None)
    (WORK / "tmp").mkdir(exist_ok=True)
    for key in ("TEMP", "TMP"):
        os.environ[key] = str(WORK / "tmp")
    jdk = PROJECT / ".tools/temurin-21/jdk-21.0.12.1+1"
    if (jdk / "bin/java.exe").is_file():
        os.environ["JAVA_HOME"] = str(jdk)
        os.environ["PATH"] = str(jdk / "bin") + os.pathsep + os.environ.get("PATH", "")
    sys.path.insert(0, str(DEPENDENCIES))
    sys.path.insert(0, str(PROJECT / "studio"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", force=True,
                        handlers=[RotatingFileHandler(WORK / "prototype.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")])
    sys.stdout = sys.stderr = LogStream()


def main():
    configure_environment()
    host = None
    try:
        import webview
        import engine
        import server
        host = PrototypeHost(server, engine)
        host.start()
        status = {"pid": os.getpid(), "url": host.url, "title": TITLE, "state": "starting", "data": str(server.DATA_ROOT)}

        def save_status(state):
            status["state"] = state
            (WORK / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

        save_status("starting")
        webview.settings.update({"ALLOW_DOWNLOADS": True, "ALLOW_FILE_URLS": False,
                                 "OPEN_EXTERNAL_LINKS_IN_BROWSER": False, "REMOTE_DEBUGGING_PORT": None})
        window = webview.create_window(TITLE, host.url, width=1200, height=860, min_size=(760, 600),
                                       background_color="#0d1515", text_select=True)
        event_handlers = []

        def before_show():
            # This is specific to the pinned edgechromium prototype backend.
            # No API or arbitrary Python object is exposed to web content.
            control = window.native.webview

            def navigating(sender, args):
                if not internal_url(str(args.Uri), host.url):
                    args.Cancel = True

            def ready(sender, args):
                core = control.CoreWebView2
                if core is not None:
                    def new_window(sender, args):
                        args.Handled = True  # Keep external sites out of the prototype.
                    core.NewWindowRequested += new_window
                    event_handlers.append(new_window)

            control.NavigationStarting += navigating
            control.CoreWebView2InitializationCompleted += ready
            event_handlers.extend([navigating, ready])

        def closing():
            return host.accept_close(lambda: window.create_confirmation_dialog(
                "Uygulama kapatılsın mı?",
                "Devam eden işlem durdurulacak. Tamamlanmamış çıktı kullanılamaz; orijinal paket korunur."))

        window.events.before_show += before_show
        window.events.closing += closing
        window.events.loaded += lambda: save_status("ready")
        webview.start(gui="edgechromium", debug=False, private_mode=False, storage_path=str(WORK / "webview-profile"),
                      icon=str(PROJECT / "public/favicon.ico"), localization={
                          "global.ok": "Tamam", "global.cancel": "Vazgeç", "global.quit": "Çıkış",
                          "global.saveFile": "Dosyayı kaydet", "windows.fileFilter.allFiles": "Tüm dosyalar"})
        save_status("closing")
    except Exception:
        logging.exception("Windows pencere prototipi başlatılamadı")
        if os.name == "nt":
            ctypes.windll.user32.MessageBoxW(None,
                "Prototip açılamadı. Başka bir prototip penceresi açıksa önce onu kapatın.\n"
                "Ayrıntılar: " + str(WORK / "prototype.log"), TITLE, 0x10)
        return 1
    finally:
        if host is not None:
            host.stop()
            if 'save_status' in locals():
                save_status("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
