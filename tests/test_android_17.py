"""Source-level Android 17 guards; these do not replace device/APK tests."""

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android/app"
JAVA = APP / "src/main/java/com/apkcleaner/studio"
ANDROID_ATTR = "{http://schemas.android.com/apk/res/android}"


class Android17SourceTests(unittest.TestCase):
    def test_target_and_compile_sdk_preserve_old_device_matrix(self):
        gradle = (APP / "build.gradle").read_text(encoding="utf-8")
        for setting, expected in (("compileSdk", 37), ("targetSdk", 37), ("minSdk", 26)):
            values = re.findall(rf"^\s*{setting}\s+(\d+)\s*$", gradle, re.M)
            self.assertEqual(values, [str(expected)])
        self.assertIn('abiFilters "arm64-v8a", "armeabi-v7a"', gradle)
        self.assertIn('version = "3.11"', gradle)

    def test_local_engine_stays_inside_the_same_application(self):
        entry = (APP / "src/main/python/android_entry.py").read_text(encoding="utf-8")
        activity = (JAVA / "MainActivity.java").read_text(encoding="utf-8")
        service = (JAVA / "EngineService.java").read_text(encoding="utf-8")
        self.assertIn('server.serve("127.0.0.1", int(port), False, False, True)', entry)
        self.assertIn('"http://127.0.0.1:" + EngineService.PORT', activity)
        self.assertIn('"127.0.0.1"', service)
        manifest = ET.parse(APP / "src/main/AndroidManifest.xml").getroot()
        permissions = {item.get(ANDROID_ATTR + "name") for item in manifest.findall("uses-permission")}
        self.assertNotIn("android.permission.ACCESS_LOCAL_NETWORK", permissions)
        self.assertNotIn("android.permission.NEARBY_WIFI_DEVICES", permissions)
        app = manifest.find("application")
        engine = next(item for item in app.findall("service") if item.get(ANDROID_ATTR + "name") == ".EngineService")
        self.assertEqual(engine.get(ANDROID_ATTR + "exported"), "false")

    def test_network_security_does_not_weaken_external_connections(self):
        config = ET.parse(APP / "src/main/res/xml/network_security_config.xml").getroot()
        self.assertEqual(config.findall("base-config[@cleartextTrafficPermitted='true']"), [])
        domains = {item.text for group in config.findall(".//domain-config[@cleartextTrafficPermitted='true']") for item in group.findall("domain")}
        self.assertEqual(domains, {"127.0.0.1", "localhost"})
        self.assertEqual(config.findall(".//certificateTransparency[@enabled='false']"), [])
        self.assertEqual(config.findall(".//trust-anchors"), [])

    def test_android_java_does_not_use_private_queue_or_writable_native_loads(self):
        # Dependency internals need a separate audit when Chaquopy is upgraded.
        for path in JAVA.glob("*.java"):
            source = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                self.assertNotRegex(source, r"\bSystem\s*\.\s*load\s*\(")
                self.assertNotIn("getDeclaredField", source)
                self.assertNotIn("MessageQueue", source)
                self.assertNotIn("MODE_BACKGROUND_ACTIVITY_START_ALLOWED", source)

    def test_modern_back_navigation_and_resizable_windows_are_retained(self):
        source = (JAVA / "MainActivity.java").read_text(encoding="utf-8")
        callback = source.split("private void configureBackNavigation()", 1)[1].split("private void handleBack()", 1)[0]
        self.assertIn("Build.VERSION.SDK_INT >= 33", callback)
        self.assertIn("registerOnBackInvokedCallback", callback)
        self.assertIn("setOnApplyWindowInsetsListener", source)
        manifest = ET.parse(APP / "src/main/AndroidManifest.xml").getroot()
        for activity in manifest.findall("application/activity"):
            self.assertIsNone(activity.get(ANDROID_ATTR + "screenOrientation"))
            self.assertNotEqual(activity.get(ANDROID_ATTR + "resizeableActivity"), "false")

    def test_install_callback_is_explicit_and_service_handles_timeouts(self):
        installer = (JAVA / "OriginalSplitInstaller.java").read_text(encoding="utf-8")
        self.assertIn("new Intent(context, ResultReceiver.class)", installer)
        self.assertIn("PendingIntent.getBroadcast(context, sessionId, callback, flags)", installer)
        self.assertIn("PendingIntent.FLAG_MUTABLE", installer)
        service = (JAVA / "EngineService.java").read_text(encoding="utf-8")
        self.assertIn("onTimeout(int startId, int fgsType)", service)
        activity = (JAVA / "MainActivity.java").read_text(encoding="utf-8")
        self.assertIn("Intent.FLAG_GRANT_READ_URI_PERMISSION", activity)


if __name__ == "__main__":
    unittest.main()
