import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "studio"))
import server


class HistorySearchTests(unittest.TestCase):
    def make_job(self, root, index, *, owner="owner", status="done", app="Uygulama", package="com.example.app", interrupted=False):
        job = root / f"{index:032x}"
        server.write_json(job / "analysis.json", {"filename": f"Paket-{index}.apk", "created_at": index,
                          "owner_id": owner, "package_info": {"app_name": app}, "package_name": package})
        server.write_json(job / "state.json", {"status": status, "interrupted": interrupted})
        return job

    def test_search_finds_older_records_beyond_the_default_twenty(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(server, "JOBS", Path(directory)):
            for index in range(30):
                self.make_job(Path(directory), index, app="Eski Özel Uygulama" if index == 0 else "Diğer")
            self.assertEqual(len(server.list_job_history("owner", False)), 20)
            page = server.job_history_page("owner", False, {"q": ["özel"]})
            self.assertEqual(page["total"], 1)
            self.assertEqual(page["jobs"][0]["job_id"], "0" * 32)

    def test_file_app_and_package_matching_is_case_insensitive_including_turkish_i(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(server, "JOBS", Path(directory)):
            self.make_job(Path(directory), 1, app="İŞIK Arşiv", package="com.example.archive")
            for text in ("paket-1", "IŞIK", "ışık", "işik", "com.example.ARCHIVE", "Arşiv"):
                with self.subTest(query=text):
                    self.assertEqual(server.job_history_page("owner", False, {"q": [text]})["total"], 1)

    def test_filters_and_pagination_never_leak_another_owners_records_or_counts(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(server, "JOBS", Path(directory)):
            for index in range(26):
                self.make_job(Path(directory), index, status="error", interrupted=index == 0)
            self.make_job(Path(directory), 100, owner="other", app="Hidden")
            self.make_job(Path(directory), 101, status="working")
            self.make_job(Path(directory), 102, status="cancelled")
            first = server.job_history_page("owner", False, {"status": ["error"]})
            second = server.job_history_page("owner", False, {"status": ["error"], "offset": ["20"]})
            self.assertEqual(first["total"], 26)
            self.assertEqual(len(first["jobs"]), 20)
            self.assertEqual(len(second["jobs"]), 6)
            self.assertTrue(first["has_more"]); self.assertFalse(second["has_more"])
            self.assertFalse({row["job_id"] for row in first["jobs"]} & {row["job_id"] for row in second["jobs"]})
            self.assertEqual(server.job_history_page("owner", False, {"q": ["Hidden"]})["total"], 0)
            for status in ("active", "cancelled", "interrupted"):
                self.assertEqual(server.job_history_page("owner", False, {"status": [status]})["total"], 1)

    def test_invalid_query_rejected_and_deleted_last_page_clamped(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(server, "JOBS", Path(directory)):
            self.make_job(Path(directory), 1)
            page = server.job_history_page("owner", False, {"offset": ["999"], "limit": ["999"]})
            self.assertEqual(page["offset"], 0); self.assertEqual(page["limit"], 50)
            for query in ({"status": ["unknown-filter"]}, {"limit": ["nan"]}, {"offset": ["1.5"]}):
                with self.assertRaises(ValueError): server.job_history_page("owner", False, query)

    def test_handler_applies_filters_and_reports_invalid_requests_in_turkish(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(server, "JOBS", Path(directory)):
            self.make_job(Path(directory), 1, status="cancelled")
            for query, expected_status in (("status=cancelled&q=Paket", None), ("status=invalid", 400)):
                handler = server.StudioHandler.__new__(server.StudioHandler)
                handler.path = "/api/history?" + query
                handler.client_address = ("127.0.0.1", 1234)
                handler.headers = {"Host": "127.0.0.1:8080"}
                with mock.patch.object(handler, "send_json") as send:
                    handler.do_GET()
                if expected_status:
                    self.assertEqual(send.call_args.args[1], expected_status)
                    self.assertIn("geçersiz", send.call_args.args[0]["error"])
                else:
                    self.assertEqual(send.call_args.args[0]["total"], 1)
