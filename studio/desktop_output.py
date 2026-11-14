"""Reveal only APKs actually saved by the Windows application's WebView."""
from collections import OrderedDict
import ctypes
import json
import logging
from pathlib import Path
import re
from threading import Lock
from urllib.parse import urlsplit


JOB_ID = re.compile(r"[a-f0-9]{32}")


def add_output_controls(page):
    button = ('<button id="revealSavedOutput" type="button" class="secondary hidden" disabled '
              'title="APK kaydedildikten sonra konumunu açar">Klasörde göster</button>')
    return (page.replace('<button id="reportButton"', button + '<button id="reportButton"', 1)
            .replace('</body>', '<script src="/desktop-output.js" defer></script></body>', 1))


def output_download_job(uri, origin):
    try:
        address = urlsplit(uri)
        expected = urlsplit(origin)
        if (address.scheme, address.netloc) != (expected.scheme, expected.netloc):
            return None
        match = re.fullmatch(r"/api/jobs/([a-f0-9]{32})/download", address.path)
        return match.group(1) if match else None
    except ValueError:
        return None


def expose_output_controls(window, outputs):
    # Expose two functions rather than a stateful object with private members.
    def saved_output_exists(job):
        return outputs.saved_output_exists(job)

    def reveal_saved_output(job):
        return outputs.reveal_saved_output(job)

    window.expose(saved_output_exists, reveal_saved_output)


def select_in_explorer(path):
    # Use the Shell item API, not a command line assembled from a file path.
    shell = ctypes.WinDLL("shell32")
    ole = ctypes.WinDLL("ole32")
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    ole.CoInitializeEx.restype = ctypes.c_long
    ole.CoUninitialize.restype = None
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole.CoTaskMemFree.restype = None
    shell.SHParseDisplayName.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_ulong, ctypes.c_void_p]
    shell.SHParseDisplayName.restype = ctypes.c_long
    shell.SHOpenFolderAndSelectItems.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_ulong]
    shell.SHOpenFolderAndSelectItems.restype = ctypes.c_long
    if ole.CoInitializeEx(None, 2) < 0:
        raise OSError("Windows dosya gezgini başlatılamadı.")
    item = ctypes.c_void_p()
    try:
        if shell.SHParseDisplayName(str(path), None, ctypes.byref(item), 0, None) < 0 or not item:
            raise OSError("Kaydedilen APK bulunamadı.")
        if shell.SHOpenFolderAndSelectItems(item, 0, None, 0) < 0:
            raise OSError("APK'nın bulunduğu klasör açılamadı.")
    finally:
        if item:
            ole.CoTaskMemFree(item)
        ole.CoUninitialize()


class SavedOutputs:
    def __init__(self):
        self._paths = OrderedDict()
        self._lock = Lock()

    def _record(self, job, filename):
        path = Path(filename)
        if not JOB_ID.fullmatch(job) or not path.is_absolute() or path.suffix.lower() != ".apk" or not path.is_file():
            return False
        with self._lock:
            self._paths[job] = path
            self._paths.move_to_end(job)
            if len(self._paths) > 100:
                self._paths.popitem(last=False)
        return True

    def _saved_path(self, job):
        if not isinstance(job, str) or not JOB_ID.fullmatch(job):
            return None
        with self._lock:
            path = self._paths.get(job)
        return path if path and path.is_file() else None

    def saved_output_exists(self, job):
        return self._saved_path(job) is not None

    def reveal_saved_output(self, job):
        try:
            path = self._saved_path(job)
            if not path:
                return {"opened": False, "error": "Kaydedilen APK bulunamadı. Dosyayı yeniden indir."}
            select_in_explorer(path)
            return {"opened": True}
        except OSError:
            return {"opened": False, "error": "APK'nın bulunduğu klasör açılamadı."}


def watch_output_downloads(core, origin, outputs):
    def starting(_sender, event):
        operation = event.DownloadOperation
        job = output_download_job(str(operation.Uri), origin)
        if not job:
            return

        def state_changed(_sender, _event):
            status = str(operation.State)
            if status == "InProgress" or (status == "Interrupted" and operation.CanResume):
                return
            operation.StateChanged -= state_changed
            if status == "Completed":
                try:
                    if outputs._record(job, str(operation.ResultFilePath)):
                        core.PostWebMessageAsJson(json.dumps({"type": "apk-cleaner-output-saved", "job": job}))
                except Exception:
                    logging.getLogger("desktop.output").exception("Kaydedilen APK sonucu okunamadı")

        operation.StateChanged += state_changed

    core.DownloadStarting += starting
    return starting
