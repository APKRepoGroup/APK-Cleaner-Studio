"""Local desktop preferences, shared by HTTP handlers and the native UI timer."""
import json
from pathlib import Path
import threading

MODES = {"all", "errors", "off"}


class DesktopPreferences:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.mode = "all"
        try:
            if self.path.stat().st_size <= 4096:
                value = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(value, dict) and value.get("notifications") in MODES:
                    self.mode = value["notifications"]
        except (OSError, ValueError, TypeError):
            pass

    def state(self):
        with self.lock:
            return {"notifications": self.mode}

    def set_mode(self, mode):
        if not isinstance(mode, str) or mode not in MODES:
            raise ValueError("Bildirim tercihi geçersiz.")
        with self.lock:
            # Commit the in-memory preference only after the atomic save succeeds.
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps({"notifications": mode}), encoding="utf-8")
            temporary.replace(self.path)
            self.mode = mode
            return {"notifications": mode}
