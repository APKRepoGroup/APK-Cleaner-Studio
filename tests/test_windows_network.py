"""Real HTTP/TLS tests, bound only to loopback (never expose the test engine)."""
from contextlib import ExitStack
import json
from pathlib import Path
import socket
import ssl
import sys
import tempfile
import unittest
from unittest import mock
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "studio"))
import desktop
import engine
import server
from desktop_network import private_address


class WindowsNetworkTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="desktop-lan-")))
        self.root = root
        for name, value in {"DATA_ROOT": root, "JOBS": root / "jobs", "LOCAL_CA_PATH": root / "tls/local-root-ca.crt",
                            "CLIENT_LABELS_PATH": root / "labels.json", "CLIENT_BLOCKLIST_PATH": root / "blocks.json",
                            "_CLIENTS": {}, "_CLIENT_LABELS": {}, "_BLOCKED_CLIENTS": set(),
                            "_ACTIVE_JOBS": set(), "_SCANNING_JOBS": set(), "_JOB_CANCEL_EVENTS": {},
                            "_INTERRUPTED_STATE_FALLBACKS": {}}.items():
            self.stack.enter_context(mock.patch.object(server, name, value))
        self.stack.enter_context(mock.patch.object(server, "cleanup_stale_jobs"))
        self.stack.enter_context(mock.patch.object(server, "local_network_ip", return_value="192.168.50.10"))
        self.stack.enter_context(mock.patch.object(server, "_resolve_lan_hostname"))
        self.stack.enter_context(mock.patch.object(server.Toolchain, "detect", return_value=mock.Mock(status=lambda: {})))
        self.stack.enter_context(mock.patch.object(server, "check_for_updates", return_value={"available": False}))
        original = server.StudioServer
        class LoopbackTestServer(original):
            def __init__(listener, address, handler, context):
                self.assertEqual(address[0], "0.0.0.0")
                class PeerHandler(handler):
                    def setup(request):
                        super().setup()
                        request.client_address = ("192.168.50.20", request.client_address[1])
                super().__init__(("127.0.0.1", address[1]), PeerHandler, context)
        self.stack.enter_context(mock.patch.object(server, "StudioServer", LoopbackTestServer))
        self.host = desktop.DesktopHost(server, engine, port=0, lan_port=0)
        self.host.start()
        self.addCleanup(self.host.stop)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def control(self, enabled, origin=True):
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = self.host.url.rstrip("/") if origin is True else origin
        request = urllib.request.Request(self.host.url + "api/desktop/network", data=json.dumps({"enabled": enabled}).encode(), headers=headers)
        with self.opener.open(request, timeout=8) as response:
            return json.load(response)

    def remote(self, path, data=None, headers=None, secure=False):
        port = self.host.network.http.server_port
        address = ("https" if secure else "http") + f"://127.0.0.1:{port}/"
        request = urllib.request.Request(address + path, data=data,
                                         headers={"Host": f"192.168.50.10:{port}", "X-Client-ID": "lan-test-client", **(headers or {})})
        opener = self.opener
        if secure:
            context = ssl.create_default_context(cafile=str(server.LOCAL_CA_PATH))
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))
        with opener.open(request, timeout=8) as response:
            return response.read()

    def test_default_closed_and_control_requires_native_same_origin_and_boolean(self):
        self.assertFalse(self.host.network.state()["enabled"])
        self.assertFalse((self.root / "tls").exists())
        self.assertIsNone(self.host.network.http)
        for origin, value, expected in [(False, True, 403), ("https://evil.example", True, 403), (True, "true", 400)]:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.control(value, origin)
            self.assertEqual(error.exception.code, expected)
        with self.opener.open(self.host.url) as response:
            source = response.read()
            self.assertIn(b'id="desktopNetworkCard"', source)
            self.assertIn(b'/desktop-network.js', source)
        self.assertFalse(self.host.network.state()["enabled"])

    def test_http_https_sessions_and_remote_admin_restrictions(self):
        with mock.patch.object(server, "request_local_https_trust") as trust:
            state = self.control(True)
            trust.assert_not_called()
        self.assertTrue(state["enabled"])
        for secure in (False, True):
            data = json.loads(self.remote("api/status", secure=secure))
            self.assertEqual(len(data["clients"]), 1)
            self.assertFalse(data["clients"][0]["can_manage"])
            self.assertEqual(data["clients"][0]["address"], "192.168.50.20")
        for path in ("api/setup", "api/update/apply", "api/client/manage"):
            with self.assertRaises(urllib.error.HTTPError):
                self.remote(path, b'{"target_id":"x","action":"block"}', {"X-Forwarded-For": "127.0.0.1"})
        for path in ("api/diagnostic", "api/desktop/network"):
            with self.assertRaises(urllib.error.HTTPError):
                self.remote(path)
        for headers in ({"Origin": "https://evil.example"}, {"Host": "evil.example"}, {"Host": "[broken"}):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.remote("api/status", headers=headers)
            self.assertEqual(error.exception.code, 403)
        with self.opener.open(self.host.url + "api/status") as response:
            rows = json.load(response)["clients"]
        peer = next(row for row in rows if not row["local"])
        self.assertTrue(peer["can_manage"])
        data = json.dumps({"target_id": peer["id"], "action": "block"}).encode()
        with self.opener.open(urllib.request.Request(self.host.url + "api/client/manage", data=data)) as response:
            self.assertTrue(json.load(response)["ok"])
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.remote("api/status")
        self.assertEqual(error.exception.code, 403)
        server.load_client_settings()
        self.assertIn(peer["id"], server._BLOCKED_CLIENTS)

    def test_disable_reenable_and_close_release_listener_without_stopping_engine(self):
        self.control(True)
        port = self.host.network.http.server_port
        self.assertFalse(self.control(False)["enabled"])
        self.assertTrue(self.host.thread.is_alive())
        with socket.socket() as connection:
            connection.settimeout(.5)
            self.assertNotEqual(connection.connect_ex(("127.0.0.1", port)), 0)
        self.assertTrue(self.control(True)["enabled"])
        self.host.stop()
        self.assertFalse(self.host.network.state()["enabled"])
        self.assertIsNone(self.host.network.http)

    def test_unavailable_network_or_busy_port_do_not_leave_partial_listener(self):
        with mock.patch.object(server, "local_network_ip", return_value=None):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.control(True)
            self.assertEqual(error.exception.code, 400)
        with mock.patch.object(server, "StudioServer", side_effect=OSError("busy")):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.control(True)
            self.assertEqual(error.exception.code, 503)
        self.assertFalse(self.host.network.state()["enabled"])
        self.assertIsNone(self.host.network.http)

    def test_only_private_unicast_ipv4_peers_are_accepted(self):
        for value in ("192.168.1.2", "10.0.0.4", "172.16.1.4", "127.0.0.1"):
            self.assertTrue(private_address(value))
        for value in ("8.8.8.8", "0.0.0.0", "224.0.0.1", "255.255.255.255", "::1", "invalid"):
            self.assertFalse(private_address(value))

    def test_default_lan_port_is_8080_and_native_origin_is_independent(self):
        host = desktop.DesktopHost(server, engine)
        try:
            self.assertEqual(host.network.port, 8080)
            self.assertEqual(host.http.server_address[0], "127.0.0.1")
            self.assertFalse(host.network.state()["enabled"])
        finally:
            host.stop()


if __name__ == "__main__":
    unittest.main()
