import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InstalledIconQualityTests(unittest.TestCase):
    def test_list_loads_dense_artwork_before_rendering_a_bounded_density_aware_preview(self):
        source = (ROOT / "android/app/src/main/java/com/apkcleaner/studio/MainActivity.java").read_text(encoding="utf-8")
        self.assertIn("final int iconSize = Math.max(128, Math.min(256,", source)
        self.assertIn("Math.round(48f * getResources().getDisplayMetrics().density)", source)
        helper = source.split("private String installedIconDataUri(", 1)[1].split("static String drawableDataUri(", 1)[0]
        self.assertEqual(helper.count("getDrawableForDensity("), 2)
        self.assertEqual(helper.count("DENSITY_XXXHIGH"), 2)
        self.assertIn("launcher.resolvePackageName", helper)
        self.assertIn("launcher.getIconResource()", helper)
        self.assertIn("launcher.loadIcon(manager), size", helper)
        self.assertIn("manager.getApplicationIcon(info.applicationInfo), size", helper)
        self.assertNotIn("return drawableDataUri(drawable, 72)", source)
        self.assertIn("bitmap.recycle();", source)
        self.assertIn("drawable.setBounds(previousBounds);", source)
        self.assertIn("FILTER_BITMAP_FLAG", source)
