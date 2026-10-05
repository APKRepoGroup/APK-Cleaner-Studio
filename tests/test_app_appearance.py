import base64
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "studio"))
import engine
from app_appearance import validate_appearance


def png(width=2, height=2):
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress((b"\0" + b"\xff\0\0\xff" * width) * height)) + chunk(b"IEND", b""))


def image(data=None):
    return "data:image/png;base64," + base64.b64encode(data or png()).decode()


class AppearanceValidationTests(unittest.TestCase):
    def test_opt_in_and_valid_png(self):
        self.assertEqual(validate_appearance(None), {})
        self.assertEqual(validate_appearance({"name": "   ", "icon": ""}), {})
        self.assertEqual(validate_appearance({"name": " Türkçe & <ad> ", "icon": image()})["name"], "Türkçe & <ad>")

    def test_invalid_data_is_rejected(self):
        for value in (False, {"name": []}, {"name": "a" * 81}, {"name": "x\ny"}, {"extra": 1},
                      {"icon": "https://example.org/icon.png"}, {"icon": "data:image/svg+xml;base64,YQ=="},
                      {"icon": image(b"not png")}, {"icon": image(png(513, 1))},
                      {"icon": image(png()[:-1])}, {"icon": image(png() + b"tail")}):
            with self.subTest(value=str(value)[:50]), self.assertRaises(ValueError):
                validate_appearance(value)


class AppearanceBinaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        java_home = Path(os.environ.get("JAVA_HOME", "C:/Program Files/Zulu/zulu-26"))
        cls.java, javac = str(java_home / "bin/java.exe"), str(java_home / "bin/javac.exe")
        if not Path(javac).is_file():
            raise unittest.SkipTest("JDK yok")
        temp = tempfile.TemporaryDirectory(prefix="appearance-java-")
        cls.addClassCleanup(temp.cleanup)
        cls.root = Path(temp.name)
        # A short temporary dependency path also avoids Windows JDK zipfs-close
        # errors on the long workspace path. Never alter the bundled tool JAR.
        cls.editor = cls.root / "editor.jar"
        shutil.copyfile(ROOT / "studio/tools/APKEditor.jar", cls.editor)
        cls.classes = cls.root / "classes"
        cls.classes.mkdir()
        subprocess.run([javac, "--release", "8", "-encoding", "UTF-8", "-cp", str(cls.editor), "-d", str(cls.classes),
                        str(ROOT / "binary-xml-patcher/src/local/apkcleaner/xml/AppAppearancePatcher.java"),
                        str(ROOT / "binary-xml-patcher/src/local/apkcleaner/xml/BinaryManifestPatcher.java"),
                        str(ROOT / "tests/AppAppearanceFixture.java")], check=True, capture_output=True)
        cls.classpath = os.pathsep.join((str(cls.classes), str(cls.editor)))

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="appearance-case-")
        self.addCleanup(temp.cleanup)
        self.case = Path(temp.name)
        self.manifest, self.table = self.case / "manifest.bin", self.case / "table.bin"
        self.run_fixture("write", self.manifest, self.table)
        self.source = self.case / "source.apk"
        with zipfile.ZipFile(self.source, "w") as archive:
            archive.writestr("AndroidManifest.xml", self.manifest.read_bytes())
            archive.writestr("resources.arsc", self.table.read_bytes())
            archive.writestr("classes.dex", b"dex fixture")
            archive.writestr("res/drawable/original.png", png())
            archive.writestr("assets/keep.bin", b"untouched")
        self.tools = mock.Mock(java=self.java, apkeditor=self.editor, binary_manifest_patcher=self.classes)

    def run_fixture(self, *args):
        return subprocess.run([self.java, "-Dfile.encoding=UTF-8", "-Dstdout.encoding=UTF-8", "-cp", self.classpath, "AppAppearanceFixture", *map(str, args)], check=True,
                              capture_output=True, text=True, encoding="utf-8").stdout.strip()

    def test_name_and_icon_retain_existing_resources_and_identity(self):
        output = self.case / "customized.apk"
        result = engine.patch_app_appearance(self.source, output, validate_appearance({"name": "Yeni & <ad>", "icon": image()}), self.tools, [])
        with zipfile.ZipFile(self.source) as before, zipfile.ZipFile(output) as after:
            for name in ("classes.dex", "res/drawable/original.png", "assets/keep.bin"):
                self.assertEqual(before.read(name), after.read(name))
            self.assertEqual(after.read(result["icon_path"]), png())
            self.manifest.write_bytes(after.read("AndroidManifest.xml"))
            self.table.write_bytes(after.read("resources.arsc"))
        lines = self.run_fixture("read", self.manifest, self.table).splitlines()
        fields = lines[0].split("\t")
        self.assertEqual(fields[:4], ["com.example.fixture", "42", "1.2.3", "Yeni & <ad>"])
        self.assertEqual(fields[4], fields[5])
        self.assertEqual(lines[1:], ["Original title", "res/drawable/original.png", "Yeni & <ad>"])
        from package_info import inspect_package_info
        metadata = inspect_package_info(output)
        self.assertEqual((metadata["min_sdk"], metadata["target_sdk"], metadata["version_name"]), (26, 37, "1.2.3"))
        self.assertEqual(metadata["permissions"], ["android.permission.INTERNET"])
        self.assertEqual(engine.extract_apk_icon(output), image())

    def test_name_only_does_not_touch_table_or_icons(self):
        output = self.case / "renamed.apk"
        result = engine.patch_app_appearance(self.source, output, {"name": "Yeni ad"}, self.tools, [])
        self.assertFalse(result["icon_changed"])
        with zipfile.ZipFile(self.source) as before, zipfile.ZipFile(output) as after:
            self.assertEqual(before.read("resources.arsc"), after.read("resources.arsc"))
            self.assertEqual(set(before.namelist()), set(after.namelist()))

    def test_appearance_keeps_clone_and_store_version_edits(self):
        manifest_out = self.case / "identity.bin"
        engine.patch_manifest_binary(self.manifest, manifest_out, self.tools, set(), [],
                                     clone_package_name="com.example.fixture.clone", restrict_store_updates=True)
        staged = self.case / "staged.apk"
        engine.rewrite_apk(self.source, staged, {"AndroidManifest.xml": manifest_out}, set())
        output = self.case / "customized.apk"
        engine.patch_app_appearance(staged, output, {"name": "Klon", "icon": image()}, self.tools, [])
        with zipfile.ZipFile(output) as archive:
            self.manifest.write_bytes(archive.read("AndroidManifest.xml"))
            self.table.write_bytes(archive.read("resources.arsc"))
        self.assertEqual(self.run_fixture("read", self.manifest, self.table).splitlines()[0].split("\t")[:4],
                         ["com.example.fixture.clone", "2100000000", "1.2.3", "Klon"])

    def test_processing_appearance_only_and_final_signer_tampering(self):
        report = {"filename": "source.apk", "package_name": "com.example.fixture", "dex": [{"name": "classes.dex", "networks": []}],
                  "detections": [], "network_count": 0, "manifest_hits": {}, "layout_hits": [], "install_source_checks": []}
        self.tools.status.return_value = {"clean_ready": True, "manifest_tool": True, "signer": True}
        def sign(source, output, *_args, **_kwargs):
            shutil.copyfile(source, output)
            return True, None
        with mock.patch("engine.Toolchain.detect", return_value=self.tools), mock.patch("engine.sign_apk", side_effect=sign), mock.patch(
                "engine.verify_output_apk", return_value={"passed": True, "signature_tool": "fixture"}), mock.patch("engine._process_one_dex") as dex:
            result = engine.process_apk(self.source, self.case / "out", patch_ads=False, analysis_report=report,
                                        app_appearance={"name": "Yeni ad", "icon": image()})
            self.assertEqual(result["app_appearance"]["name"], "Yeni ad")
            dex.assert_not_called()
            def tamper(source, output, *_args, **_kwargs):
                shutil.copyfile(self.source, output)
                return True, None
            with mock.patch("engine.sign_apk", side_effect=tamper), self.assertRaisesRegex(RuntimeError, "adı veya simgesi korunmadı"):
                engine.process_apk(self.source, self.case / "bad", patch_ads=False, analysis_report=report, app_appearance={"name": "Yeni ad"})
