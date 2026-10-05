import io
from pathlib import Path
import struct
import sys
import unittest
import zipfile
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "studio"))
from package_icon import ANDROID_NS, MAX_MANIFEST_BYTES, read_manifest_identity
from engine import _archive_manifest_identity
from test_package_icon import strings


def binary_manifest(utf8=True, code=42, major=None, reference=False):
    pool = strings(["manifest", "package", "com.example.app", ANDROID_NS, "versionCode", "versionCodeMajor"], utf8)
    attrs = [struct.pack("<IIIHBBI", 0xffffffff, 1, 2, 8, 0, 3, 2),
             struct.pack("<IIIHBBI", 3, 4, 0xffffffff, 8, 0, 1 if reference else 0x10, code)]
    if major is not None:
        attrs.append(struct.pack("<IIIHBBI", 3, 5, 0xffffffff, 8, 0, 0x10, major))
    ext = struct.pack("<II6H", 0xffffffff, 0, 20, 20, len(attrs), 0, 0, 0)
    tag = struct.pack("<HHIII", 0x102, 16, 16 + len(ext) + sum(map(len, attrs)), 1, 0xffffffff) + ext + b"".join(attrs)
    body = pool + tag
    return struct.pack("<HHI", 3, 8, len(body) + 8) + body


class ManifestIdentityTests(unittest.TestCase):
    def test_binary_utf8_and_utf16_manifest_identity(self):
        for utf8 in (True, False):
            self.assertEqual(read_manifest_identity(binary_manifest(utf8)), {"package_name": "com.example.app", "version_code": "42"})

    def test_xml_zero_hex_and_long_codes(self):
        data = f'<manifest xmlns:android="{ANDROID_NS}" package="com.example.app" android:versionCode="0x00000000" android:versionCodeMajor="1"/>'
        self.assertEqual(read_manifest_identity(data.encode())["version_code"], "4294967296")
        self.assertEqual(read_manifest_identity(binary_manifest(code=0))["version_code"], "0")
        self.assertEqual(read_manifest_identity(binary_manifest(code=0xffffffff, major=0x7fffffff))["version_code"], "9223372036854775807")

    def test_absent_or_referenced_code_is_unknown_not_zero(self):
        self.assertIsNone(read_manifest_identity(b'<manifest package="com.example.app"/>')["version_code"])
        self.assertIsNone(read_manifest_identity(binary_manifest(reference=True))["version_code"])
        data = f'<manifest xmlns:android="{ANDROID_NS}" package="com.example.app" android:versionCode="@integer/code"/>'
        self.assertIsNone(read_manifest_identity(data.encode())["version_code"])

    def test_malformed_or_oversized_metadata_is_optional(self):
        for data in (b"", b"not a manifest", b"<manifest", binary_manifest()[:30], b"x" * (MAX_MANIFEST_BYTES + 1)):
            self.assertEqual(read_manifest_identity(data), {"package_name": None, "version_code": None})
        data = f'<manifest xmlns:android="{ANDROID_NS}" package="not a package" android:versionCode="-1"/>'
        self.assertEqual(read_manifest_identity(data.encode()), {"package_name": None, "version_code": None})

    def test_archive_reader_limits_expansion_before_reading(self):
        archive = Mock()
        archive.getinfo.return_value.file_size = MAX_MANIFEST_BYTES + 1
        self.assertIsNone(_archive_manifest_identity(archive)["version_code"])
        archive.read.assert_not_called()
        with zipfile.ZipFile(io.BytesIO(), "w") as empty:
            self.assertIsNone(_archive_manifest_identity(empty)["package_name"])


if __name__ == "__main__":
    unittest.main()
