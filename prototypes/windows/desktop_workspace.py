"""Separate desktop-layout experiment; neither normal UI nor preview v1 changes."""
from pathlib import Path
from urllib.parse import urlsplit

import desktop_preview as window_host

ASSETS = Path(__file__).with_name("workspace")
WORK = window_host.PROJECT / ".codex-temp-dev6" / "windows-workspace-prototype"
PORT = 18083
TITLE = "APK Cleaner Studio — Masaüstü Düzen Prototipi"
original_handler_for = window_host.handler_for


def handler_for(runtime, tools):
    class WorkspaceHandler(original_handler_for(runtime, tools)):
        def do_GET(self):
            if not self.request_origin_allowed():
                self.send_error(403)
                return
            path = urlsplit(self.path).path
            if path == "/":
                source = (runtime.WEB / "index.html").read_text(encoding="utf-8")
                source = source.replace('<html lang="tr"', '<html data-desktop-workspace="true" lang="tr"', 1)
                source = source.replace("</head>", '<link rel="stylesheet" href="/workspace-prototype.css"></head>', 1)
                source = source.replace("</body>", '<script src="/workspace-prototype.js"></script></body>', 1)
                self.send_prototype_text(source, "text/html", html=True)
            elif path in {"/workspace-prototype.css", "/workspace-prototype.js"}:
                suffix = path.rsplit(".", 1)[1]
                content_type = "text/css" if suffix == "css" else "text/javascript"
                self.send_prototype_text((ASSETS / f"workspace.{suffix}").read_text(encoding="utf-8"), content_type)
            else:
                super().do_GET()
    return WorkspaceHandler


class WorkspaceHost(window_host.PrototypeHost):
    def __init__(self, runtime, engine, port=PORT):
        super().__init__(runtime, engine, port=port)


def main():
    # Configuration is private to this new launcher process. The original
    # launcher, HTML, styles, app.js, data and WebView profile stay untouched.
    window_host.WORK = WORK
    window_host.TITLE = TITLE
    window_host.handler_for = handler_for
    window_host.PrototypeHost = WorkspaceHost
    return window_host.main()


if __name__ == "__main__":
    raise SystemExit(main())
