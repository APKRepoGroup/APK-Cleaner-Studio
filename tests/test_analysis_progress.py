import io
from http.client import HTTPConnection
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import zipfile
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "studio"))
from analysis_sessions import AnalysisCancelled, AnalysisSessions
import engine
import server


class AnalysisSessionTests(unittest.TestCase):
    def test_sessions_are_private_and_cancel_is_scoped_to_owner(self):
        registry = AnalysisSessions()
        first = registry.begin("a" * 32, "owner")
        second = registry.begin("b" * 32, "other")
        registry.update(first, "classes.dex tarandı (1/2)", 37)
        self.assertIsNone(registry.snapshot("a" * 32, "other"))
        self.assertFalse(registry.cancel("a" * 32, "other"))
        self.assertTrue(registry.cancel("a" * 32, "owner"))
        with self.assertRaises(AnalysisCancelled):
            registry.check(first)
        registry.check(second)
        self.assertNotIn("owner", registry.snapshot("a" * 32, "owner"))
        registry.finish("a" * 32, first)
        self.assertIsNone(registry.snapshot("a" * 32, "owner"))

    def test_cancel_before_upload_registration_cannot_start_late_work(self):
        registry = AnalysisSessions()
        self.assertTrue(registry.cancel("a" * 32, "owner"))
        with self.assertRaises(AnalysisCancelled):
            registry.begin("a" * 32, "owner")
        with self.assertRaises(PermissionError):
            registry.begin("a" * 32, "other")
        self.assertFalse(registry.cancel("../invalid", "owner"))

    def test_pending_cancellations_and_active_scans_are_bounded(self):
        registry = AnalysisSessions()
        for number in range(64):
            self.assertTrue(registry.cancel(f"{number:032x}", "owner"))
        self.assertFalse(registry.cancel("f" * 32, "owner"))
        with patch("analysis_sessions.time.monotonic", return_value=10**12):
            self.assertTrue(registry.cancel("f" * 32, "owner"))
        self.assertEqual(len(registry.cancelled), 1)
        registry.begin("a" * 32, "owner")
        registry.begin("b" * 32, "owner")
        with self.assertRaises(ValueError):
            registry.begin("c" * 32, "owner")


class EngineAnalysisProgressTests(unittest.TestCase):
    def make_apk(self, path):
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("AndroidManifest.xml", "<manifest/>")
            for number in range(1, 4):
                archive.writestr(f"classes{number}.dex", b"dex\n035\0" + bytes(120))

    def test_progress_counts_finished_dex_files_and_never_changes_input(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.apk"
            self.make_apk(source)
            original = source.read_bytes()
            events = []
            with patch("engine.inspect_manifest_package", return_value="example.app"):
                report = engine.inspect_apk(source, progress=lambda message, value: events.append((message, value)))
            self.assertEqual(report["dex_count"], 3)
            self.assertTrue(any("(2/3)" in message for message, _ in events))
            self.assertEqual([value for _, value in events], sorted(value for _, value in events))
            self.assertEqual(events[-1][1], 100)
            self.assertEqual(original, source.read_bytes())

    def test_cancellation_stops_between_dex_files_before_manifest_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.apk"
            self.make_apk(source)
            cancelled = threading.Event()
            def check():
                if cancelled.is_set():
                    raise AnalysisCancelled()
            def progress(message, _value):
                if "(1/3)" in message:
                    cancelled.set()
            with patch("engine.inspect_manifest_package") as tool:
                with self.assertRaises(AnalysisCancelled):
                    engine.inspect_apk(source, progress=progress, check_cancel=check)
            tool.assert_not_called()

    def test_split_progress_is_forwarded_and_cancellation_cleans_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.apks"
            base = Path(directory) / "base.apk"
            self.make_apk(base)
            with zipfile.ZipFile(source, "w") as archive:
                archive.write(base, "base.apk")
            inventory = {"modules": [{"name": "base.apk", "kind": "base"}]}
            events = []
            cancelled = threading.Event()
            def progress(message, value):
                events.append((message, value))
                if "(1/3)" in message:
                    cancelled.set()
            def check():
                if cancelled.is_set():
                    raise AnalysisCancelled()
            with self.assertRaises(AnalysisCancelled):
                engine.inspect_split_package(source, inventory, progress, check_cancel=check)
            self.assertTrue(any("Modül 1/1" in message for message, _ in events))


class AnalysisHandlerTests(unittest.TestCase):
    def setUp(self):
        self.registry = AnalysisSessions()
        self.registry_patch = patch("server._ANALYSIS_SESSIONS", self.registry)
        self.registry_patch.start()
        self.slots = threading.BoundedSemaphore(1)
        self.slot_patch = patch("server._ANALYZE_SLOTS", self.slots)
        self.slot_patch.start()
        self.handler = server.StudioHandler.__new__(server.StudioHandler)
        self.handler.path = "/api/analyze"
        self.handler.headers = {"Host": "127.0.0.1:8080", "X-Analysis-ID": "a" * 32}
        self.handler.client_address = ("127.0.0.1", 1)
        self.handler.requester_id = Mock(return_value="owner")
        self.handler.request_origin_allowed = Mock(return_value=True)
        self.handler.requester_is_blocked = Mock(return_value=False)
        self.handler.redirect_secure_http = Mock(return_value=False)
        self.handler.send_json = Mock()
        self.handler.send_error = Mock()

    def tearDown(self):
        self.slot_patch.stop()
        self.registry_patch.stop()

    def upload(self, directory):
        source = directory / "input.apk"
        source.write_bytes(b"fixture")
        return source.name, source, "a" * 64

    def test_cancelled_scan_removes_job_and_releases_capacity(self):
        with tempfile.TemporaryDirectory() as directory:
            self.handler.receive_multipart_upload = Mock(side_effect=self.upload)
            def inspect(_source, _digest, progress, check_cancel):
                progress("classes.dex tarandı (1/3)", 26)
                self.assertEqual(self.registry.snapshot("a" * 32, "owner")["progress"], 26)
                self.registry.cancel("a" * 32, "owner")
                check_cancel()
            with patch("server.JOBS", Path(directory)), patch("server.ensure_job_capacity"), patch("server.inspect_apk", side_effect=inspect):
                self.handler.do_POST()
            self.assertEqual(list(Path(directory).iterdir()), [])
        self.assertTrue(self.handler.send_json.call_args.args[0]["cancelled"])
        self.assertEqual(self.registry.active, {})
        self.assertTrue(self.slots.acquire(blocking=False))

    def test_legacy_json_analysis_still_returns_a_ready_job(self):
        self.handler.headers.pop("X-Analysis-ID")
        with tempfile.TemporaryDirectory() as directory:
            self.handler.receive_multipart_upload = Mock(side_effect=self.upload)
            with patch("server.JOBS", Path(directory)), patch("server.ensure_job_capacity"), patch("server.inspect_apk", return_value={"network_count": 0}):
                self.handler.do_POST()
            result = self.handler.send_json.call_args.args[0]
            self.assertIn("job_id", result)
            self.assertEqual(server.read_json(Path(directory) / result["job_id"] / "state.json")["status"], "ready")
        self.assertTrue(self.slots.acquire(blocking=False))

    def test_progress_and_cancel_endpoints_enforce_same_owner_and_origin(self):
        session = self.registry.begin("a" * 32, "other")
        self.handler.path = "/api/analysis/" + "a" * 32
        self.handler.do_GET()
        self.assertEqual(self.handler.send_json.call_args.args[1], 404)
        self.handler.path += "/cancel"
        self.handler.do_POST()
        self.assertEqual(self.handler.send_json.call_args.args[1], 403)
        self.registry.check(session)
        self.handler.request_origin_allowed.return_value = False
        self.handler.do_POST()
        self.assertEqual(self.handler.send_json.call_args.args[1], 403)
        self.registry.check(session)

    def test_pre_cancelled_upload_is_rejected_before_files_are_created(self):
        self.registry.cancel("a" * 32, "owner")
        self.handler.receive_multipart_upload = Mock()
        with patch("server.ensure_job_capacity") as capacity:
            self.handler.do_POST()
        self.handler.receive_multipart_upload.assert_not_called()
        capacity.assert_not_called()
        self.assertTrue(self.handler.send_json.call_args.args[0]["cancelled"])

    def test_upload_checks_cancellation_between_chunks_and_removes_partial_file(self):
        session = self.registry.begin("a" * 32, "owner")
        self.registry.cancel("a" * 32, "owner")
        self.handler._analysis_check = lambda: self.registry.check(session)
        boundary = b"test-boundary"
        body = b'--' + boundary + b'\r\nContent-Disposition: form-data; name="package"; filename="input.apk"\r\n\r\n' + b'x' * 100 + b'\r\n--' + boundary + b'--\r\n'
        self.handler.headers.update({"Content-Type": "multipart/form-data; boundary=test-boundary", "Content-Length": str(len(body))})
        self.handler.rfile = io.BytesIO(body)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(AnalysisCancelled):
                self.handler.receive_multipart_upload(Path(directory))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_threaded_http_can_poll_and_cancel_an_in_flight_upload_request(self):
        class QuietHandler(server.StudioHandler):
            def log_message(self, *_args):
                pass
        reached_scan = threading.Event()
        def inspect(_source, _digest, progress, check_cancel):
            progress("classes.dex tarandı (1/3)", 26)
            reached_scan.set()
            for _ in range(100):
                if self.registry.active["a" * 32]["cancel"].wait(.02):
                    check_cancel()
            raise AssertionError("HTTP iptal isteği taramaya ulaşmadı.")
        body = b'--test\r\nContent-Disposition: form-data; name="package"; filename="input.apk"\r\n\r\nfixture\r\n--test--\r\n'
        replies = []
        with tempfile.TemporaryDirectory() as directory, patch("server.JOBS", Path(directory)), patch("server.ensure_job_capacity"), patch("server.inspect_apk", side_effect=inspect), patch.object(QuietHandler, "requester_id", return_value="owner"):
            httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
            serving = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=.02), daemon=True)
            serving.start()
            port = httpd.server_port
            def upload():
                connection = HTTPConnection("127.0.0.1", port, timeout=4)
                try:
                    connection.request("POST", "/api/analyze", body, {"Content-Type": "multipart/form-data; boundary=test", "X-Analysis-ID": "a" * 32})
                    response = connection.getresponse()
                    replies.append((response.status, json.loads(response.read())))
                finally:
                    connection.close()
            def request(method, path):
                connection = HTTPConnection("127.0.0.1", port, timeout=4)
                try:
                    connection.request(method, path)
                    response = connection.getresponse()
                    return response.status, json.loads(response.read())
                finally:
                    connection.close()
            worker = threading.Thread(target=upload)
            try:
                worker.start()
                self.assertTrue(reached_scan.wait(3))
                status, progress = request("GET", "/api/analysis/" + "a" * 32)
                self.assertEqual((status, progress["progress"]), (200, 26))
                status, result = request("POST", "/api/analysis/" + "a" * 32 + "/cancel")
                self.assertEqual((status, result["cancel_requested"]), (200, True))
                worker.join(4)
                self.assertFalse(worker.is_alive())
                self.assertEqual(replies[0][0], 400)
                self.assertTrue(replies[0][1]["cancelled"])
                self.assertEqual(list(Path(directory).iterdir()), [])
            finally:
                httpd.shutdown()
                httpd.server_close()
                serving.join(2)
                worker.join(4)


if __name__ == "__main__":
    unittest.main()
