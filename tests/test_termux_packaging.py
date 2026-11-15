import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packaging"))
from build_termux import should_include


class TermuxPackagingTests(unittest.TestCase):
    def test_windows_shell_and_build_leftovers_are_not_distributed(self):
        for name in ("studio/desktop.py", "studio/desktop/network.html", "studio/desktop_output.py",
                     "studio/desktop_network.py", "studio/desktop_preferences.py", "studio/desktop_pairing.py",
                     "studio/windows_shell.py", "studio/tools/binary-xml-patcher.jar.new",
                     "studio/__pycache__/server.cpython-312.pyc", "studio/jobs/fixture.apk", "studio/tls/root.pem"):
            with self.subTest(name=name):
                self.assertFalse(should_include(Path(name)))

    def test_portable_entry_points_and_engine_resources_remain(self):
        for name in ("studio/server.py", "studio/local_tls.py", "studio/apply_termux_update.py",
                     "studio/web/theme.css", "studio/web/icons/patreon.svg", "studio/windows_vector.py",
                     "studio/tools/zipalign-win.exe", "studio/tools/binary-xml-patcher.jar"):
            with self.subTest(name=name):
                self.assertTrue(should_include(Path(name)))
