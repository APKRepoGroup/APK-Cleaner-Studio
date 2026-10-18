import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "studio"))
import engine
import server


class StoragePreflightTests(unittest.TestCase):
    def test_full_disk_during_job_claim_does_not_leave_an_active_worker_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job_id = "a" * 32
            server.write_json(root / job_id / "analysis.json", {"filename": "source.apk"})
            server.write_json(root / job_id / "state.json", {"status": "ready"})
            with mock.patch.object(server, "JOBS", root), mock.patch.object(server, "_ACTIVE_JOBS", set()), mock.patch.object(server, "_SCANNING_JOBS", set()), mock.patch.object(server, "_JOB_CANCEL_EVENTS", {}), mock.patch.object(server, "write_json", side_effect=OSError("No space left on device")), mock.patch.object(server.threading, "Thread") as worker:
                with self.assertRaises(OSError):
                    server.start_clean_job(job_id, {})
                self.assertEqual(server._ACTIVE_JOBS, set())
                self.assertEqual(server._JOB_CANCEL_EVENTS, {})
                worker.assert_not_called()
            self.assertEqual(server.read_json(root / job_id / "state.json")["status"], "ready")

    def test_completed_state_is_read_inside_the_claim_lock_and_never_replayed(self):
        def read(path):
            if path.name == "state.json":
                self.assertTrue(server._ACTIVE_JOBS_LOCK.locked())
                return {"status": "done", "result": {"output": "ready.apk"}}
            return {"filename": "source.apk"}
        with mock.patch.object(server, "read_json", side_effect=read), mock.patch.object(server, "_ACTIVE_JOBS", set()), mock.patch.object(server, "_SCANNING_JOBS", set()), mock.patch.object(server.threading, "Thread") as worker:
            self.assertEqual(server.start_clean_job("b" * 32, {})[0], "done")
            worker.assert_not_called()

    def test_owned_preflight_is_read_only_and_rejects_paths_outside_the_job(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(server, "JOBS", Path(directory)):
            job_id = "a" * 32
            job = Path(directory) / job_id
            job.mkdir()
            (job / "source.apks").write_bytes(b"fixture")
            handler = server.StudioHandler.__new__(server.StudioHandler)
            handler.path = f"/api/jobs/{job_id}/preflight"
            handler.client_address = ("127.0.0.1", 12345)
            handler.headers = {"Host": "127.0.0.1:8080"}
            owner = server.client_identity("127.0.0.1", handler.headers)
            for source, expected in (("source.apks", 200), ("../outside.apk", 404)):
                server.write_json(job / "analysis.json", {"owner_id": owner, "source_path": source, "split_merged": True})
                before = {str(path): path.read_bytes() for path in job.rglob("*") if path.is_file()}
                with mock.patch.object(handler, "send_json") as send, mock.patch.object(server, "storage_preflight", return_value={"status": "ok"}) as check:
                    handler.do_GET()
                if expected == 200:
                    check.assert_called_once_with((job / source).resolve(), job / "output", split=True)
                    self.assertEqual(send.call_args.args[0]["status"], "ok")
                else:
                    check.assert_not_called()
                    self.assertEqual(send.call_args.args[1], 404)
                self.assertEqual(before, {str(path): path.read_bytes() for path in job.rglob("*") if path.is_file()})

    def test_expanded_zip_and_shared_volume_are_estimated_without_inflating_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Private-name.apk"
            with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("classes.dex", b"x" * 1024 * 1024)
            before = source.read_bytes()
            with mock.patch.object(engine.tempfile, "gettempdir", return_value=str(root)), mock.patch.object(engine.shutil, "disk_usage", return_value=SimpleNamespace(free=10**10)):
                report = engine.storage_preflight(source, root / "not-created")
            self.assertEqual(report["status"], "ok")
            self.assertTrue(report["estimated"])
            self.assertEqual(len(report["volumes"]), 1)
            self.assertGreater(report["recommended_bytes"], len(before) * 2 + 2 * 1024 * 1024)
            self.assertNotIn(str(root), json.dumps(report))
            self.assertNotIn(source.name, json.dumps(report))
            self.assertEqual(source.read_bytes(), before)
            self.assertFalse((root / "not-created").exists())

    def test_critical_shortage_is_blocked_and_warning_does_not_claim_an_exact_requirement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sample.apk"
            source.write_bytes(b"sample")
            for free, status in ((1, "blocked"), (32 * 1024 * 1024 + 1, "warning"), (10**9, "ok")):
                with self.subTest(status=status), mock.patch.object(engine.tempfile, "gettempdir", return_value=str(root)), mock.patch.object(engine.shutil, "disk_usage", return_value=SimpleNamespace(free=free)):
                    report = engine.storage_preflight(source, root / "output")
                    self.assertEqual(report["status"], status)
                    if status == "blocked":
                        with self.assertRaisesRegex(RuntimeError, "kritik"):
                            engine.require_processing_space(source, root / "output")
                    else:
                        engine.require_processing_space(source, root / "output")

    def test_separate_temp_and_output_volumes_are_checked_independently(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            temporary = root / "temp"
            output.mkdir(); temporary.mkdir()
            source = root / "source.apk"
            source.write_bytes(b"sample")
            original_stat = Path.stat
            def stat(path, *args, **kwargs):
                values = list(original_stat(path, *args, **kwargs))
                values[2] = 7 if str(path).startswith(str(output)) else 8
                return os.stat_result(values)
            def disk(path):
                return SimpleNamespace(free=1 if str(path).startswith(str(temporary)) else 10**9)
            with mock.patch.object(engine.tempfile, "gettempdir", return_value=str(temporary)), mock.patch.object(Path, "stat", stat), mock.patch.object(engine.shutil, "disk_usage", side_effect=disk):
                report = engine.storage_preflight(source, output)
            self.assertEqual(len(report["volumes"]), 2)
            self.assertEqual(report["status"], "blocked")

    def test_unavailable_free_space_is_unknown_not_a_false_success(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.apk"
            source.write_bytes(b"sample")
            with mock.patch.object(engine.shutil, "disk_usage", side_effect=PermissionError("not readable")):
                report = engine.storage_preflight(source, source.parent / "output")
            self.assertEqual(report["status"], "unknown")
            self.assertIsNone(report["free_bytes"])
