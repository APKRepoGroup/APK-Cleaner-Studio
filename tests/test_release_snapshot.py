import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from package_audit import VERSION, release_build_snapshot


class ReleaseSnapshotTests(unittest.TestCase):
    def test_audits_follow_the_current_source_version(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(VERSION, json.loads((root / "package.json").read_text(encoding="utf-8"))["version"])
        for name in ("final_artifact_workflow_audit.py", "server_load_audit.py"):
            source = (root / "tests" / name).read_text(encoding="utf-8")
            self.assertIn("from package_audit import VERSION", source)
            self.assertNotIn('VERSION = "0.6.3-dev.', source)

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="release-snapshot-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "outputs").mkdir()
        self.manifest = self.root / "release-assets" / f"v{VERSION}" / "package-manifest.json"
        self.manifest.parent.mkdir(parents=True)
        self.data = {"version": VERSION, "artifacts": {}}
        for platform, ext in (("Android", "apk"), ("Windows", "exe"), ("Termux", "zip")):
            name = f"APK-Cleaner-Studio-v{VERSION}-{platform}.{ext}"
            payload = platform.encode()
            (self.root / "outputs" / name).write_bytes(payload)
            self.data["artifacts"][platform] = {"filename": name, "size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}

    def save(self):
        self.manifest.write_text(json.dumps(self.data), encoding="utf-8")

    def test_no_snapshot_retains_existing_audit_behavior(self):
        self.assertIsNone(release_build_snapshot(self.root))

    def test_unchanged_three_packages_are_verified(self):
        self.save()
        self.assertEqual(release_build_snapshot(self.root), self.data)

    def test_modified_bytes_are_rejected_even_at_the_same_size(self):
        self.save()
        entry = self.data["artifacts"]["Android"]
        (self.root / "outputs" / entry["filename"]).write_bytes(b"x" * entry["size_bytes"])
        with self.assertRaisesRegex(RuntimeError, "değişmiş"):
            release_build_snapshot(self.root)

    def test_other_versions_and_arbitrary_paths_are_rejected(self):
        self.data["version"] = "0.0.0"
        self.save()
        with self.assertRaisesRegex(RuntimeError, "sürümü"):
            release_build_snapshot(self.root)
        self.data["version"] = VERSION
        self.data["artifacts"]["Android"]["filename"] = "../other.apk"
        self.save()
        with self.assertRaisesRegex(RuntimeError, "dosya adı"):
            release_build_snapshot(self.root)
