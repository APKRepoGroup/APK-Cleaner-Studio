"""Track and reveal APKs actually saved by the Windows application."""
from collections import OrderedDict
import ctypes
import json
import logging
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from threading import Lock
from urllib.parse import urlsplit


JOB_ID = re.compile(r"[a-f0-9]{32}")
MAX_FOLDER_SETTING_BYTES = 256 * 1024


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


class OutputFolderPreference:
    def __init__(self, path):
        self.path = Path(path)
        self._lock = Lock()
        self._folder = None
        try:
            with self.path.open("rb") as settings:
                raw = settings.read(MAX_FOLDER_SETTING_BYTES + 1)
            if len(raw) <= MAX_FOLDER_SETTING_BYTES:
                value = json.loads(raw)
                folder = value.get("directory") if isinstance(value, dict) else None
                if isinstance(folder, str) and "\0" not in folder and Path(folder).is_absolute():
                    self._folder = Path(folder)
        except (OSError, ValueError, RecursionError):
            pass  # Missing or corrupt preferences must not affect downloading.

    def current(self):
        with self._lock:
            folder = self._folder
        try:
            return folder if folder is not None and folder.is_dir() else None
        except OSError:
            return None

    def remember(self, folder):
        with self._lock:
            self._folder = folder
            temporary = None
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                        prefix="output-folder-", suffix=".tmp", delete=False) as settings:
                    temporary = Path(settings.name)
                    json.dump({"directory": str(folder)}, settings, ensure_ascii=False)
                temporary.replace(self.path)
            except OSError:
                logging.getLogger("desktop.output").warning("Son APK kayıt klasörü diske kaydedilemedi")
                if temporary is not None:
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        pass


def choose_output_destination(form, directory, filename, all_files_label):
    from System.Windows.Forms import DialogResult, SaveFileDialog

    dialog = SaveFileDialog()
    try:
        dialog.InitialDirectory = str(directory)
        dialog.FileName = filename
        dialog.Filter = f"{all_files_label} (*.*)|*.*"
        dialog.RestoreDirectory = True
        return str(dialog.FileName) if dialog.ShowDialog(form) == DialogResult.OK else None
    finally:
        dialog.Dispose()


class SavedOutputs:
    def __init__(self, folder_preference=None):
        self._paths = OrderedDict()
        self._lock = Lock()
        self._folder_preference = folder_preference

    def _last_folder(self):
        return self._folder_preference.current() if self._folder_preference is not None else None

    def _record(self, job, filename):
        path = Path(filename)
        if not JOB_ID.fullmatch(job) or not path.is_absolute() or path.suffix.lower() != ".apk" or not path.is_file():
            return False
        with self._lock:
            self._paths[job] = path
            self._paths.move_to_end(job)
            if len(self._paths) > 100:
                self._paths.popitem(last=False)
        if self._folder_preference is not None:
            self._folder_preference.remember(path.parent)
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


def watch_output_downloads(core, origin, outputs, *, default_dialog=None, choose_destination=None):
    def starting(sender, event):
        operation = event.DownloadOperation
        job = output_download_job(str(operation.Uri), origin)
        if default_dialog is not None:
            folder = outputs._last_folder() if job else None
            if folder is None:
                default_dialog(sender, event)
            else:
                try:
                    destination = choose_destination(folder, Path(str(event.ResultFilePath)).name)
                    if destination is None:
                        event.Cancel = True
                    else:
                        event.ResultFilePath = destination
                except Exception:
                    logging.getLogger("desktop.output").exception("Son kayıt klasörü açılamadı; varsayılan pencere kullanılıyor")
                    default_dialog(sender, event)
        if not job or event.Cancel:
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

    # pywebview already installed its own SaveFileDialog handler. Replace it
    # with this wrapper; it still handles reports and the default directory.
    if default_dialog is not None:
        core.DownloadStarting -= default_dialog
    try:
        core.DownloadStarting += starting
    except Exception:
        if default_dialog is not None:
            core.DownloadStarting += default_dialog
        raise
    return starting
