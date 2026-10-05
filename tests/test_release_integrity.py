import json
import re
import sys
import unittest
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "studio"))

import server


class ReleaseIntegrityTests(unittest.TestCase):
    def test_android_release_credentials_live_outside_the_source_tree(self):
        self.assertFalse((ROOT / "android" / "signing.properties").exists())
        signing = ROOT / "android" / "signing"
        self.assertFalse(any(signing.glob("*.jks")))
        self.assertFalse(any(signing.glob("*.p12")))
        gradle = (ROOT / "android" / "app" / "build.gradle").read_text(encoding="utf-8")
        self.assertIn("APK_CLEANER_SIGNING_PROPERTIES", gradle)
        self.assertIn("APKCleanerStudio/release-signing/signing.properties", gradle)

    def test_output_signing_certificate_contains_only_product_common_name(self):
        payload = (ROOT / "studio" / "tools" / "output-signing.p12").read_bytes()
        _key, certificate, _chain = load_key_and_certificates(payload, b"apkcleaner")
        self.assertIsNotNone(certificate)
        self.assertEqual(certificate.subject.rfc4514_string(), "CN=APK Cleaner Studio")
        self.assertEqual(certificate.issuer.rfc4514_string(), "CN=APK Cleaner Studio")

    def test_version_is_consistent_across_runtime_web_and_packaging(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
        version = package["version"]
        self.assertEqual(package["name"], "apk-cleaner-studio")
        self.assertEqual(lock["name"], "apk-cleaner-studio")
        self.assertEqual(lock["packages"][""]["name"], "apk-cleaner-studio")
        self.assertEqual(server.VERSION, version)
        self.assertEqual(lock["version"], version)
        self.assertEqual(lock["packages"][""]["version"], version)
        self.assertIn(version, (ROOT / "VERSION.txt").read_text(encoding="utf-8"))
        self.assertIn(version, (ROOT / "studio" / "web" / "index.html").read_text(encoding="utf-8"))
        self.assertIn(version, (ROOT / "packaging" / "build_termux.py").read_text(encoding="utf-8"))
        self.assertIn(version, (ROOT / "packaging" / "APK-Cleaner-Studio-Windows.spec").read_text(encoding="utf-8"))

    def test_development_version_uses_development_release_channel(self):
        server = (ROOT / "studio" / "server.py").read_text(encoding="utf-8")
        self.assertIn('VERSION = "0.6.3-dev.4"', server)
        self.assertIn('RELEASE_CHANNEL = "dev"', server)

    def test_android_readme_matches_actual_package_identity_and_version(self):
        gradle = (ROOT / "android" / "app" / "build.gradle").read_text(encoding="utf-8")
        readme = (ROOT / "android" / "README.md").read_text(encoding="utf-8")
        for field in ("applicationId", "versionCode", "versionName"):
            match = re.search(rf"^\s*{field}\s+(\"[^\"]+\"|\d+)\s*$", gradle, re.MULTILINE)
            self.assertIsNotNone(match, field)
            self.assertIn(match.group(1).strip('"'), readme, field)

    def test_termux_launcher_defaults_to_http_and_cleans_its_owned_process(self):
        launcher = (ROOT / "start-termux.sh").read_text(encoding="utf-8")
        self.assertIn("--prefer-http", launcher)
        self.assertIn("http://127.0.0.1:8080/", launcher)
        self.assertNotIn("termux-open-url https://127.0.0.1:8080/", launcher)
        self.assertIn(".apk-cleaner-termux.pid", launcher)
        self.assertIn("trap stop_server EXIT", launcher)
        self.assertIn("kill -KILL", launcher)
        self.assertIn("studio/server.py", launcher)

    def test_working_view_exposes_real_job_cancellation(self):
        html = (ROOT / "studio" / "web" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "studio" / "web" / "app.js").read_text(encoding="utf-8")
        backend = (ROOT / "studio" / "server.py").read_text(encoding="utf-8")
        self.assertIn('id="cancelJobButton"', html)
        self.assertIn('/cancel`', script)
        self.assertIn('status === "cancelled"', script)
        self.assertIn('cancel_match = re.fullmatch', backend)

    def test_report_viewer_supports_inline_reading_and_explicit_download(self):
        html = (ROOT / "studio" / "web" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "studio" / "web" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "studio" / "web" / "theme.css").read_text(encoding="utf-8")
        self.assertIn('id="reportViewerDownload"', html)
        self.assertIn("Raporu indir", html)
        self.assertIn('download.href = `/api/jobs/${encodeURIComponent(jobId)}/report`', script)
        self.assertIn('html[data-embedded="android"] .report-viewer', css)
        self.assertIn("var(--android-status-inset", css)

    def test_special_thanks_area_is_present_and_editable_in_one_place(self):
        html = (ROOT / "studio" / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="specialThanksTitle"', html)
        self.assertIn('id="supporterList"', html)
        self.assertIn("Ahmet Özesen", html)
        self.assertIn("Zafer Can Şenol", html)
        self.assertIn("<b>SHADOW</b><small>Destekçi</small>", html)
        self.assertIn("Daimi Destekçi", html)

    def test_termux_installer_and_runtime_version_match_development_release(self):
        docs = "\n".join(
            (ROOT / name).read_text(encoding="utf-8")
            for name in ("README.md", "README-TR.md", "README-TERMUX.md", "VERSION.txt")
        )
        self.assertNotIn("0.5.3", docs)
        self.assertIn("APK Cleaner Studio 0.6.3-dev.4", docs)
        installer = (ROOT / "install-termux.sh").read_text(encoding="utf-8")
        self.assertIn("openjdk-25", installer)
        self.assertIn("openjdk-21", installer)

    def test_https_help_is_browser_neutral(self):
        html = (ROOT / "studio" / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Kurulum ve tarayıcı notlarını göster", html)
        self.assertNotIn("Kurulum ve Brave notunu göster", html)
        self.assertNotIn("Brave’i tamamen kapatıp yeniden aç", html)

    def test_https_setup_card_is_desktop_visible_and_secure_connection_aware(self):
        html = (ROOT / "studio" / "web" / "index.html").read_text(encoding="utf-8")
        boot = (ROOT / "studio" / "web" / "boot.js").read_text(encoding="utf-8")
        css = (ROOT / "studio" / "web" / "theme.css").read_text(encoding="utf-8")
        self.assertIn('const secure = location.protocol === "https:"', boot)
        self.assertIn('document.documentElement.dataset.secure = secure ? "true" : "false"', boot)
        self.assertIn('sessionStorage.setItem("apk-cleaner-trusted-https", "1")', boot)
        self.assertIn('html[data-secure="true"] .mobile-https-banner { display: none; }', css)
        self.assertIn("grid-template-columns: 52px minmax(0,1fr) minmax(220px,280px)", css)
        self.assertIn("İSTEĞE BAĞLI YEREL HTTPS", html)
        self.assertIn('id="httpFallback"', html)
        self.assertIn('.mobile-cert { display: block; }', css)
        self.assertIn("Windows + Termux + APK", html)

    def test_windows_starts_on_http_before_trusted_https_upgrade(self):
        backend = (ROOT / "studio" / "server.py").read_text(encoding="utf-8")
        self.assertIn('scheme = "http"', backend)
        self.assertNotIn('scheme = "http" if prefer_http else "https"', backend)

    def test_detection_profiles_have_complete_unique_schema(self):
        profiles = json.loads((ROOT / "studio" / "profiles.json").read_text(encoding="utf-8"))
        self.assertEqual(len(profiles), 18)
        self.assertEqual(len({row["label"] for row in profiles.values()}), 18)
        for profile_id, row in profiles.items():
            self.assertRegex(profile_id, r"^[a-z0-9_]+$")
            self.assertTrue(row["label"])
            self.assertTrue(row["descriptors"])
            for key in ("descriptors", "manifest", "metadata", "assets", "libraries"):
                self.assertIsInstance(row[key], list)
                self.assertEqual(len(row[key]), len(set(row[key])))

    def test_bundled_java_tools_are_valid_nonempty_archives(self):
        tool_dir = ROOT / "studio" / "tools"
        for name in ("APKEditor.jar", "binary-xml-patcher.jar", "dexlib2-runtime.jar", "direct-dex-patcher.jar", "uber-apk-signer.jar"):
            path = tool_dir / name
            self.assertGreater(path.stat().st_size, 1024, name)
            with zipfile.ZipFile(path) as archive:
                self.assertIsNone(archive.testzip(), name)
                self.assertIn("META-INF/MANIFEST.MF", archive.namelist(), name)
        zipalign = tool_dir / "zipalign-win.exe"
        self.assertGreater(zipalign.stat().st_size, 100_000)
        self.assertEqual(zipalign.read_bytes()[:2], b"MZ")

    def test_update_channel_never_uses_insecure_remote_manifest(self):
        channel = json.loads((ROOT / "studio" / "update-channel.json").read_text(encoding="utf-8"))
        url = channel.get("manifest_url", "")
        self.assertEqual(url, "https://api.github.com/repos/APKRepoGroup/APK-Cleaner-Studio/releases/latest")

    def test_github_update_ui_and_platform_apply_endpoint_are_connected(self):
        html = (ROOT / "studio" / "web" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "studio" / "web" / "app.js").read_text(encoding="utf-8")
        backend = (ROOT / "studio" / "server.py").read_text(encoding="utf-8")
        updater = (ROOT / "studio" / "updater.py").read_text(encoding="utf-8")
        self.assertIn('id="updateDownload"', html)
        self.assertIn("installUpdate", script)
        self.assertIn('"/api/update/apply"', script)
        self.assertIn('path == "/api/update/apply"', backend)
        self.assertIn("stage_update(VERSION)", backend)
        self.assertIn("releases/latest", updater)
        self.assertIn("digest", updater)

    def test_private_owner_address_is_not_embedded_in_runtime_or_packaging(self):
        forbidden = ("apkcleaner.erdgn", "10.10.30.")
        paths = [
            *(ROOT / "studio").glob("*.py"),
            *(ROOT / "studio" / "web").glob("*.js"),
            *(ROOT / "packaging").glob("*"),
        ]
        payload = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in paths if path.is_file())
        for marker in forbidden:
            self.assertNotIn(marker, payload)


if __name__ == "__main__":
    unittest.main()
