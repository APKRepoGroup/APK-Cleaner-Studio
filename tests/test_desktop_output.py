from pathlib import Path
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "studio"))
from desktop_output import (OutputFolderPreference, SavedOutputs, add_output_controls, choose_output_destination, expose_output_controls,
                            output_download_job, select_in_explorer, watch_output_downloads)

ORIGIN = "http://127.0.0.1:8081/"
JOB = "a" * 32
DOWNLOAD = f"{ORIGIN}api/jobs/{JOB}/download"


class Event(list):
    def __iadd__(self, handler):
        self.append(handler)
        return self

    def __isub__(self, handler):
        self.remove(handler)
        return self

    def fire(self, event=None):
        for handler in self[:]:
            handler(None, event)


class DesktopOutputTests(unittest.TestCase):
    def test_save_dialog_starts_in_remembered_folder_and_keeps_user_choice(self):
        owner, dialog = Mock(), Mock()
        folder = Path("C:/Örnek çıktı klasörü")
        dialog.ShowDialog.return_value = "ok"
        forms = SimpleNamespace(SaveFileDialog=Mock(return_value=dialog), DialogResult=SimpleNamespace(OK="ok"))

        def choose(_owner):
            self.assertEqual(dialog.InitialDirectory, str(folder))
            self.assertEqual(dialog.FileName, "Örnek.apk")
            dialog.FileName = str(folder / "Yeni ad.apk")
            return "ok"

        dialog.ShowDialog.side_effect = choose
        with patch.dict(sys.modules, {"System.Windows.Forms": forms}):
            self.assertEqual(choose_output_destination(owner, folder, "Örnek.apk", "Tüm dosyalar"), str(folder / "Yeni ad.apk"))
            dialog.ShowDialog.side_effect = None
            dialog.ShowDialog.return_value = "cancel"
            self.assertIsNone(choose_output_destination(owner, folder, "Örnek.apk", "Tüm dosyalar"))
        self.assertEqual(dialog.ShowDialog.call_args_list, [unittest.mock.call(owner), unittest.mock.call(owner)])
        self.assertEqual(dialog.Dispose.call_count, 2)

    def test_last_apk_folder_survives_restart_and_uses_final_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = root / "desktop-output-folder.json"
            saved_folder = root / "Çıktılar, 2026"
            saved_folder.mkdir()
            core = SimpleNamespace(DownloadStarting=Event(), PostWebMessageAsJson=Mock())

            def default_dialog(_sender, event):
                event.ResultFilePath = str(saved_folder / "Farklı ad.apk")

            core.DownloadStarting += default_dialog
            picker = Mock()
            preference = OutputFolderPreference(settings)
            watch_output_downloads(core, ORIGIN, SavedOutputs(preference), default_dialog=default_dialog,
                                   choose_destination=picker)
            self.assertEqual(len(core.DownloadStarting), 1)
            operation = SimpleNamespace(Uri=DOWNLOAD, StateChanged=Event(), State="InProgress")
            event = SimpleNamespace(DownloadOperation=operation, ResultFilePath=str(root / "ilk.apk"), Cancel=False)
            core.DownloadStarting.fire(event)
            picker.assert_not_called()
            self.assertEqual(Path(event.ResultFilePath).parent, saved_folder)
            self.assertFalse(settings.exists())
            output = Path(event.ResultFilePath)
            output.write_bytes(b"APK fixture")
            operation.ResultFilePath, operation.State = str(output), "Completed"
            operation.StateChanged.fire()
            self.assertEqual(json.loads(settings.read_text(encoding="utf-8")), {"directory": str(saved_folder)})

            restarted = OutputFolderPreference(settings)
            self.assertEqual(restarted.current(), saved_folder)
            core = SimpleNamespace(DownloadStarting=Event([default_dialog]), PostWebMessageAsJson=Mock())
            picker.return_value = str(root / "İkinci.apk")
            watch_output_downloads(core, ORIGIN, SavedOutputs(restarted), default_dialog=default_dialog,
                                   choose_destination=picker)
            operation.State = "InProgress"
            event.ResultFilePath = str(root / "Örnek.apk")
            core.DownloadStarting.fire(event)
            picker.assert_called_once_with(saved_folder, "Örnek.apk")
            self.assertEqual(event.ResultFilePath, str(root / "İkinci.apk"))
            self.assertEqual(restarted.current(), saved_folder)
            Path(event.ResultFilePath).touch()
            operation.ResultFilePath, operation.State = event.ResultFilePath, "Completed"
            operation.StateChanged.fire()
            self.assertEqual(OutputFolderPreference(settings).current(), root)

    def test_cancelled_interrupted_and_non_apk_downloads_preserve_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = root / "settings.json"
            preference = OutputFolderPreference(settings)
            original = root / "önceki"
            original.mkdir()
            preference.remember(original)
            picker, default_dialog = Mock(return_value=None), Mock()
            core = SimpleNamespace(DownloadStarting=Event([default_dialog]), PostWebMessageAsJson=Mock())
            watch_output_downloads(core, ORIGIN, SavedOutputs(preference), default_dialog=default_dialog,
                                   choose_destination=picker)
            operation = SimpleNamespace(Uri=DOWNLOAD, StateChanged=Event(), State="InProgress")
            event = SimpleNamespace(DownloadOperation=operation, ResultFilePath=str(root / "Örnek.apk"), Cancel=False)
            core.DownloadStarting.fire(event)
            self.assertTrue(event.Cancel)
            self.assertEqual(operation.StateChanged, [])
            default_dialog.assert_not_called()
            event.Cancel = False
            picker.return_value = str(root / "öteki.apk")
            core.DownloadStarting.fire(event)
            operation.State, operation.CanResume = "Interrupted", False
            operation.StateChanged.fire()
            self.assertEqual(operation.StateChanged, [])
            operation.Uri = DOWNLOAD.replace("/download", "/report")
            core.DownloadStarting.fire(event)
            default_dialog.assert_called_once_with(None, event)
            self.assertEqual(picker.call_count, 2)
            self.assertEqual(OutputFolderPreference(settings).current(), original)
            core.PostWebMessageAsJson.assert_not_called()

    def test_deleted_or_invalid_saved_folder_uses_default_save_dialog(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = root / "settings.json"
            for raw in (b"not json", b'{"directory":"relative"}', b'{"directory":null}',
                        json.dumps({"directory": str(root / "deleted")}).encode(),
                        json.dumps({"directory": str(root), "extra": "a" * 262144}).encode()):
                settings.write_bytes(raw)
                preference = OutputFolderPreference(settings)
                self.assertIsNone(preference.current())
                picker, default_dialog = Mock(), Mock()
                core = SimpleNamespace(DownloadStarting=Event([default_dialog]))
                watch_output_downloads(core, ORIGIN, SavedOutputs(preference), default_dialog=default_dialog,
                                       choose_destination=picker)
                operation = SimpleNamespace(Uri=DOWNLOAD, StateChanged=Event())
                event = SimpleNamespace(DownloadOperation=operation, Cancel=False)
                core.DownloadStarting.fire(event)
                default_dialog.assert_called_once_with(None, event)
                picker.assert_not_called()

    def test_preference_write_failure_does_not_prevent_a_completed_output_from_being_revealed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = root / "settings.json"
            preference = OutputFolderPreference(settings)
            output = root / "Çıktı.apk"
            output.touch()
            outputs = SavedOutputs(preference)
            with patch.object(Path, "replace", side_effect=PermissionError("read only")), self.assertLogs("desktop.output", level="WARNING"):
                self.assertTrue(outputs._record(JOB, str(output)))
            self.assertTrue(outputs.saved_output_exists(JOB))
            self.assertEqual(preference.current(), root)
            self.assertEqual(list(root.iterdir()), [output])
            self.assertTrue(outputs._record(JOB, str(output)))
            self.assertEqual(OutputFolderPreference(settings).current(), root)

    def test_bridge_exposes_only_queries_and_reveal_not_recording_arbitrary_paths(self):
        window = Mock()
        expose_output_controls(window, SavedOutputs())
        controls = window.expose.call_args.args
        self.assertEqual([action.__name__ for action in controls], ["saved_output_exists", "reveal_saved_output"])
        self.assertFalse(controls[0](JOB))
        self.assertFalse(controls[1]("C:/work/private.apk")["opened"])

    def test_only_actual_result_downloads_from_the_native_origin_are_tracked(self):
        self.assertEqual(output_download_job(DOWNLOAD + "?filename=sample.apk", ORIGIN), JOB)
        for uri in (DOWNLOAD.replace(":8081", ":8080"), DOWNLOAD.replace("http:", "https:"),
                    DOWNLOAD.replace("/download", "/report"), DOWNLOAD + "/more",
                    DOWNLOAD.replace(JOB, "../outside"), DOWNLOAD.replace("127.0.0.1", "127.0.0.1@other.example")):
            self.assertIsNone(output_download_job(uri, ORIGIN))

    def test_download_completion_uses_final_saved_path_not_initial_suggestion(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "Örnek, farklı ad.apk"
            outputs = SavedOutputs()
            core = SimpleNamespace(DownloadStarting=Event(), PostWebMessageAsJson=Mock())
            watch_output_downloads(core, ORIGIN, outputs)
            operation = SimpleNamespace(Uri=DOWNLOAD, StateChanged=Event(), State="InProgress",
                                        ResultFilePath=str(output.with_name("ilk.apk")))
            core.DownloadStarting.fire(SimpleNamespace(DownloadOperation=operation, Cancel=False))
            operation.StateChanged.fire()
            self.assertFalse(outputs.saved_output_exists(JOB))
            output.write_bytes(b"fixture")
            operation.State, operation.ResultFilePath = "Completed", str(output)
            operation.StateChanged.fire()
            self.assertEqual(operation.StateChanged, [])
            notice, = core.PostWebMessageAsJson.call_args.args
            self.assertEqual(json.loads(notice), {"type": "apk-cleaner-output-saved", "job": JOB})
            with patch("desktop_output.select_in_explorer") as reveal:
                self.assertEqual(outputs.reveal_saved_output(JOB), {"opened": True})
                reveal.assert_called_once_with(output)
                self.assertFalse(outputs.reveal_saved_output(str(output))["opened"])
                output.unlink()
                self.assertFalse(outputs.reveal_saved_output(JOB)["opened"])
                self.assertEqual(reveal.call_count, 1)

    def test_cancelled_and_non_apk_downloads_are_not_exposed(self):
        with tempfile.TemporaryDirectory() as directory:
            partial = Path(directory) / "sample.apk"
            partial.write_bytes(b"partial fixture")
            outputs = SavedOutputs()
            core = SimpleNamespace(DownloadStarting=Event(), PostWebMessageAsJson=Mock())
            watch_output_downloads(core, ORIGIN, outputs)
            for status, filename in (("Interrupted", partial), ("Completed", partial.with_suffix(".txt"))):
                filename.touch()
                operation = SimpleNamespace(Uri=DOWNLOAD, StateChanged=Event(), State=status,
                                            CanResume=False, ResultFilePath=str(filename))
                core.DownloadStarting.fire(SimpleNamespace(DownloadOperation=operation, Cancel=False))
                operation.StateChanged.fire()
                self.assertEqual(operation.StateChanged, [])
            core.PostWebMessageAsJson.assert_not_called()
            self.assertFalse(outputs.saved_output_exists(JOB))

    def test_windows_shell_selects_one_absolute_item_and_releases_com_memory(self):
        shell, ole = Mock(), Mock()
        ole.CoInitializeEx.return_value = 0
        def parse(_path, _binding, result, _attrs, _out_attrs):
            result._obj.value = 123
            return 0
        shell.SHParseDisplayName.side_effect = parse
        shell.SHOpenFolderAndSelectItems.return_value = 0
        path = Path("C:/work/Örnek, paket.apk")
        with patch("desktop_output.ctypes.WinDLL", side_effect=[shell, ole], create=True):
            select_in_explorer(path)
        item, count, children, flags = shell.SHOpenFolderAndSelectItems.call_args.args
        self.assertEqual((item.value, count, children, flags), (123, 0, None, 0))
        self.assertEqual(shell.SHParseDisplayName.call_args.args[0], str(path))
        ole.CoTaskMemFree.assert_called_once_with(item)
        ole.CoUninitialize.assert_called_once()

    def test_output_control_is_injected_only_in_desktop_html(self):
        shared = (ROOT / "studio/web/index.html").read_text(encoding="utf-8")
        self.assertNotIn('id="revealSavedOutput"', shared)
        page = add_output_controls(shared)
        self.assertIn('id="revealSavedOutput" type="button" class="secondary hidden" disabled', page)
        self.assertIn('src="/desktop-output.js"', page)
        self.assertLess(page.index('id="downloadButton"'), page.index('id="revealSavedOutput"'))
        self.assertLess(page.index('id="revealSavedOutput"'), page.index('id="reportButton"'))
