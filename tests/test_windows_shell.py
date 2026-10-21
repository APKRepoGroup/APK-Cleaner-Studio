from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "studio"))
from windows_shell import capture_geometry, restore_geometry, WindowStateStore

PRIMARY = {"name": "primary", "x": 0, "y": 0, "width": 1920, "height": 1040, "dpi": 96}
LEFT = {"name": "left", "x": -2560, "y": 0, "width": 2560, "height": 1400, "dpi": 144}


class WindowGeometryTests(unittest.TestCase):
    def test_first_start_is_centered_and_never_larger_than_work_area(self):
        state = restore_geometry({}, [PRIMARY])
        self.assertEqual((state["x"], state["y"], state["width"], state["height"]), (360, 90, 1200, 860))
        small = {**PRIMARY, "width": 700, "height": 500}
        state = restore_geometry({}, [small])
        self.assertEqual((state["width"], state["height"], state["min_width"], state["min_height"]), (700, 500, 700, 500))

    def test_negative_monitor_coordinates_and_dpi_changes_round_trip(self):
        bounds = {"x": -2300, "y": 120, "width": 1500, "height": 1000}
        saved = capture_geometry(bounds, LEFT, True)
        restored = restore_geometry(saved, [PRIMARY, LEFT])
        for field in bounds:
            self.assertLessEqual(abs(restored[field] - bounds[field]), 1)
        self.assertTrue(restored["maximized"])
        lower_dpi = {**LEFT, "dpi": 96}
        restored = restore_geometry(saved, [lower_dpi])
        self.assertEqual(restored["width"], 1000)
        self.assertEqual(restored["height"], 667)

    def test_removed_monitor_or_invalid_coordinates_do_not_hide_the_window(self):
        saved = capture_geometry({"x": -2200, "y": 40, "width": 1500, "height": 1000}, LEFT, False)
        restored = restore_geometry(saved, [PRIMARY])
        self.assertGreaterEqual(restored["x"], 0)
        saved.update(monitor="primary", offset_x=-99999, offset_y=99999, width=99999, height=99999)
        restored = restore_geometry(saved, [PRIMARY])
        self.assertEqual((restored["x"], restored["y"], restored["width"], restored["height"]), (0, 0, 1920, 1040))

    def test_corrupted_unknown_or_non_numeric_preferences_use_safe_defaults(self):
        for saved in (None, [], {"schema": 99}, {"schema": 1, "width": "oops", "height": float("nan"), "offset_x": True}):
            state = restore_geometry(saved, [PRIMARY])
            self.assertEqual(state["width"], 1200)
            self.assertEqual(state["height"], 860)

    def test_preferences_are_atomic_and_invalid_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "window.json"
            store = WindowStateStore(path)
            self.assertEqual(store.load(), {})
            store.save({"schema": 1, "width": 1100})
            self.assertEqual(store.load()["width"], 1100)
            self.assertFalse(path.with_suffix(".json.tmp").exists())
            path.write_text("broken", encoding="utf-8")
            self.assertEqual(store.load(), {})
            path.write_text("x" * 16385, encoding="utf-8")
            self.assertEqual(store.load(), {})


if __name__ == "__main__":
    unittest.main()
