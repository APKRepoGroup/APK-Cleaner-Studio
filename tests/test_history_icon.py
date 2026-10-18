import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "studio"))
import server


class HistoryIconTests(unittest.TestCase):
    def check_reuse(self, *, android=True, split=False, refreshed="new-high-resolution-icon"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / ("b" * 32)
            original.mkdir()
            source = original / "source.apk"
            source.write_bytes(b"original-source-bytes")
            old = {"source_path": "source.apk", "owner_id": "owner", "filename": "Source.apk",
                   "app_icon": "legacy-icon", "split_merged": split}
            server.write_json(original / "analysis.json", old)
            with mock.patch.object(server, "JOBS", root), mock.patch.object(server, "ANDROID_RUNTIME", android), mock.patch.object(server, "extract_apk_icon", return_value=refreshed) as extract:
                new_id, analysis = server.clone_job_for_reuse(original.name, "owner", True)
                self.assertEqual(extract.call_count, int(android and not split))
            self.assertEqual(analysis["app_icon"], refreshed if android and not split and refreshed else "legacy-icon")
            self.assertEqual(server.read_json(original / "analysis.json"), old)
            self.assertEqual(source.read_bytes(), b"original-source-bytes")
            self.assertEqual((root / new_id / "source.apk").read_bytes(), source.read_bytes())

    def test_android_reopened_apk_refreshes_legacy_preview_without_changing_original(self):
        self.check_reuse()

    def test_failed_icon_refresh_preserves_existing_preview(self):
        self.check_reuse(refreshed="")

    def test_desktop_history_does_not_refresh_native_icons(self):
        self.check_reuse(android=False)

    def test_split_history_retains_its_density_resource_preview(self):
        self.check_reuse(split=True)
