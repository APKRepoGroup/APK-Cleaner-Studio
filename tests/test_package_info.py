from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "studio"))
from package_info import manifest_fields, inspect_package_info
from package_icon import ANDROID_NS, MAX_MANIFEST_BYTES


class PackageInfoTests(unittest.TestCase):
    def test_plain_metadata_references_and_permissions(self):
        data = f'<manifest xmlns:android="{ANDROID_NS}" android:versionName="1.2"><uses-sdk android:minSdkVersion="26" android:targetSdkVersion="37"/><application android:label="@string/title"/><uses-permission android:name="android.permission.INTERNET"/><uses-permission android:name="android.permission.INTERNET"/></manifest>'.encode()
        result = manifest_fields(data)
        self.assertEqual((result["min_sdk"], result["target_sdk"], result["version_name"]), (26, 37, "1.2"))
        self.assertIsNone(result["app_name"])
        self.assertEqual(len(result["permissions"]), 1)

    def test_malformed_metadata_is_unknown_not_compatibility_guarantee(self):
        for value in (b"", b"not XML", b"<manifest", b"x" * (MAX_MANIFEST_BYTES + 1)):
            self.assertIsNone(manifest_fields(value)["min_sdk"])
        self.assertIsNone(manifest_fields(f'<manifest xmlns:android="{ANDROID_NS}"><uses-sdk android:minSdkVersion="@integer/sdk"/></manifest>'.encode())["min_sdk"])

    def test_architectures_and_signature_presence_without_verification(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "source.apk"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("AndroidManifest.xml", b"<manifest/>")
                archive.writestr("lib/arm64-v8a/libexample.so", b"library")
                archive.writestr("lib/x86_64/libexample.so", b"library")
                archive.writestr("assets/fake-arm64-v8a.so", b"not native")
                archive.writestr("META-INF/TEST.RSA", b"not a certificate")
                archive.writestr("META-INF/TEST.SF", b"not verified")
            result = inspect_package_info(path)
            self.assertEqual(result["abis"], ["arm64-v8a", "x86_64"])
            self.assertEqual(result["signature_schemes"], ["V1"])
            self.assertNotIn("verified", result)

    def test_bounded_signing_block_pairs_are_detected(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "source.apk"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("AndroidManifest.xml", b"<manifest/>")
            data = path.read_bytes()
            end = data.rfind(b"PK\x05\x06")
            central = struct.unpack_from("<I", data, end + 16)[0]
            pairs = b"".join(struct.pack("<QI", 5, identity) + b"x" for identity in (0x7109871a, 0xf05368c0))
            size = len(pairs) + 24
            block = struct.pack("<Q", size) + pairs + struct.pack("<Q", size) + b"APK Sig Block 42"
            final = bytearray(data[:central] + block + data[central:])
            struct.pack_into("<I", final, end + len(block) + 16, central + len(block))
            path.write_bytes(final)
            self.assertEqual(inspect_package_info(path)["signature_schemes"], ["V2", "V3"])
