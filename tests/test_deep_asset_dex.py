import hashlib
import json
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "studio"))
import engine
from deep_asset_fixture import AD_DEX, NESTED_AD_DEX, RETAINED_DEX, build_asset_fixture


class DeepAssetDexTests(unittest.TestCase):
    def test_missing_fingerprint_is_turkish(self):
        with tempfile.TemporaryDirectory() as name:
            source = Path(name) / "empty.zip"
            with zipfile.ZipFile(source, "w"):
                pass
            with zipfile.ZipFile(source) as archive:
                with self.assertRaisesRegex(RuntimeError, "APK arşivinde beklenen dosya bulunamadı"):
                    engine._entry_fingerprint(archive, AD_DEX)

    def test_same_basename_has_independent_worker_paths(self):
        names = ("classes.dex", AD_DEX, RETAINED_DEX, "assets/a/b/classes.dex")
        for kind in ("input", "patched", "scanned"):
            paths = [engine._dex_work_path(Path("temp"), kind, name) for name in names]
            self.assertEqual(len(set(paths)), len(names))
            self.assertTrue(all(path.parent == Path("temp") for path in paths))

    def test_unplanned_asset_dex_loss_is_rejected_before_signature(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source, output = root / "source.apk", root / "output.apk"
            with zipfile.ZipFile(source, "w") as archive:
                for entry in ("AndroidManifest.xml", "classes.dex", AD_DEX, RETAINED_DEX):
                    archive.writestr(entry, entry.encode())
            engine.rewrite_apk(source, output, {}, {AD_DEX, RETAINED_DEX})
            with mock.patch("engine.run_checked") as signature:
                with self.assertRaisesRegex(RuntimeError, "DEX bileşeni eksik"):
                    engine.verify_output_apk(source, output, types.SimpleNamespace(apksigner="fixture"), [],
                                             removed_files={AD_DEX})
                signature.assert_not_called()

    def test_real_deep_asset_removal_and_retained_dex_report(self):
        tools = engine.Toolchain.detect()
        if not tools.status()["fully_ready"] or not (ROOT / "work/hello-with-ad-call.apk").is_file():
            self.skipTest("Local integration fixture/toolchain unavailable")
        with tempfile.TemporaryDirectory(prefix="deep-asset-dex-") as name:
            root = Path(name)
            source = build_asset_fixture(root, tools.java)
            source_hash = engine.sha256(source)
            inspection = engine.inspect_apk(source)
            self.assertIn("facebook_ads", {row["id"] for row in inspection["detections"]})
            for mode in ("safe", "balanced", "deep"):
                with self.subTest(mode=mode):
                    result = engine.process_apk(source, root / mode, mode, strip_debug=True,
                                                normalize_dex=True, analysis_report=inspection)
                    self.assertTrue(result["signed"] and result["verification"]["passed"])
                    report = (root / mode / "report.txt").read_text(encoding="utf-8")
                    saved = json.loads((root / mode / "report.json").read_text(encoding="utf-8"))
                    self.assertEqual(saved["changes"], result["changes"])
                    rows = {row["file"]: row for row in result["changes"]["dex"]}
                    with zipfile.ZipFile(source) as before, zipfile.ZipFile(root / mode / result["output"]) as after:
                        self.assertIsNone(after.testzip())
                        self.assertIn(b"AssetKept", after.read(RETAINED_DEX))
                        self.assertNotIn(b"AssetOne", after.read(RETAINED_DEX))
                        self.assertNotIn(b"AssetKept", after.read("classes.dex"))
                        for entry in ("classes.dex", AD_DEX, NESTED_AD_DEX, RETAINED_DEX):
                            row = rows[entry]
                            self.assertEqual(row["before"]["sha256"], hashlib.sha256(before.read(entry)).hexdigest())
                            if mode == "deep" and entry in {AD_DEX, NESTED_AD_DEX}:
                                self.assertNotIn(entry, after.namelist())
                                self.assertTrue(row["removed"])
                                self.assertIsNone(row["after"])
                                self.assertIn(f"{entry}: kaldırıldı", report)
                            else:
                                self.assertEqual(row["after"]["sha256"], hashlib.sha256(after.read(entry)).hexdigest())
                                self.assertFalse(row.get("removed", False))
            self.assertEqual(engine.sha256(source), source_hash)


if __name__ == "__main__":
    unittest.main()
