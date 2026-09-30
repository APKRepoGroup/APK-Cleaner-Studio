import sys
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "studio"))

from updater import (
    GITHUB_API_URL,
    GITHUB_RELEASES_API_URL,
    check_for_updates,
    fetch_remote_update,
    find_local_update,
    manifest_url,
    version_tuple,
)


class UpdaterTests(unittest.TestCase):
    def test_semantic_version_comparison(self):
        self.assertGreater(version_tuple("0.10.0"), version_tuple("0.9.9"))
        self.assertGreater(version_tuple("0.6.3"), version_tuple("0.6.3-dev.7"))
        self.assertGreater(version_tuple("0.6.3-dev.2"), version_tuple("0.6.3-dev.1"))

    def test_newest_local_release_is_selected(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            for version in ("0.3.2", "0.4.1", "0.5.0"):
                (folder / f"APK-Cleaner-Studio-v{version}-Windows.exe").touch()
            (folder / "unrelated.exe").touch()
            update = find_local_update("0.4.0", folder)
            self.assertIsNotNone(update)
            self.assertEqual(update["latest_version"], "0.5.0")
            self.assertEqual(update["source"], "local")

    def test_no_notification_for_current_or_older_files(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            (folder / "APK-Cleaner-Studio-v0.4.0-Windows.exe").touch()
            self.assertIsNone(find_local_update("0.4.0", folder))

    def test_stable_local_install_ignores_dev_executable(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            (folder / "APK-Cleaner-Studio-v0.6.3-dev.7-Windows.exe").touch()
            self.assertIsNone(find_local_update("0.6.2", folder))
            self.assertEqual(find_local_update("0.6.3-dev.1", folder)["latest_version"], "0.6.3-dev.7")

    def test_manifest_requires_https(self):
        with mock.patch.dict(os.environ, {"APK_CLEANER_UPDATE_URL": "http://example.test/update.json"}):
            self.assertIsNone(manifest_url())
        with mock.patch.dict(os.environ, {"APK_CLEANER_UPDATE_URL": "https://example.test/update.json"}):
            self.assertEqual(manifest_url(), "https://example.test/update.json")

    def test_github_latest_selects_android_asset_and_digest(self):
        payload = json.dumps({
            "tag_name": "v0.6.3",
            "draft": False,
            "prerelease": False,
            "html_url": "https://github.com/APKRepoGroup/APK-Cleaner-Studio/releases/tag/v0.6.3",
            "published_at": "2026-09-22T10:00:00Z",
            "body": "## 0.6.3\n\n### İyileştirmeler\n- Güncelleme düzeltildi.",
            "assets": [{
                "name": "APK-Cleaner-Studio-v0.6.3-Android.apk",
                "state": "uploaded",
                "size": 123456,
                "digest": "sha256:" + "a" * 64,
                "browser_download_url": "https://github.com/APKRepoGroup/APK-Cleaner-Studio/releases/download/v0.6.3/APK-Cleaner-Studio-v0.6.3-Android.apk",
            }],
        }).encode()
        with mock.patch.dict(os.environ, {"APK_CLEANER_ANDROID": "1"}), mock.patch(
            "updater.urllib.request.urlopen", return_value=io.BytesIO(payload)
        ):
            update = fetch_remote_update("0.6.2", GITHUB_API_URL)
        self.assertEqual(update["latest_version"], "0.6.3")
        self.assertEqual(update["sha256"], "a" * 64)
        self.assertEqual(update["install_mode"], "android")
        self.assertTrue(update["automatic"])
        self.assertEqual(update["release_notes"], "## 0.6.3\n\n### İyileştirmeler\n- Güncelleme düzeltildi.")
        self.assertNotIn("GitHub", update["notes"])
        self.assertEqual(update["notes"], "Yeni sürüm kullanıma hazır. Güncelleme notlarına aşağıdan ulaşabilirsiniz.")

    def test_prerelease_is_never_offered_as_stable_update(self):
        payload = json.dumps({"tag_name": "v0.6.4-dev.1", "draft": False, "prerelease": True, "assets": []}).encode()
        with mock.patch("updater.urllib.request.urlopen", return_value=io.BytesIO(payload)):
            self.assertIsNone(fetch_remote_update("0.6.3", GITHUB_API_URL))

    def test_dev_channel_selects_newest_prerelease(self):
        def release(version, *, prerelease=True):
            filename = f"APK-Cleaner-Studio-v{version}-Android.apk"
            return {
                "tag_name": f"v{version}", "draft": False, "prerelease": prerelease,
                "html_url": f"https://github.com/APKRepoGroup/APK-Cleaner-Studio/releases/tag/v{version}",
                "body": f"### {version}\n- Bu sürümün değişiklikleri.",
                "assets": [{
                    "name": filename, "state": "uploaded", "size": 123456,
                    "digest": "sha256:" + "b" * 64,
                    "browser_download_url": f"https://github.com/APKRepoGroup/APK-Cleaner-Studio/releases/download/v{version}/{filename}",
                }],
            }

        payload = json.dumps([
            release("0.6.4-dev.1"), release("0.6.3-dev.2"), release("0.6.3-dev.7")
        ]).encode()
        with mock.patch.dict(os.environ, {"APK_CLEANER_ANDROID": "1"}), mock.patch(
            "updater.urllib.request.urlopen", return_value=io.BytesIO(payload)
        ):
            update = fetch_remote_update("0.6.3-dev.1", GITHUB_RELEASES_API_URL)
        self.assertEqual(update["latest_version"], "0.6.3-dev.7")
        self.assertEqual(update["release_channel"], "dev")
        self.assertTrue(update["automatic"])
        self.assertIn("0.6.3-dev.7", update["release_notes"])
        self.assertEqual(update["notes"], "Yeni test sürümü kullanıma hazır. Güncelleme notlarına aşağıdan ulaşabilirsiniz.")
        self.assertNotIn("GitHub", update["notes"])

    def test_legacy_release_notes_are_separate_from_notification_description(self):
        payload = json.dumps({"version": "0.6.3", "notes": "### Yeni özellikler\n- Örnek özellik."}).encode()
        with mock.patch("updater.urllib.request.urlopen", return_value=io.BytesIO(payload)):
            update = fetch_remote_update("0.6.2", "https://example.test/update.json")
        self.assertEqual(update["release_notes"], "### Yeni özellikler\n- Örnek özellik.")
        self.assertNotIn("Örnek özellik", update["notes"])
        self.assertEqual(update["notes"], "Yeni sürüm kullanıma hazır. Güncelleme notlarına aşağıdan ulaşabilirsiniz.")

    def test_release_notes_missing_or_oversized_are_handled(self):
        for body in (None, "x" * 40000):
            with self.subTest(body_length=len(body or "")):
                payload = json.dumps({
                    "version": "0.6.3", "release_notes": body,
                }).encode()
                with mock.patch("updater.urllib.request.urlopen", return_value=io.BytesIO(payload)):
                    update = fetch_remote_update("0.6.2", "https://example.test/update.json")
                self.assertEqual(update["release_notes"], (body or "")[:32000])

    def test_dev_channel_prefers_same_numbered_stable_release(self):
        def release(version, prerelease):
            filename = f"APK-Cleaner-Studio-v{version}-Android.apk"
            return {
                "tag_name": f"v{version}", "draft": False, "prerelease": prerelease,
                "assets": [{
                    "name": filename, "state": "uploaded", "size": 123456,
                    "digest": "sha256:" + "c" * 64,
                    "browser_download_url": f"https://github.com/APKRepoGroup/APK-Cleaner-Studio/releases/download/v{version}/{filename}",
                }],
            }

        payload = json.dumps([release("0.6.3-dev.7", True), release("0.6.3", False)]).encode()
        with mock.patch.dict(os.environ, {"APK_CLEANER_ANDROID": "1"}), mock.patch(
            "updater.urllib.request.urlopen", return_value=io.BytesIO(payload)
        ):
            update = fetch_remote_update("0.6.3-dev.2", GITHUB_RELEASES_API_URL)
        self.assertEqual(update["latest_version"], "0.6.3")
        self.assertEqual(update["release_channel"], "stable")

    def test_dev_build_can_move_to_same_numbered_stable_release(self):
        update = {"latest_version": "0.6.3", "available": True}
        with mock.patch("updater.find_local_update", return_value=None), mock.patch(
            "updater.fetch_remote_update", return_value=update
        ) as remote:
            result = check_for_updates("0.6.3-dev.1")
        remote.assert_called_once()
        self.assertEqual(remote.call_args.args[1], GITHUB_RELEASES_API_URL)
        self.assertTrue(result["available"])
        self.assertEqual(result["channel"], "dev")


if __name__ == "__main__":
    unittest.main()
