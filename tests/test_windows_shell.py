from pathlib import Path
import sys
import tempfile
import ctypes
import re
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "studio"))
from windows_shell import capture_geometry, restore_geometry, WindowStateStore, InstanceGate, progress_snapshot, NativeTaskbar, WindowsShell

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


class InstanceGateTests(unittest.TestCase):
    def test_second_instance_signals_existing_window_and_releases_only_its_handles(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "logs/desktop-session.json"
            path.parent.mkdir()
            path.write_text('{"pid": 123}', encoding="utf-8")
            api = mock.Mock()
            api.mutex.return_value = (101, True)
            api.open_event.return_value = 202
            api.signal.return_value = True
            gate = InstanceGate(path, api=api)
            self.assertTrue(gate.existing)
            api.event.assert_not_called()
            self.assertTrue(gate.request_activation())
            api.grant_foreground.assert_called_once_with(123, "APK Cleaner Studio")
            api.signal.assert_called_once_with(202)
            gate.close()
            gate.close()
            self.assertEqual(api.close.call_args_list, [mock.call(202), mock.call(101)])

    def test_startup_click_is_queued_without_needing_a_session_file(self):
        api = mock.Mock()
        api.mutex.return_value = (101, False)
        api.event.return_value = 202
        api.consume.return_value = True
        gate = InstanceGate("unwritten/logs/desktop-session.json", api=api)
        self.assertFalse(gate.existing)
        self.assertTrue(gate.consume_activation())
        gate.foreground(333)
        api.foreground.assert_called_once_with(333)
        gate.close()
        self.assertEqual(api.close.call_args_list, [mock.call(202), mock.call(101)])

    def test_failed_event_initialization_releases_mutex_and_data_roots_are_isolated(self):
        api = mock.Mock()
        api.mutex.return_value = (101, False)
        api.event.side_effect = OSError("not available")
        with self.assertRaises(OSError):
            InstanceGate("one/logs/session.json", api=api)
        api.close.assert_called_once_with(101)
        api.event.side_effect = None
        api.event.return_value = 202
        first = InstanceGate("one/logs/session.json", api=api)
        other = InstanceGate("two/logs/session.json", api=api)
        self.assertNotEqual(first.name, other.name)
        first.close()
        other.close()


class TaskbarTests(unittest.TestCase):
    def runtime(self, records):
        return SimpleNamespace(_ACTIVE_JOBS_LOCK=threading.Lock(), _ACTIVE_JOBS=set(records), _SCANNING_JOBS=set(),
                               JOB_ID=re.compile(r"[a-f0-9]{32}"), JOBS=Path("jobs"),
                               read_json=lambda path: records[path.parent.name])

    def test_idle_analysis_active_and_terminal_states(self):
        runtime = self.runtime({})
        self.assertEqual(progress_snapshot(runtime), ("none", 0))
        self.assertEqual(progress_snapshot(runtime, True), ("indeterminate", 0))
        for record, expected in [({}, ("indeterminate", 0)), ([], ("indeterminate", 0)),
                                 ({"status": "working", "progress": 53}, ("normal", 53)),
                                 ({"status": "cancelling", "progress": 53}, ("paused", 53)),
                                 ({"status": "working", "progress": 100}, ("normal", 99)),
                                 ({"status": "working", "progress": float("nan")}, ("indeterminate", 0))]:
            self.assertEqual(progress_snapshot(self.runtime({"a" * 32: record})), expected)
        for status in ("done", "ready", "error", "cancelled", "interrupted"):
            self.assertEqual(progress_snapshot(self.runtime({"a" * 32: {"status": status, "progress": 100}})), ("none", 0))

    def test_multiple_jobs_invalid_ids_and_value_before_paused_state(self):
        runtime = self.runtime({"a" * 32: {"progress": 40}, "b" * 32: {"progress": 80}, "../outside": {"progress": 1}})
        self.assertEqual(progress_snapshot(runtime), ("normal", 40))
        bar = NativeTaskbar.__new__(NativeTaskbar)
        bar.ctypes, bar.hwnd, bar.pointer, bar.last = ctypes, 123, ctypes.c_void_p(1), None
        bar.call = mock.Mock()
        bar.update("paused", 53)
        bar.update("paused", 53)
        self.assertEqual([call.args[0] for call in bar.call.call_args_list], [9, 10])
        self.assertEqual(bar.call.call_args.args, (10, 123, 8))
        bar.owned_com, bar.ole = True, mock.Mock()
        bar.close()
        bar.close()
        bar.ole.CoUninitialize.assert_called_once()
        self.assertFalse(bar.pointer.value)
        self.assertEqual(sum(call.args[0] == 2 for call in bar.call.call_args_list), 1)

    def test_ui_timer_restores_existing_minimized_window_and_updates_without_web_polling(self):
        shell = WindowsShell.__new__(WindowsShell)
        shell.closed, shell.pending_save, shell.last_maximized = False, 0, True
        shell.WindowState = SimpleNamespace(Minimized=1, Maximized=2, Normal=0)
        shell.form, shell.instance, shell.taskbar = mock.Mock(), mock.Mock(), mock.Mock()
        shell.form.WindowState = 1
        shell.form.Handle.ToInt64.return_value = 321
        shell.instance.consume_activation.return_value = True
        shell.runtime = self.runtime({"a" * 32: {"progress": 67}})
        shell.analyzing = lambda: False
        shell.tick(None, None)
        self.assertEqual(shell.form.WindowState, 2)
        shell.form.Show.assert_called_once()
        shell.form.Activate.assert_called_once()
        shell.instance.foreground.assert_called_once_with(321)
        shell.taskbar.update.assert_called_once_with("normal", 67)
        shell.timer = mock.Mock()
        bar = shell.taskbar
        shell.on_closed(None, None)
        shell.on_closed(None, None)
        bar.close.assert_called_once()
        shell.timer.Dispose.assert_called_once()


if __name__ == "__main__":
    unittest.main()
