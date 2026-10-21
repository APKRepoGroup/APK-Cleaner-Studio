from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "studio"))
from desktop_preferences import DesktopPreferences
import desktop
import server


class PreferencesTests(unittest.TestCase):
    def test_persistence_validation_and_failed_save(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            preferences = DesktopPreferences(path)
            self.assertEqual(preferences.state(), {"notifications": "all"})
            for mode in ("errors", "off", "all"):
                preferences.set_mode(mode)
                self.assertEqual(DesktopPreferences(path).state()["notifications"], mode)
            for mode in ([], {}, True, None, "unknown"):
                with self.assertRaises(ValueError):
                    preferences.set_mode(mode)
            with mock.patch.object(Path, "replace", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    preferences.set_mode("off")
            self.assertEqual(preferences.state()["notifications"], "all")
            for value in ('{"notifications": []}', '{"notifications": "unknown"}', 'broken', 'x' * 5000):
                path.write_text(value, encoding="utf-8")
                self.assertEqual(DesktopPreferences(path).state()["notifications"], "all")

    def test_post_requires_exact_native_origin_and_valid_mode(self):
        preferences = mock.Mock()
        preferences.set_mode.return_value = {"notifications": "off"}
        handler = desktop.handler_for(server, desktop.OwnedTools(), preferences=preferences)
        request = handler.__new__(handler)
        request.path = "/api/desktop/preferences"
        request.server = mock.Mock(server_port=8081)
        request.read_body_json = lambda: {"notifications": "off"}
        request.request_origin_allowed = lambda: True
        request.send_json = mock.Mock()
        for origin in (None, "https://evil.example", "http://127.0.0.1:8080"):
            request.headers = {"Origin": origin}
            request.do_POST()
            self.assertEqual(request.send_json.call_args.args[1], 403)
        preferences.set_mode.assert_not_called()
        request.headers = {"Origin": "http://127.0.0.1:8081"}
        request.do_POST()
        preferences.set_mode.assert_called_once_with("off")
        self.assertEqual(request.send_json.call_args.args, ({"notifications": "off"},))


if __name__ == "__main__":
    unittest.main()
