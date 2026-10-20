import importlib.util
from pathlib import Path
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
import engine
import server

spec = importlib.util.spec_from_file_location("desktop_prototype_test", ROOT / "prototypes/windows/desktop_preview.py")
prototype = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prototype)


class WindowsPrototypeTests(unittest.TestCase):
    def test_navigation_is_restricted_to_the_owned_loopback_origin(self):
        origin = "http://127.0.0.1:18082/"
        for url in (origin, origin + "?capture=demo", origin + "api/status", "about:blank"):
            self.assertTrue(prototype.internal_url(url, origin), url)
        for url in ("https://github.com/", "http://127.0.0.1:18081/", "http://localhost:18082/",
                    "file:///C:/private.txt", "javascript:alert(1)", "http://user@127.0.0.1:18082/",
                    "http://127.0.0.1:wrong/", "https://127.0.0.1:18082/"):
            self.assertFalse(prototype.internal_url(url, origin), url)

    def test_owned_backend_disables_updates_downloads_and_closes_only_owned_tools(self):
        original_subprocess = engine.subprocess
        with tempfile.TemporaryDirectory(prefix="window-prototype-") as directory:
            with mock.patch.object(server, "JOBS", Path(directory) / "jobs"), \
                 mock.patch.object(server, "_ACTIVE_JOBS", set()), \
                 mock.patch.object(server, "_SCANNING_JOBS", set()), \
                 mock.patch.object(server, "_JOB_CANCEL_EVENTS", {}), \
                 mock.patch.object(server, "_INTERRUPTED_STATE_FALLBACKS", {}), \
                 mock.patch.object(server, "check_for_updates") as update_check, \
                 mock.patch.object(server, "install_tools") as install:
                host = prototype.PrototypeHost(server, engine, port=0)
                host.start()
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                try:
                    with opener.open(host.url + "api/update") as response:
                        self.assertEqual(response.status, 200)
                        self.assertIn(b'"available": false', response.read())
                    with opener.open(host.url) as response:
                        policies = response.headers.get_all("Content-Security-Policy")
                        self.assertTrue(any("connect-src 'self'; object-src" in value for value in policies))
                        self.assertIn(b'desktop-prototype.css', response.read())
                    with opener.open(host.url + "boot.js") as response:
                        self.assertIn(b'No LAN HTTPS probe in the native prototype', response.read())
                    for route in ("api/update/apply", "api/setup"):
                        with self.assertRaises(urllib.error.HTTPError) as error:
                            opener.open(urllib.request.Request(host.url + route, data=b'{}', method="POST"))
                        self.assertEqual(error.exception.code, 409)
                    request = urllib.request.Request(host.url + "api/update", headers={"Host": "evil.example"})
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        opener.open(request)
                    self.assertEqual(error.exception.code, 403)
                    update_check.assert_not_called()
                    install.assert_not_called()
                    # Window close must not stop an active job without approval.
                    server._ACTIVE_JOBS.add("example-job")
                    event = threading.Event()
                    server._JOB_CANCEL_EVENTS["example-job"] = event
                    self.assertFalse(host.accept_close(lambda: False))
                    self.assertFalse(host.tools.closing.is_set())
                    child = host.tools.Popen([sys.executable, "-c", "import time;time.sleep(120)"],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.assertTrue(host.accept_close(lambda: True))
                    with self.assertRaises(InterruptedError):
                        host.tools.Popen([sys.executable, "-c", "pass"])
                    host.stop()
                    self.assertIsNotNone(child.poll())
                    self.assertTrue(event.is_set())
                    self.assertFalse(host.thread.is_alive())
                    self.assertIsNone(server._ACTIVE_SERVER)
                    self.assertIs(engine.subprocess, original_subprocess)
                    host.stop()  # repeated shutdown is safe
                finally:
                    host.stop()

    def test_console_distribution_and_old_launchers_are_not_replaced(self):
        # Dev.6 now promotes preview v1 into the console-free distribution;
        # source console launchers remain available for diagnostics/Termux.
        self.assertIn("console=False", (ROOT / "packaging/APK-Cleaner-Studio-Windows.spec").read_text(encoding="utf-8"))
        self.assertIn('studio\\server.py" --open', (ROOT / "start.ps1").read_text(encoding="utf-8"))
        self.assertIn('"%~dp0start.ps1"', (ROOT / "APK-Cleaner-Studio.bat").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
