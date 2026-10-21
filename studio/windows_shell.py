"""Windows-only shell integration; pure geometry helpers remain testable anywhere."""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
import time


def number(value, fallback=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return fallback
    return value if math.isfinite(value) and abs(value) <= 1_000_000 else fallback


def restore_geometry(saved, monitors):
    """Return on-screen physical bounds from saved logical window preferences."""
    if not monitors:
        raise ValueError("Kullanılabilir ekran bulunamadı.")
    saved = saved if isinstance(saved, dict) and saved.get("schema") == 1 else {}
    target = next((area for area in monitors if area["name"] == saved.get("monitor")), monitors[0])
    scale = max(.5, min(4, number(target.get("dpi"), 96) / 96))
    min_width = min(round(760 * scale), target["width"])
    min_height = min(round(600 * scale), target["height"])
    width = min(target["width"], max(min_width, round(number(saved.get("width"), 1200) * scale)))
    height = min(target["height"], max(min_height, round(number(saved.get("height"), 860) * scale)))
    same_monitor = target["name"] == saved.get("monitor")
    offset_x = round(number(saved.get("offset_x")) * scale) if same_monitor else (target["width"] - width) // 2
    offset_y = round(number(saved.get("offset_y")) * scale) if same_monitor else (target["height"] - height) // 2
    x = target["x"] + max(0, min(offset_x, target["width"] - width))
    y = target["y"] + max(0, min(offset_y, target["height"] - height))
    return {"x": x, "y": y, "width": width, "height": height,
            "min_width": min_width, "min_height": min_height,
            "maximized": saved.get("maximized") is True}


def capture_geometry(bounds, monitor, maximized):
    scale = max(.5, min(4, number(monitor.get("dpi"), 96) / 96))
    return {"schema": 1, "monitor": monitor["name"],
            "width": round(bounds["width"] / scale), "height": round(bounds["height"] / scale),
            "offset_x": round((bounds["x"] - monitor["x"]) / scale),
            "offset_y": round((bounds["y"] - monitor["y"]) / scale), "maximized": bool(maximized)}


class WindowStateStore:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        try:
            if self.path.stat().st_size > 16384:
                return {}
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def save(self, value):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            logging.getLogger("desktop.shell").warning("Pencere ayarı kaydedilemedi", exc_info=True)


class WindowsShell:
    """Attach only on the WinForms UI thread (pywebview before_show)."""
    def __init__(self, form, runtime, state_path):
        from System.Drawing import Size
        from System.Windows.Forms import FormStartPosition, FormWindowState, Screen, Timer
        self.form, self.runtime = form, runtime
        self.Screen, self.WindowState = Screen, FormWindowState
        self.store = WindowStateStore(state_path)
        self.last_maximized = False
        self.pending_save = 0
        self.closed = False
        self.last_saved = None
        areas = [self.screen_info(screen) for screen in Screen.AllScreens]
        # Primary monitor is the predictable fallback after removing a screen.
        areas.sort(key=lambda area: not area["primary"])
        placement = restore_geometry(self.store.load(), areas)
        form.StartPosition = FormStartPosition.Manual
        form.MinimumSize = Size(placement["min_width"], placement["min_height"])
        form.SetBounds(placement["x"], placement["y"], placement["width"], placement["height"])
        if placement["maximized"]:
            form.WindowState = FormWindowState.Maximized
        self.last_maximized = placement["maximized"]
        self.handlers = [self.changed, self.on_closing, self.on_closed, self.tick]
        form.Move += self.changed
        form.Resize += self.changed
        # Registered after pywebview's handler, so a rejected close is respected.
        form.FormClosing += self.on_closing
        form.FormClosed += self.on_closed
        self.timer = Timer()
        self.timer.Interval = 400
        self.timer.Tick += self.tick
        self.timer.Start()

    def screen_info(self, screen):
        area = screen.WorkingArea
        dpi = 96
        try:
            import ctypes
            from ctypes import wintypes
            user = ctypes.WinDLL("user32")
            user.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
            user.MonitorFromPoint.restype = wintypes.HANDLE
            monitor = user.MonitorFromPoint(wintypes.POINT(area.X + 1, area.Y + 1), 2)
            x, y = ctypes.c_uint(), ctypes.c_uint()
            shcore = ctypes.WinDLL("shcore")
            shcore.GetDpiForMonitor.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                              ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
            if shcore.GetDpiForMonitor(monitor, 0, ctypes.byref(x), ctypes.byref(y)) == 0:
                dpi = x.value
        except (OSError, AttributeError):
            pass
        return {"name": str(screen.DeviceName), "primary": bool(screen.Primary), "dpi": dpi,
                "x": int(area.X), "y": int(area.Y), "width": int(area.Width), "height": int(area.Height)}

    def changed(self, sender, event):
        if self.form.WindowState != self.WindowState.Minimized:
            self.last_maximized = self.form.WindowState == self.WindowState.Maximized
        self.pending_save = time.monotonic() + .7

    def save(self):
        if self.closed:
            return
        normal = self.form.WindowState == self.WindowState.Normal
        bounds = self.form.Bounds if normal else self.form.RestoreBounds
        if bounds.Width <= 0 or bounds.Height <= 0:
            return
        screen = self.Screen.FromRectangle(bounds)
        value = capture_geometry({"x": int(bounds.X), "y": int(bounds.Y), "width": int(bounds.Width),
                                  "height": int(bounds.Height)}, self.screen_info(screen), self.last_maximized)
        if value != self.last_saved:
            self.store.save(value)
            self.last_saved = value
        self.pending_save = 0

    def tick(self, sender, event):
        if not self.closed and self.pending_save and time.monotonic() >= self.pending_save:
            self.save()

    def on_closing(self, sender, event):
        if not event.Cancel:
            self.save()

    def on_closed(self, sender, event):
        self.closed = True
        self.timer.Stop()
        self.timer.Dispose()
