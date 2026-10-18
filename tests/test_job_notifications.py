import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "studio"))
import server


class JobNotificationTests(unittest.TestCase):
    def test_native_bridge_is_android_only_validated_and_best_effort(self):
        native = mock.Mock()
        java = types.SimpleNamespace(jclass=mock.Mock(return_value=native))
        with mock.patch.dict(sys.modules, {"java": java}), mock.patch.object(server, "ANDROID_RUNTIME", False):
            server.notify_job_outcome("a" * 32, "done", "App.apk", "b" * 32)
            java.jclass.assert_not_called()
        with mock.patch.dict(sys.modules, {"java": java}), mock.patch.object(server, "ANDROID_RUNTIME", True):
            for job_id, status in (("invalid", "done"), ("a" * 32, "working"), ("a" * 32, "cancelled")):
                server.notify_job_outcome(job_id, status, "App.apk", "b" * 32)
            java.jclass.assert_not_called()
            native.publish.side_effect = RuntimeError("permission/channel unavailable")
            server.notify_job_outcome("a" * 32, "done", "App.apk", "b" * 32)
            native.publish.assert_called_once_with("a" * 32, "done", "App.apk", "b" * 32)

    def test_outcome_emitted_once_after_terminal_commit_and_worker_cleanup(self):
        for status in ("done", "error", "cancelled"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                job = root / ("c" * 32)
                job.mkdir()
                (job / "source.apk").write_bytes(b"original")
                server.write_json(job / "analysis.json", {"filename": "App.apk", "prepared_path": "source.apk", "source_path": "source.apk"})
                error = server.JobCancelled("İptal") if status == "cancelled" else ValueError("İşlem başarısız") if status == "error" else None
                events = []

                def notify(job_id, terminal, filename, event_id):
                    self.assertEqual(server.read_json(job / "state.json")["status"], status)
                    self.assertNotIn(job_id, server._ACTIVE_JOBS)
                    self.assertNotIn(job_id, server._JOB_THREADS)
                    self.assertEqual(len(event_id), 32)
                    events.append((job_id, terminal, filename))

                with mock.patch.object(server, "JOBS", root), mock.patch.object(server, "_ACTIVE_JOBS", {job.name}), mock.patch.object(server, "_JOB_THREADS", {}), mock.patch.object(server, "_JOB_CANCEL_EVENTS", {}), mock.patch.object(server, "require_processing_space"), mock.patch.object(server, "reset_tool_cancellation"), mock.patch.object(server, "process_apk", side_effect=error, return_value={"output": "out.apk"}), mock.patch.object(server, "notify_job_outcome", side_effect=notify):
                    server._execute_clean_job(job.name, {"profile": "balanced", "operation": "patch"})
                self.assertEqual(events, [] if status == "cancelled" else [(job.name, status, "App.apk")])
                self.assertEqual((job / "source.apk").read_bytes(), b"original")

    def test_native_result_contract_covers_permission_lock_screen_and_unique_intents(self):
        source = (ROOT / "android/app/src/main/java/com/apkcleaner/studio/JobNotifications.java").read_text(encoding="utf-8")
        for fragment in ("getApplicationContext()", "POST_NOTIFICATIONS", "areNotificationsEnabled()",
                         "power.isInteractive()", "!keyguard.isKeyguardLocked()", "FLAG_IMMUTABLE",
                         "VISIBILITY_PRIVATE", "setPublicVersion(publicVersion)", "setData(Uri.parse(",
                         'manager.notify("job:" + jobId, 32, result)', "delivered.size() > 64"):
            self.assertIn(fragment, source)
        self.assertNotIn("startActivity(", source)
        self.assertNotIn("getActivity(context, 1,", source)
