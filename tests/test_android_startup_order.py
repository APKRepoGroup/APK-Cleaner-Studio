"""Guard the cold-start boundary: first UI must not wait for Python startup."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / "android/app/src/main/java/com/apkcleaner/studio"
ATTR = "{http://schemas.android.com/apk/res/android}"


class AndroidStartupOrderTests(unittest.TestCase):
    def setUp(self):
        self.service = (JAVA / "EngineService.java").read_text(encoding="utf-8")
        self.start = self.service.split("private void startPythonServer()", 1)[1].split("private static String describe", 1)[0]

    def test_application_does_not_start_the_interpreter_before_the_activity(self):
        app = ET.parse(ROOT / "android/app/src/main/AndroidManifest.xml").getroot().find("application")
        self.assertIn(app.get(ATTR + "name"), (None, "android.app.Application"))
        for source in JAVA.glob("*.java"):
            if source.name != "EngineService.java":
                self.assertNotIn("Python.start(", source.read_text(encoding="utf-8"))

    def test_runtime_start_is_on_the_existing_serialized_service_worker(self):
        worker = self.service.split("private void ensureEngineRunning()", 1)[1].split("public static boolean isReachable", 1)[0]
        self.assertIn("executor.execute(() ->", worker)
        self.assertIn("startPythonServer();", worker)
        self.assertIn("0, 1, 15, TimeUnit.SECONDS", self.service)
        lifecycle = self.service.split("@Override public void onCreate()", 1)[1].split("private void ensureEngineRunning()", 1)[0]
        self.assertNotIn("Python.start(", lifecycle)
        self.assertNotIn("Python.getInstance()", lifecycle)
        self.assertIn("startForeground(31,", lifecycle)

    def test_cold_start_uses_android_context_and_warm_start_reuses_the_runtime(self):
        self.assertIn("if (!Python.isStarted()) {\n                Python.start(new AndroidPlatform(getApplicationContext()));\n            }", self.start)
        self.assertLess(self.start.index("Python.start("), self.start.index("Python.getInstance()"))
        self.assertEqual(self.service.count("Python.start("), 1)

    def test_stop_during_initialization_cannot_launch_a_late_http_server(self):
        start = self.start.index("Python.start(")
        stopped = self.start.index("if (stopping) return;", start)
        module = self.start.index('getModule("android_entry")')
        self.assertLess(start, stopped)
        self.assertLess(stopped, module)
        self.assertIn('DiagnosticRecorder.record(this, "engine-startup", error)', self.start)
        self.assertIn("startupError = describe(error)", self.start)

    def test_ui_stays_independent_of_engine_readiness_and_keeps_the_design(self):
        launcher = (JAVA / "LauncherActivity.java").read_text(encoding="utf-8")
        animation = launcher.split("private void startSplashAnimation()", 1)[1].split("private void applySplashSystemBars()", 1)[0]
        self.assertNotIn("EngineService.ready", animation)
        self.assertNotIn("Python", launcher)
        self.assertIn("splashAnimationStarted || splashAnimation == null", animation)
        self.assertIn("EngineService.ready && splashAnimationStarted && visibleElapsed >= 720", launcher)
        for duration in (430, 620, 720, 760):
            self.assertIn(f"setDuration({duration})", launcher)
