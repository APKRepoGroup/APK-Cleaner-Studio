import io
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "studio"))
import server
from package_info import manifest_fields


class PackageComparisonTests(unittest.TestCase):
    def setUp(self):
        self.paths = []
        self.handler = server.StudioHandler.__new__(server.StudioHandler)
        self.handler.path = "/api/compare/analyze"
        self.handler.client_address = ("127.0.0.1", 12345)
        self.handler.headers = {"Host": "127.0.0.1:8080", "Content-Length": "2"}
        self.handler.rfile = io.BytesIO(b"{}")
        self.handler.request_origin_allowed = Mock(return_value=True)
        self.handler.requester_is_blocked = Mock(return_value=False)
        self.handler.redirect_secure_http = Mock(return_value=False)
        self.handler.send_json = Mock()
        self.handler.send_error = Mock()
        self.handler.receive_multipart_upload = Mock(side_effect=self.upload)
        self.slots = threading.BoundedSemaphore(1)
        self.patch = patch("server._ANALYZE_SLOTS", self.slots)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def upload(self, directory):
        self.paths.append(directory)
        source = directory / "example.apk"
        source.write_bytes(b"fixture")
        return source.name, source, "a" * 64

    def test_read_only_analysis_creates_no_history_and_cleans_temporary_files(self):
        report = {"package_name": "com.example", "package_info": {"version_code": 12}, "size": 7, "sha256": "a" * 64,
                  "dex_count": 1, "detections": [], "app_icon": "large", "toolchain": {"path": "private"}}
        with patch("server.inspect_apk", return_value=report) as inspect, patch("server.write_json") as write:
            self.handler.do_POST()
        inspect.assert_called_once()
        write.assert_not_called()
        result = self.handler.send_json.call_args.args[0]
        self.assertNotIn("job_id", result)
        self.assertNotIn("app_icon", result["analysis"])
        self.assertNotIn("toolchain", result["analysis"])
        self.assertTrue(all(not path.exists() for path in self.paths))
        self.assertTrue(self.slots.acquire(blocking=False))

    def test_invalid_packages_clean_up_and_release_the_slot(self):
        with patch("server.inspect_apk", side_effect=ValueError("Geçersiz APK dosyası.")):
            self.handler.do_POST()
        self.assertEqual(self.handler.send_json.call_args.args[1], 400)
        self.assertFalse(self.paths[0].exists())
        self.assertTrue(self.slots.acquire(blocking=False))

    def test_concurrent_upload_limit_is_shared_with_regular_analysis(self):
        self.slots.acquire()
        self.handler.do_POST()
        self.handler.receive_multipart_upload.assert_not_called()
        self.assertEqual(self.handler.send_json.call_args.args[1], 429)

    def test_cross_origin_upload_is_rejected_before_reading_file(self):
        self.handler.request_origin_allowed.return_value = False
        self.handler.do_POST()
        self.handler.receive_multipart_upload.assert_not_called()
        self.assertEqual(self.handler.send_json.call_args.args[1], 403)

    def test_manifest_version_codes_are_bounded_and_not_fabricated(self):
        for value, expected in [("42", 42), ("2147483647", 2147483647), ("9999999999", None), ("@integer/code", None), ("-1", None)]:
            data = f'<manifest xmlns:android="http://schemas.android.com/apk/res/android" android:versionCode="{value}" android:versionCodeMajor="2"/>'.encode()
            result = manifest_fields(data)
            self.assertEqual(result["version_code"], expected)
            self.assertEqual(result["version_code_major"], 2)


if __name__ == "__main__":
    unittest.main()
