import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "android/app/src/main/res"


class SplashThemeTests(unittest.TestCase):
    def palette(self, folder):
        return {node.get("name"): node.text for node in ET.parse(RES / folder / "colors.xml").getroot()}

    def test_system_theme_resources_preserve_the_previous_dark_palette(self):
        light, dark = self.palette("values"), self.palette("values-night")
        self.assertEqual(dark["splash_background_color"], "#07100D")
        self.assertEqual(dark["splash_gradient_center"], "#0B1713")
        self.assertEqual(dark["splash_gradient_bottom"], "#101815")
        self.assertEqual(dark["splash_title"], "#EEF5F1")
        self.assertEqual(dark["splash_tagline"], "#66B797")
        self.assertEqual(dark["splash_glow"], "#4EC4FF2B")
        self.assertEqual((light["splash_light_bars"], dark["splash_light_bars"]), ("true", "false"))
        self.assertNotEqual(light["splash_background_color"], dark["splash_background_color"])

    def test_both_android_splash_stages_use_theme_resources_without_changing_timings(self):
        java = (ROOT / "android/app/src/main/java/com/apkcleaner/studio/LauncherActivity.java").read_text(encoding="utf-8")
        for name in ("splash_background_color", "splash_title", "splash_tagline", "splash_glow"):
            self.assertIn("getColor(R.color." + name + ")", java)
        for duration in (430, 620, 720, 760): self.assertIn(f"setDuration({duration})", java)
        self.assertIn("APPEARANCE_LIGHT_STATUS_BARS", java)
        self.assertIn("SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR", java)
        for folder in ("values", "values-v27", "values-v31"):
            styles = ET.parse(RES / folder / "styles.xml").getroot()
            splash = next(node for node in styles if node.get("name") == "Theme.APKCleanerStudio.Splash")
            values = {node.get("name"): node.text for node in splash}
            self.assertEqual(values["android:windowLightStatusBar"], "@bool/splash_light_bars")
            self.assertEqual(values["android:navigationBarColor"], "@color/splash_background_color")

    def test_light_navigation_bar_is_scoped_to_supported_android_versions(self):
        for folder in ("values", "values-v27", "values-v31"):
            styles = ET.parse(RES / folder / "styles.xml").getroot()
            splash = next(node for node in styles if node.get("name") == "Theme.APKCleanerStudio.Splash")
            values = {node.get("name"): node.text for node in splash}
            if folder == "values":
                self.assertNotIn("android:windowLightNavigationBar", values)
            else:
                self.assertEqual(values["android:windowLightNavigationBar"], "@bool/splash_light_bars")
        java = (ROOT / "android/app/src/main/java/com/apkcleaner/studio/LauncherActivity.java").read_text(encoding="utf-8")
        self.assertIn("if (Build.VERSION.SDK_INT >= 27) mask |= View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR", java)

    def test_system_cover_has_no_duplicate_launcher_icon_or_icon_animation(self):
        styles = ET.parse(RES / "values-v31/styles.xml").getroot()[0]
        values = {node.get("name"): node.text for node in styles}
        self.assertEqual(values["android:windowSplashScreenAnimatedIcon"], "@drawable/splash_transparent_icon")
        self.assertEqual(values["android:windowSplashScreenIconBackgroundColor"], "@android:color/transparent")
        self.assertEqual(values["android:windowSplashScreenAnimationDuration"], "0")
        icon = ET.parse(RES / "drawable/splash_transparent_icon.xml").getroot()
        attr = "{http://schemas.android.com/apk/res/android}"
        self.assertEqual(icon.tag, "vector")
        for path in icon.findall("path"):
            self.assertEqual(path.get(attr + "fillColor"), "@android:color/transparent")
        manifest = ET.parse(RES.parent / "AndroidManifest.xml").getroot()
        self.assertEqual(manifest.find("application").get(attr + "icon"), "@mipmap/ic_launcher")

    def test_animation_waits_for_visible_content_and_has_a_no_system_splash_fallback(self):
        java = (ROOT / "android/app/src/main/java/com/apkcleaner/studio/LauncherActivity.java").read_text(encoding="utf-8")
        self.assertIn("if (Build.VERSION.SDK_INT >= 31)", java)
        self.assertIn("getSplashScreen().setOnExitAnimationListener", java)
        self.assertIn("splash.remove();\n                startSplashAnimation();", java)
        pre_draw = java.split("@Override public boolean onPreDraw()", 1)[1].split("return true;", 1)[0]
        self.assertIn("startSplashAnimation();", pre_draw)
        self.assertNotIn("postOnAnimation", pre_draw)
        self.assertIn("removeOnPreDrawListener(this)", java)
        start = java.split("private void startSplashAnimation()", 1)[1].split("private void applySplashSystemBars()", 1)[0]
        self.assertIn("splashAnimationStarted || splashAnimation == null || isFinishing() || isDestroyed()", start)
        self.assertLess(start.index("splashAnimationStarted = true"), start.index("animation.run()"))
        self.assertIn("EngineService.ready && splashAnimationStarted && visibleElapsed >= 720", java)
        self.assertIn("now - launchStartedAt >= 30000", java)
        self.assertNotIn("System.currentTimeMillis()", java)
