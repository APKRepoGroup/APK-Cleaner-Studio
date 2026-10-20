from pathlib import Path
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "studio"))
import desktop
import engine
import server


class WindowsDesktopTests(unittest.TestCase):
    def test_navigation_policy(self):
        origin = "http://127.0.0.1:8080/"
        self.assertTrue(desktop.internal_url(origin + "api/status", origin))
        self.assertTrue(desktop.external_url("https://example.com/"))
        for url in ("file:///C:/private.txt", "javascript:alert(1)", "http://user@127.0.0.1:8080/",
                    "http://127.0.0.1:8081/", "https://example.com/", "http://[broken"):
            self.assertFalse(desktop.internal_url(url, origin))
        for url in ("file:///C:/private.txt", "javascript:alert(1)", "http://example.com", "https://user:pw@example.com/", "https://[broken"):
            self.assertFalse(desktop.external_url(url))

    def test_packaging_promotes_only_preview_one(self):
        spec = (ROOT / "packaging/APK-Cleaner-Studio-Windows.spec").read_text(encoding="utf-8")
        self.assertIn('"desktop.py"', spec)
        self.assertIn("console=False", spec)
        self.assertIn('"webview.platforms.edgechromium"', spec)
        self.assertNotIn("desktop_workspace", spec)
        self.assertNotIn("prototypes", spec)
        source = (ROOT / "studio/desktop.py").read_text(encoding="utf-8")
        self.assertNotIn("windows-prototype", source)
        self.assertNotIn("APK_CLEANER_DATA_ROOT\"] =", source)
        self.assertIn('storage_path=str(engine.DATA_ROOT / "desktop-webview")', source)

    def test_real_routes_remain_available_and_close_stops_only_owned_children(self):
        original = engine.subprocess
        with tempfile.TemporaryDirectory(prefix="native-desktop-") as directory, \
             mock.patch.object(server, "JOBS", Path(directory) / "jobs"), \
             mock.patch.object(server, "cleanup_stale_jobs"), \
             mock.patch.object(server, "_ACTIVE_JOBS", set()), \
             mock.patch.object(server, "_SCANNING_JOBS", set()), \
             mock.patch.object(server, "_JOB_CANCEL_EVENTS", {}), \
             mock.patch.object(server, "_INTERRUPTED_STATE_FALLBACKS", {}), \
             mock.patch.object(server, "check_for_updates", return_value={"available": False}) as update, \
             mock.patch.object(server, "install_tools", return_value={"ready": True}) as setup:
            host = desktop.DesktopHost(server, engine, port=0)
            host.start()
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            try:
                with opener.open(host.url) as response:
                    body = response.read()
                    self.assertIn(b'data-desktop-native="true"', body)
                    self.assertNotIn(b'desktop-workspace', body)
                with opener.open(host.url + "boot.js") as response:
                    self.assertIn(b'Native loopback window', response.read())
                with opener.open(host.url + "api/update") as response:
                    self.assertFalse(json.load(response)["available"])
                update.assert_called_once_with(server.VERSION)
                with opener.open(urllib.request.Request(host.url + "api/setup", data=b'{}', method="POST")) as response:
                    self.assertTrue(json.load(response)["ready"])
                setup.assert_called_once()
                for headers in ({"Host": "evil.example"}, {"Origin": "https://evil.example"}, {"Host": "[broken"}):
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        opener.open(urllib.request.Request(host.url + "api/status", headers=headers))
                    self.assertEqual(error.exception.code, 403)
                server._ACTIVE_JOBS.add("example")
                event = threading.Event()
                server._JOB_CANCEL_EVENTS["example"] = event
                self.assertFalse(host.accept_close(lambda: False))
                self.assertFalse(host.tools.closing.is_set())
                child = host.tools.Popen([sys.executable, "-c", "import time; time.sleep(120)"],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.assertTrue(host.accept_close(lambda: True))
                with self.assertRaises(InterruptedError):
                    host.tools.Popen([sys.executable, "-c", "pass"])
                host.stop()
                self.assertIsNotNone(child.poll())
                self.assertTrue(event.is_set())
                self.assertIs(engine.subprocess, original)
                self.assertFalse(host.thread.is_alive())
                host.stop()
            finally:
                host.stop()

    def test_update_shutdown_closes_window_without_leaving_gui_process_waiting(self):
        with tempfile.TemporaryDirectory(prefix="desktop-update-") as directory, \
             mock.patch.object(server, "JOBS", Path(directory) / "jobs"), \
             mock.patch.object(server, "cleanup_stale_jobs"), \
             mock.patch.object(server, "_INTERRUPTED_STATE_FALLBACKS", {}), \
             mock.patch.object(server, "stage_update", return_value={"status": "restarting", "shutdown": True}) as stage:
            host = desktop.DesktopHost(server, engine, port=0)
            host.start()
            window = mock.Mock()
            watcher = threading.Thread(target=host.watch_shutdown, args=(window,), daemon=True)
            watcher.start()
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(urllib.request.Request(host.url + "api/update/apply", data=b'{}', method="POST")) as response:
                    self.assertEqual(json.load(response)["status"], "restarting")
                self.assertTrue(host.server_stopped.wait(4))
                watcher.join(timeout=2)
                stage.assert_called_once_with(server.VERSION)
                window.destroy.assert_called_once()
            finally:
                host.stop()


if __name__ == "__main__":
    unittest.main()
