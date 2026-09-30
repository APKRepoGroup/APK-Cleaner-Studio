import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "studio"))
import server


class StartupApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.job_id = "a" * 32
        self.job = self.root / self.job_id
        self.job.mkdir()
        (self.job / "input.apk").write_bytes(b"fixture")
        server.write_json(self.job / "analysis.json", {"prepared_path": "input.apk", "filename": "input.apk"})
        server.write_json(self.job / "state.json", {"status": "ready"})
        self.handler = server.StudioHandler.__new__(server.StudioHandler)
        self.handler.path = f"/api/jobs/{self.job_id}/message-candidates"
        self.handler.client_address = ("127.0.0.1", 12345)
        self.handler.headers = {"Host": "127.0.0.1:8080", "Content-Length": "2"}
        self.handler.rfile = io.BytesIO(b"{}")
        self.handler.redirect_secure_http = Mock(return_value=False)
        self.handler.send_json = Mock()
        self.handler.receive_multipart_upload = Mock(side_effect=AssertionError("Original APK must not be requested"))
        self.roots = patch("server.JOBS", self.root)
        self.roots.start()

    def tearDown(self):
        server._SCANNING_JOBS.discard(self.job_id)
        self.roots.stop()
        self.temp.cleanup()

    def test_json_scan_does_not_require_original_apk_and_persists_only_candidates(self):
        candidates = [{"id": "classes.dex:lc-found", "owner_method": "onCreate"}]
        with patch("server.inspect_startup_calls", return_value=candidates) as scan:
            self.handler.do_POST()
        scan.assert_called_once_with(self.job / "input.apk")
        self.handler.send_json.assert_called_once_with({"candidates": candidates, "count": 1})
        self.assertEqual(server.read_json(self.job / "analysis.json")["approved_message_targets"], ["classes.dex:lc-found"])
        self.assertNotIn(self.job_id, server._SCANNING_JOBS)

    def test_failed_scan_releases_claim_and_returns_error(self):
        with patch("server.inspect_startup_calls", side_effect=ValueError("invalid dex")):
            self.handler.do_POST()
        self.assertNotIn(self.job_id, server._SCANNING_JOBS)
        self.assertEqual(self.handler.send_json.call_args.args,
                         ({"error": "İşlem bileşeni beklenmeyen bir hata nedeniyle tamamlanamadı."}, 400))

    def test_foreign_job_is_not_scanned(self):
        with patch("server.job_visible_to", return_value=False), patch("server.inspect_startup_calls") as scan:
            self.handler.do_POST()
        scan.assert_not_called()
        self.assertEqual(self.handler.send_json.call_args.args[1], 403)

    def test_scan_blocks_processing_and_deletion_until_finished(self):
        server._SCANNING_JOBS.add(self.job_id)
        with self.assertRaisesRegex(ValueError, "taraması"):
            server.start_clean_job(self.job_id, {})
        with self.assertRaisesRegex(ValueError, "taraması"):
            server.delete_job_history(self.job_id, "owner", True)

    def test_split_rescans_use_fresh_temporary_directories(self):
        server.write_json(self.job / "analysis.json", {"split_merged": True, "source_path": "input.apks"})
        paths = []

        def merge(source, output, **kwargs):
            paths.append(output)
            prepared = output / "prepared.apk"
            prepared.write_bytes(b"fixture")
            return prepared, []

        with patch("server.merge_split_package", side_effect=merge), patch("server.inspect_startup_calls", return_value=[]):
            for _ in range(2):
                self.handler.rfile = io.BytesIO(b"{}")
                self.handler.do_POST()
        self.assertEqual(len(paths), 2)
        self.assertNotEqual(paths[0], paths[1])
        self.assertTrue(all(not path.exists() for path in paths))
        self.assertEqual(self.handler.send_json.call_args.args, ({"candidates": [], "count": 0},))


if __name__ == "__main__":
    unittest.main()
