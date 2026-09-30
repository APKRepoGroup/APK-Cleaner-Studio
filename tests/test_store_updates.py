"""Real binary AXML tests; no network, emulator, signing keys or APK build."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "studio"))
import engine
import server


class StoreUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        java_home = Path(os.environ.get("JAVA_HOME", ""))
        bundled = ROOT / ".tools/temurin-21/jdk-21.0.12.1+1"
        if bundled.is_dir():
            java_home = bundled
        suffix = ".exe" if os.name == "nt" else ""
        cls.java = str(java_home / "bin" / ("java" + suffix)) if java_home.is_dir() else shutil.which("java")
        javac = str(java_home / "bin" / ("javac" + suffix)) if java_home.is_dir() else shutil.which("javac")
        if not cls.java or not javac:
            raise unittest.SkipTest("JDK required for binary manifest integration tests")
        cls.temp = tempfile.TemporaryDirectory(prefix="store-updates-test-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.classes = Path(cls.temp.name)
        cls.editor = ROOT / "studio/tools/APKEditor.jar"
        cls.patcher = ROOT / "studio/tools/binary-xml-patcher.jar"
        cls.classpath = os.pathsep.join(map(str, (cls.classes, cls.editor, cls.patcher)))
        subprocess.run([javac, "-cp", str(cls.editor), "-d", str(cls.classes),
                        str(ROOT / "tests/StoreUpdateManifestFixture.java")], check=True, capture_output=True)

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="store-updates-case-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source, self.output = self.root / "source.bin", self.root / "output.bin"
        self.tools = mock.Mock(java=self.java, apkeditor=self.editor, binary_manifest_patcher=self.patcher)

    def java_run(self, *args):
        return subprocess.run([self.java, "-cp", self.classpath, "StoreUpdateManifestFixture", *map(str, args)],
                              check=True, capture_output=True, text=True).stdout.strip()

    def fixture(self, code=42, major=0, kind="decimal"):
        self.java_run("write", self.source, kind, code, major)

    def patch(self, selected=True, **kwargs):
        return engine.patch_manifest_binary(self.source, self.output, self.tools, set(), [],
                                            restrict_store_updates=selected, **kwargs)

    def test_opt_in_raises_code_and_preserves_package_name_and_visible_version(self):
        self.fixture(42, 7)
        metadata = self.patch()["store_updates"]
        self.assertEqual(metadata, {"version_code_before": 42, "version_code_after": 2100000000,
                                    "version_code_major": 7, "changed": True})
        self.assertEqual(engine.inspect_manifest_version(self.output.read_bytes(), self.tools), (2100000000, 7))
        self.assertEqual(self.java_run("read", self.output), "com.example.fixture\t1.2.3")

    def test_default_off_does_not_change_version(self):
        self.fixture(123, 2)
        self.assertIsNone(self.patch(False)["store_updates"])
        self.assertEqual(engine.inspect_manifest_version(self.output.read_bytes(), self.tools), (123, 2))

    def test_already_high_version_is_never_lowered(self):
        for code in (2100000000, 2100000001, 2147483647):
            with self.subTest(code=code):
                self.fixture(code)
                self.assertFalse(self.patch()["store_updates"]["changed"])
                self.assertEqual(engine.inspect_manifest_version(self.output.read_bytes(), self.tools), (code, 0))

    def test_missing_and_hexadecimal_codes_are_supported(self):
        for kind, before in (("missing", 0), ("hex", 43)):
            with self.subTest(kind=kind):
                self.fixture(before, kind=kind)
                self.assertEqual(self.patch()["store_updates"]["version_code_before"], before)

    def test_unsafe_code_types_and_negative_codes_fail_closed(self):
        for kind, code in (("string", 42), ("reference", 42), ("decimal", -1)):
            with self.subTest(kind=kind):
                self.fixture(code, kind=kind)
                with self.assertRaises(RuntimeError):
                    self.patch()

    def test_clone_and_ad_manifest_cleanup_can_be_combined(self):
        self.fixture()
        result = engine.patch_manifest_binary(self.source, self.output, self.tools, {"google_ads"}, [],
                     clone_package_name="com.example.fixture.clone", restrict_store_updates=True)
        self.assertGreater(result["count"], 0)
        self.assertEqual(self.java_run("read", self.output), "com.example.fixture.clone\t1.2.3")
        self.assertEqual(engine.inspect_manifest_version(self.output.read_bytes(), self.tools), (2100000000, 0))

    def test_final_output_rejects_lost_version_patch(self):
        self.fixture()
        apk = self.root / "lost-patch.apk"
        with zipfile.ZipFile(apk, "w") as archive:
            archive.writestr("AndroidManifest.xml", self.source.read_bytes())
            archive.writestr("classes.dex", b"fixture dex")
        with self.assertRaisesRegex(RuntimeError, "sürüm kodu korunmadı"):
            engine.verify_output_apk(apk, apk, self.tools, [], expected_version=(2100000000, 0))

    def test_version_only_processing_patches_final_archive_without_dex_changes(self):
        self.fixture()
        apk = self.root / "source.apk"
        with zipfile.ZipFile(apk, "w") as archive:
            archive.writestr("AndroidManifest.xml", self.source.read_bytes())
            archive.writestr("classes.dex", b"fixture dex")
        report = {"filename": "source.apk", "package_name": "com.example.fixture", "size": apk.stat().st_size,
                  "sha256": "fixture", "dex": [{"name": "classes.dex", "networks": []}], "dex_count": 1,
                  "detections": [], "network_count": 0, "manifest_hits": {}, "layout_hits": [],
                  "install_source_checks": [], "suspicious_files": [], "toolchain": {}, "warnings": []}
        self.tools.status.return_value = dict(clean_ready=True, resource_tool=True, manifest_tool=True, signer=True)
        def fake_sign(source, output, *_args, **_kwargs):
            shutil.copyfile(source, output)
            return True, None
        with mock.patch("engine.Toolchain.detect", return_value=self.tools), mock.patch(
                "engine.sign_apk", side_effect=fake_sign), mock.patch("engine.verify_output_apk", return_value={"passed": True, "signature_tool": "fixture"}) as verify, mock.patch(
                "engine._process_one_dex") as dex:
            result = engine.process_apk(apk, self.root / "result", patch_ads=False,
                                        analysis_report=report, restrict_store_updates=True)
        dex.assert_not_called()
        self.assertEqual(result["operation"], "patch")
        self.assertEqual(verify.call_args.kwargs["expected_version"], (2100000000, 0))
        with zipfile.ZipFile(self.root / "result" / result["output"]) as archive:
            self.assertEqual(archive.read("classes.dex"), b"fixture dex")
            self.assertEqual(engine.inspect_manifest_version(archive.read("AndroidManifest.xml"), self.tools), (2100000000, 0))

    def test_server_forwards_only_boolean_opt_in(self):
        for value in (True, False, "true", 1):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as temp, mock.patch("server.JOBS", Path(temp)):
                job_id = "c" * 32
                job = Path(temp) / job_id
                job.mkdir()
                (job / "source.apk").write_bytes(b"fixture")
                server.write_json(job / "analysis.json", {"filename": "source.apk", "source_path": "source.apk", "prepared_path": "source.apk"})
                with mock.patch("server.process_apk", return_value={"signed": True}) as process:
                    server._execute_clean_job(job_id, {"patch_ads": False, "restrict_store_updates": value})
                if isinstance(value, bool):
                    self.assertIs(process.call_args.kwargs["restrict_store_updates"], value)
                    self.assertEqual(server.read_json(job / "state.json")["status"], "done")
                else:
                    process.assert_not_called()
                    self.assertEqual(server.read_json(job / "state.json")["status"], "error")
