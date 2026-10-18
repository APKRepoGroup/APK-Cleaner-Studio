import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "studio"))
import server


class JobTerminalRaceTests(unittest.TestCase):
    def test_terminal_state_wins_over_late_cancel_even_before_worker_cleanup(self):
        for status in ("done", "error", "cancelled"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                job_id = "c" * 32
                job = root / job_id
                job.mkdir()
                server.write_json(job / "analysis.json", {"owner_id": "owner"})
                terminal = {"status": status, "progress": 100, "result": {"output": "result.apk"}}
                server.write_json(job / "state.json", terminal)
                event = threading.Event()
                with mock.patch.object(server, "JOBS", root), mock.patch.object(server, "_ACTIVE_JOBS", {job_id}), mock.patch.object(server, "_JOB_CANCEL_EVENTS", {job_id: event}), mock.patch.object(server, "_JOB_THREADS", {job_id: 123}), mock.patch.object(server, "terminate_active_tools") as terminate:
                    accepted = server.cancel_clean_job(job_id, "owner", True)
                self.assertFalse(accepted)
                self.assertFalse(event.is_set())
                terminate.assert_not_called()
                self.assertEqual(server.read_json(job / "state.json"), terminal)

    def test_completion_during_tool_shutdown_cannot_be_overwritten_by_cancelling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job_id = "d" * 32
            job = root / job_id
            job.mkdir()
            server.write_json(job / "analysis.json", {"owner_id": "owner"})
            server.write_json(job / "state.json", {"status": "working", "progress": 99})
            def completed(_):
                server.write_json(job / "state.json", {"status": "cancelled", "progress": 0})
            with mock.patch.object(server, "JOBS", root), mock.patch.object(server, "_ACTIVE_JOBS", {job_id}), mock.patch.object(server, "_JOB_CANCEL_EVENTS", {job_id: threading.Event()}), mock.patch.object(server, "_JOB_THREADS", {job_id: 123}), mock.patch.object(server, "terminate_active_tools", side_effect=completed):
                self.assertTrue(server.cancel_clean_job(job_id, "owner", True))
            self.assertEqual(server.read_json(job / "state.json")["status"], "cancelled")


class InterruptedJobTests(unittest.TestCase):
    def make_job(self, root, status, job_id="e" * 32):
        job = root / job_id
        job.mkdir()
        (job / "source.apk").write_bytes(b"preserved-source")
        server.write_json(job / "analysis.json", {"filename": "Source.apk", "source_path": "source.apk", "owner_id": "owner"})
        server.write_json(job / "state.json", {"status": status, "message": "DEX doğrulanıyor", "events": [{"message": "Kaydedilen adım", "id": 1}]})
        return job

    def test_owned_session_reads_analysis_and_completed_result_without_starting_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = self.make_job(root, "done")
            handler = server.StudioHandler.__new__(server.StudioHandler)
            handler.path = f"/api/jobs/{job.name}/session"
            handler.client_address = ("127.0.0.1", 12345)
            handler.headers = {"Host": "127.0.0.1:8080"}
            analysis = server.read_json(job / "analysis.json")
            analysis["owner_id"] = server.client_identity("127.0.0.1", handler.headers)
            server.write_json(job / "analysis.json", analysis)
            server.write_json(job / "output/report.json", {"output": "result.apk", "signed": True})
            before = (job / "state.json").read_bytes()
            with mock.patch.object(server, "JOBS", root), mock.patch.object(handler, "send_json") as send, mock.patch.object(server, "start_clean_job") as start:
                handler.do_GET()
            self.assertEqual(send.call_args.args[0]["job"]["result"]["output"], "result.apk")
            self.assertEqual(send.call_args.args[0]["analysis"], analysis)
            self.assertEqual((job / "state.json").read_bytes(), before)
            start.assert_not_called()

    def test_startup_settles_orphan_work_without_deleting_sources_or_replaying_it(self):
        for status in ("analyzing", "working", "cancelling"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                job = self.make_job(root, status)
                with mock.patch.object(server, "JOBS", root), mock.patch.object(server, "_ACTIVE_JOBS", set()), mock.patch.object(server, "_SCANNING_JOBS", set()), mock.patch.object(server, "start_clean_job") as start:
                    self.assertEqual(server.reconcile_interrupted_jobs(), 1)
                    self.assertEqual(server.reconcile_interrupted_jobs(), 0)
                state = server.read_json(job / "state.json")
                self.assertEqual(state["status"], "error")
                self.assertTrue(state["interrupted"])
                self.assertEqual(state["events"][0]["id"], 1)
                self.assertEqual((job / "source.apk").read_bytes(), b"preserved-source")
                self.assertTrue((job / "diagnostic.json").is_file())
                start.assert_not_called()

    def test_live_workers_scans_and_terminal_jobs_are_untouched(self):
        for status, active, scanning in (("working", True, False), ("analyzing", False, True), ("done", False, False), ("error", False, False), ("cancelled", False, False), ("ready", False, False)):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                job = self.make_job(root, status)
                before = (job / "state.json").read_bytes()
                with mock.patch.object(server, "JOBS", root), mock.patch.object(server, "_ACTIVE_JOBS", {job.name} if active else set()), mock.patch.object(server, "_SCANNING_JOBS", {job.name} if scanning else set()):
                    self.assertEqual(server.reconcile_interrupted_jobs(), 0)
                self.assertEqual((job / "state.json").read_bytes(), before)

    def test_full_disk_does_not_prevent_startup_or_leave_a_dead_job_live(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = self.make_job(root, "working")
            with mock.patch.object(server, "JOBS", root), mock.patch.object(server, "_ACTIVE_JOBS", set()), mock.patch.object(server, "_SCANNING_JOBS", set()), mock.patch.object(server, "_INTERRUPTED_STATE_FALLBACKS", {}):
                with mock.patch.object(server, "write_json", side_effect=OSError("No space left on device")):
                    self.assertEqual(server.reconcile_interrupted_jobs(), 1)
                self.assertEqual(server.read_json(job / "state.json")["status"], "error")
                self.assertTrue(server.read_json(job / "state.json")["interrupted"])
                self.assertEqual(server.reconcile_interrupted_jobs(), 0)
                server.write_json(job / "state.json", {"status": "ready"})
                self.assertEqual(server.read_json(job / "state.json")["status"], "ready")
                self.assertEqual(server._INTERRUPTED_STATE_FALLBACKS, {})

    def test_interrupted_outputs_are_not_offered_as_completed_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = self.make_job(root, "working")
            output = job / "output"
            output.mkdir()
            (output / "partial.apk").write_bytes(b"partial")
            server.write_json(output / "report.json", {"output": "partial.apk"})
            with mock.patch.object(server, "JOBS", root), mock.patch.object(server, "_ACTIVE_JOBS", set()), mock.patch.object(server, "_SCANNING_JOBS", set()):
                server.reconcile_interrupted_jobs()
                row = server.list_job_history("owner", True)[0]
            self.assertTrue(row["interrupted"])
            self.assertFalse(row["has_output"])
            self.assertTrue(row["can_reuse"])
            self.assertTrue(row["can_delete"])
            self.assertTrue((output / "partial.apk").exists())

    def test_failed_worker_start_leaves_a_terminal_error_not_ghost_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = self.make_job(root, "ready")
            fake = mock.Mock()
            fake.start.side_effect = RuntimeError("cannot start new thread")
            with mock.patch.object(server, "JOBS", root), mock.patch.object(server, "_ACTIVE_JOBS", set()), mock.patch.object(server, "_SCANNING_JOBS", set()), mock.patch.object(server, "_JOB_CANCEL_EVENTS", {}), mock.patch.object(server.threading, "Thread", return_value=fake):
                with self.assertRaises(RuntimeError):
                    server.start_clean_job(job.name, {})
                self.assertNotIn(job.name, server._ACTIVE_JOBS)
            self.assertEqual(server.read_json(job / "state.json")["status"], "error")
