import errno
import io
import json
import os
from pathlib import Path
import ssl
import sys
import tempfile
import unittest
from unittest import mock
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "studio"))
import updater


class UpdateTransportTests(unittest.TestCase):
    def test_missing_optional_keylog_path_does_not_break_verified_windows_tls(self):
        with tempfile.TemporaryDirectory() as folder:
            missing = str(Path(folder) / "removed" / "sslkeys.log")
            with mock.patch.dict(os.environ, {"SSLKEYLOGFILE": missing}):
                with self.assertRaises(FileNotFoundError):
                    ssl.create_default_context()
                context = updater._windows_https_context()
            self.assertTrue(context.check_hostname)
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertGreaterEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
            self.assertIsNone(context.keylog_filename)
            self.assertFalse(Path(missing).exists())

    def test_metadata_and_download_share_verified_context_on_windows(self):
        response = io.BytesIO(json.dumps({"version": "0.6.3"}).encode())
        with mock.patch.object(updater.os, "name", "nt"), mock.patch.object(updater.urllib.request, "urlopen", return_value=response) as call:
            updater._read_json_response("https://example.test/manifest")
        self.assertTrue(call.call_args.kwargs["context"].check_hostname)
        self.assertEqual(call.call_args.kwargs["context"].verify_mode, ssl.CERT_REQUIRED)

    def test_failed_check_is_not_reported_as_up_to_date_or_raw_english(self):
        failures = (FileNotFoundError(errno.ENOENT, "No such file or directory"),
                    urllib.error.URLError(ssl.SSLError("CERTIFICATE_VERIFY_FAILED")),
                    OSError("Connection refused"))
        for error in failures:
            with self.subTest(error=type(error).__name__), mock.patch.object(updater, "find_local_update", return_value=None), mock.patch.object(updater, "manifest_url", return_value=updater.GITHUB_API_URL), mock.patch.object(updater, "fetch_remote_update", side_effect=error), self.assertLogs("studio.updater", level="WARNING"):
                result = updater.check_for_updates("0.6.3-dev.7")
                self.assertEqual(result["check_status"], "failed")
                self.assertFalse(result["available"])
                self.assertTrue(result["warning"])
                self.assertNotIn(str(error), result["warning"])
