import base64
import hashlib
import io
import os
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "studio"))
from package_icon import extract_apk_icon, extract_split_icon, _manifest_icon, _resource_paths, _raster_uri
from engine import inspect_apk, inspect_split_package

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRz0AAAAASUVORK5CYII=")
ICON = "data:image/png;base64," + base64.b64encode(PNG).decode()
PATH = "res/mipmap-xxhdpi-v4/a.png"
RESOURCE = 0x7f010000


def strings(values, utf8=True):
    content, offsets = bytearray(), []
    for value in values:
        offsets.append(len(content))
        encoded = value.encode("utf-8" if utf8 else "utf-16le")
        content += bytes((len(value), len(encoded))) + encoded + b"\0" if utf8 else struct.pack("<H", len(value)) + encoded + b"\0\0"
    content += b"\0" * (-len(content) % 4)
    start = 28 + 4 * len(values)
    return struct.pack("<HHI5I", 1, 28, start + len(content), len(values), 0, 256 if utf8 else 0, start, 0) + struct.pack(f"<{len(values)}I", *offsets) + content


def manifest(resource=RESOURCE, utf8=True):
    pool = strings(["application", "http://schemas.android.com/apk/res/android", "icon"], utf8)
    node = struct.pack("<HHIII", 0x102, 16, 56, 0, 0xffffffff)
    ext = struct.pack("<II6H", 0xffffffff, 0, 20, 20, 1, 0, 0, 0)
    attr = struct.pack("<IIIHBBI", 1, 2, 0xffffffff, 8, 0, 1, resource)
    body = pool + node + ext + attr
    return struct.pack("<HHI", 3, 8, len(body) + 8) + body


def resources(path=PATH, flags=0, compact=False, alias=False, utf8=True):
    pool = strings([path], utf8)
    header = 84
    offsets = struct.pack("<HH", 0, 0) if flags & 1 else struct.pack("<H", 0) + b"\0\0" if flags & 2 else struct.pack("<I", 0)
    value_type, value = (1, RESOURCE) if alias else (3, 0)
    entry = struct.pack("<HHI", 0, 8 | (value_type << 8), value) if compact else struct.pack("<HHIHBBI", 8, 0, 0, 8, 0, value_type, value)
    chunk = bytearray(header)
    struct.pack_into("<HHIBBHII", chunk, 0, 0x201, header, header + len(offsets) + len(entry), 1, flags, 0, 1, header + len(offsets))
    struct.pack_into("<I", chunk, 20, 64)
    chunk += offsets + entry
    package = bytearray(288)
    struct.pack_into("<HHII", package, 0, 0x200, 288, 288 + len(chunk), 0x7f)
    package += chunk
    return struct.pack("<HHII", 2, 12, 12 + len(pool) + len(package), 1) + pool + package


def apk_bytes(manifest_data=None, resource_data=None, image=PNG, include_dex=True):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        if manifest_data is not None:
            archive.writestr("AndroidManifest.xml", manifest_data)
        if resource_data is not None:
            archive.writestr("resources.arsc", resource_data)
        if image is not None:
            archive.writestr(PATH, image)
        if include_dex:
            archive.writestr("classes.dex", b"dex\n035\0")
    return buffer.getvalue()


class PackageIconTests(unittest.TestCase):
    def test_binary_manifest_and_dense_sparse_offset16_compact_resources(self):
        for utf8 in (True, False):
            self.assertEqual(_manifest_icon(manifest(utf8=utf8)), RESOURCE)
            for flags, compact in ((0, False), (1, False), (2, False), (0, True)):
                self.assertEqual(_resource_paths(resources(flags=flags, compact=compact, utf8=utf8), RESOURCE), [PATH])

    def test_correct_source_icon_and_original_archive_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.apk"
            path.write_bytes(apk_bytes(manifest(), resources()))
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(extract_apk_icon(path), ICON)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_missing_unsupported_corrupt_and_oversized_icons_do_not_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.apk"
            for xml, table, image in (
                (manifest(), resources(), None),
                (b"bad manifest", resources(), PNG),
                (manifest(), b"bad resources", PNG),
                (manifest(), resources(), b"<svg onload='alert(1)'/>"),
                (manifest(), resources(), PNG + b"\0" * (512 * 1024)),
                (manifest(), resources(alias=True), PNG),
            ):
                path.write_bytes(apk_bytes(xml, table, image))
                self.assertEqual(extract_apk_icon(path), "")
            path.write_bytes(b"not a ZIP")
            self.assertEqual(extract_apk_icon(path), "")

    def test_never_guesses_unrelated_launcher_named_images(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.apk"
            path.write_bytes(apk_bytes(b'<manifest><application/></manifest>', resources()))
            self.assertEqual(extract_apk_icon(path), "")

    def test_source_analysis_exposes_icon_as_optional_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.apk"
            path.write_bytes(apk_bytes(manifest(), resources()))
            with mock.patch("engine.inspect_manifest_package", return_value="com.example.app"):
                self.assertEqual(inspect_apk(path)["app_icon"], ICON)

    def test_split_icon_follows_base_resource_into_density_module_not_feature(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.apks"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("base.apk", apk_bytes(manifest(), resources(), None))
                archive.writestr("config.xxhdpi.apk", apk_bytes(None, resources(), PNG, False))
                archive.writestr("feature.apk", apk_bytes(manifest(), resources(), b"wrong"))
            inventory = {"modules": [{"name": "base.apk", "kind": "base"}, {"name": "config.xxhdpi.apk", "kind": "density"}]}
            self.assertEqual(extract_split_icon(path, inventory), ICON)
            with mock.patch("engine.inspect_manifest_package", return_value="com.example.app"):
                self.assertEqual(inspect_split_package(path, inventory)["app_icon"], ICON)

    def test_native_preview_is_bounded_and_failure_uses_source_resource_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.apk"
            path.write_bytes(apk_bytes(manifest(), resources()))
            runner = types.SimpleNamespace(inspectArchiveIcon=lambda _: ICON)
            with mock.patch.dict(os.environ, {"APK_CLEANER_ANDROID": "1"}), mock.patch.dict(sys.modules, {"java": types.SimpleNamespace(jclass=lambda _: runner)}):
                self.assertEqual(extract_apk_icon(path), ICON)
                runner.inspectArchiveIcon = lambda _: "data:image/png;base64," + "!" * 50
                self.assertEqual(extract_apk_icon(path), ICON)

    def test_passive_image_mimes_and_pixel_limits(self):
        self.assertEqual(_raster_uri(PNG), ICON)
        oversized = bytearray(PNG)
        struct.pack_into(">II", oversized, 16, 100000, 100000)
        self.assertEqual(_raster_uri(oversized), "")
        webp = b"RIFF" + b"\0" * 4 + b"WEBPVP8X" + b"\0" * 8 + (71).to_bytes(3, "little") * 2
        self.assertTrue(_raster_uri(webp).startswith("data:image/webp;base64,"))
        self.assertEqual(_raster_uri(b"<svg>" + b" " * 50), "")

    def test_android_source_shares_native_icon_renderer_and_sync_includes_helper(self):
        native = (ROOT / "android/app/src/main/java/com/apkcleaner/studio/EmbeddedToolRunner.java").read_text(encoding="utf-8")
        self.assertIn("info.applicationInfo.sourceDir = apkPath", native)
        self.assertIn("info.applicationInfo.publicSourceDir = apkPath", native)
        self.assertIn("resources.getDrawable(info.applicationInfo.icon, null)", native)
        self.assertIn("MainActivity.drawableDataUri", native)
        self.assertIn('"package_icon.py"', (ROOT / "packaging/sync_android.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
