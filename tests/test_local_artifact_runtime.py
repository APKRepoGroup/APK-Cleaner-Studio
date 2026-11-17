import json
from pathlib import Path
import tempfile
import unittest

from local_artifact_runtime import _native_ready_address, launch_arguments, local_open, local_package_server


class LocalArtifactRuntimeTests(unittest.TestCase):
    def test_update_fixture_overrides_cannot_enable_external_requests_or_change_data_root(self):
        for settings in ({'APK_CLEANER_UPDATE_URL':'https://example.invalid/manifest'},
                         {'APK_CLEANER_UPDATE_URL':'https://127.0.0.1:1234/manifest', 'APK_CLEANER_DATA_ROOT':'outside'}):
            with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
                with local_package_server(['must-not-be-launched'],folder,update_fixture=settings):
                    self.fail('An unsafe fixture must never launch a process.')

    def test_windows_exe_and_console_server_get_different_arguments(self):
        self.assertEqual(launch_arguments(['studio.exe'], 0, True), ['studio.exe', '--port', '0'])
        self.assertEqual(launch_arguments(['python', 'server.py'], 8021, False),
                         ['python', 'server.py', '--host', '127.0.0.1', '--port', '8021', '--no-open', '--no-trust-prompt'])

    def test_native_session_requires_ready_and_loopback(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'desktop-session.json'
            self.assertIsNone(_native_ready_address(path))
            for state, url, expected in (
                ('starting', 'http://127.0.0.1:8081/', None),
                ('ready', 'https://127.0.0.1:8081/', None),
                ('ready', 'http://127.0.0.1:8081/', 'http://127.0.0.1:8081'),
                ('ready', 'http://example.invalid:8081/', None),
                ('ready', 'http://127.0.0.1/', None),
            ):
                path.write_text(json.dumps(dict(state=state, url=url)), encoding='utf-8')
                self.assertEqual(_native_ready_address(path), expected)

    def test_http_helper_rejects_nonlocal_urls_before_connecting(self):
        for value in ('http://example.invalid/', 'https://127.0.0.1:1/', 'http://u@127.0.0.1:1/'):
            with self.assertRaises(ValueError):
                local_open(value)
