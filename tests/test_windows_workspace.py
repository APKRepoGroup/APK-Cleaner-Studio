from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototypes/windows"))
sys.path.insert(0, str(ROOT / "studio"))
import desktop_preview
import desktop_workspace
import engine
import server


class WindowsWorkspaceTests(unittest.TestCase):
    def test_import_keeps_original_launcher_configuration(self):
        self.assertEqual(desktop_preview.PORT, 18082)
        self.assertEqual(desktop_workspace.PORT, 18083)
        self.assertNotEqual(desktop_preview.WORK, desktop_workspace.WORK)
        self.assertNotEqual(desktop_preview.TITLE, desktop_workspace.TITLE)
        self.assertIs(desktop_preview.handler_for, desktop_workspace.original_handler_for)

    def test_layout_and_assets_are_only_served_by_the_new_handler(self):
        source = ROOT / "studio/web/index.html"
        before = source.read_bytes()
        with tempfile.TemporaryDirectory(prefix="workspace-test-") as directory:
            with mock.patch.object(server, "JOBS", Path(directory) / "jobs"), \
                 mock.patch.object(desktop_preview, "handler_for", desktop_workspace.handler_for):
                host = desktop_workspace.WorkspaceHost(server, engine, port=0)
                host.start()
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                try:
                    for path, marker in (("", b'data-desktop-workspace="true"'),
                                         ("workspace-prototype.js", b'desktop-shell'),
                                         ("workspace-prototype.css", b'grid-template-columns:212px'),
                                         ("api/update", b'"available": false'),
                                         ("boot.js", b'No LAN HTTPS probe')):
                        with opener.open(host.url + path) as response:
                            self.assertEqual(response.status, 200)
                            self.assertIn(marker, response.read())
                finally:
                    host.stop()
        self.assertEqual(source.read_bytes(), before)
        self.assertNotIn(b'data-desktop-workspace', before)


if __name__ == "__main__":
    unittest.main()
