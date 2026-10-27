import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packaging"))
from release_integrity import PLATFORMS, prepare_release, verify_release


class ReleaseChecksumTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.version = "0.6.3-dev.7"
        (self.root / "outputs").mkdir()
        (self.root / "package.json").write_text(json.dumps({"version": self.version}), encoding="utf-8")
        (self.root / f"RELEASE-NOTES-v{self.version}.md").write_text("Build notes", encoding="utf-8")
        for platform, extension in PLATFORMS:
            self.artifact(platform, extension).write_bytes(platform.encode())
        self.checksums = self.root / "outputs" / f"SHA256-v{self.version}.txt"

    def artifact(self, platform, extension):
        return self.root / "outputs" / f"APK-Cleaner-Studio-v{self.version}-{platform}.{extension}"

    def test_prepares_exact_three_file_list_and_verifies_without_touching_packages(self):
        before = {path.name: path.read_bytes() for path in (self.root / "outputs").iterdir()}
        snapshot = prepare_release(self.root)
        self.assertEqual(verify_release(self.root), snapshot)
        self.assertEqual(len(self.checksums.read_text().splitlines()), 3)
        for name, payload in before.items():
            self.assertEqual((self.root / "outputs" / name).read_bytes(), payload)

    def test_old_windows_checksum_is_rejected_even_when_other_hashes_match(self):
        snapshot = prepare_release(self.root)
        old = self.checksums.read_text()
        self.checksums.write_text(old.replace(snapshot["artifacts"]["Windows"]["sha256"].upper(), "F" * 64), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "SHA-256 listesi"):
            verify_release(self.root)

    def test_changed_same_size_package_cannot_be_silently_snapshotted_again(self):
        prepare_release(self.root)
        self.artifact("Windows", "exe").write_bytes(b"changed")
        with self.assertRaisesRegex(RuntimeError, "değişmiş"):
            prepare_release(self.root)
        prepare_release(self.root, refresh=True)
        verify_release(self.root)

    def test_missing_or_empty_packages_do_not_generate_a_checksum_file(self):
        self.artifact("Android", "apk").unlink()
        with self.assertRaises(RuntimeError):
            prepare_release(self.root)
        self.assertFalse(self.checksums.exists())
        self.artifact("Android", "apk").write_bytes(b"")
        with self.assertRaisesRegex(RuntimeError, "boş"):
            prepare_release(self.root)

    def test_final_notes_can_gain_commit_links_without_changing_tested_package_snapshot(self):
        snapshot = prepare_release(self.root)
        (self.root / f"RELEASE-NOTES-v{self.version}.md").write_text("Final links", encoding="utf-8")
        self.assertEqual(verify_release(self.root), snapshot)

    def test_existing_package_audit_also_checks_the_new_checksum_snapshot(self):
        from package_audit import release_build_snapshot
        snapshot = prepare_release(self.root)
        self.assertEqual(release_build_snapshot(self.root), snapshot)
        self.checksums.write_bytes(b"old checksum")
        with self.assertRaisesRegex(RuntimeError, "SHA-256"):
            release_build_snapshot(self.root)

    def test_wrong_versions_and_path_injection_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "sürümü"):
            prepare_release(self.root, "../private")
        prepare_release(self.root)
        path = self.root / "release-assets" / f"v{self.version}" / "package-manifest.json"
        snapshot = json.loads(path.read_text())
        snapshot["artifacts"]["Windows"]["filename"] = "../private.exe"
        path.write_text(json.dumps(snapshot), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "geçersiz"):
            verify_release(self.root)


if __name__ == "__main__":
    unittest.main()
