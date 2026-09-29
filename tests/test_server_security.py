import sys
import io
import hashlib
import os
import tempfile
import stat
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "studio"))

from server import StudioHandler, _ACTIVE_JOBS, _ACTIVE_JOBS_LOCK, _BLOCKED_CLIENTS, _CLIENTS, _CLIENTS_LOCK, _JOB_CANCEL_EVENTS, _JOB_THREADS, cancel_clean_job, cleanup_stale_jobs, client_identity, clone_job_for_reuse, delete_job_history, diagnostic_report, direct_https_target, effective_client_address, failure_diagnostic, lan_https_target, list_job_history, list_job_storage, manage_client, observe_public_origin, preferred_browser_url, public_https_target, read_json, record_blocked_client_details, record_client, request_client_access, start_clean_job, write_json


class LocalRequestSecurityTests(unittest.TestCase):
    def test_storage_summary_counts_only_visible_job_files_and_protects_active_jobs(self):
        with tempfile.TemporaryDirectory() as name, mock.patch("server.JOBS", Path(name)):
            owner = "owner-123"
            own_id, other_id = "a" * 32, "b" * 32
            for job_id, identity in ((own_id, owner), (other_id, "other-456")):
                job = Path(name) / job_id
                (job / "output").mkdir(parents=True)
                write_json(job / "analysis.json", {"owner_id": identity, "source_path": "source.apks", "filename": "source.apks"})
                write_json(job / "state.json", {"status": "done"})
                (job / "source.apks").write_bytes(b"s" * 5)
                (job / "output" / "result.apk").write_bytes(b"o" * 7)
                (job / "work.tmp").write_bytes(b"w" * 3)
            with _ACTIVE_JOBS_LOCK:
                _ACTIVE_JOBS.add(own_id)
            try:
                result = list_job_storage(owner, False)
                self.assertEqual(len(result["jobs"]), 1)
                self.assertEqual(result["jobs"][0]["job_id"], own_id)
                self.assertEqual(result["jobs"][0]["sizes"]["source"], 5)
                self.assertEqual(result["jobs"][0]["sizes"]["output"], 7)
                self.assertGreaterEqual(result["jobs"][0]["sizes"]["working"], 3)
                self.assertFalse(result["jobs"][0]["can_delete"])
                with self.assertRaises(ValueError):
                    delete_job_history(own_id, owner, False)
            finally:
                with _ACTIVE_JOBS_LOCK:
                    _ACTIVE_JOBS.discard(own_id)

    def test_diagnostic_preview_hides_identifiers_and_untrusted_error_text(self):
        with tempfile.TemporaryDirectory() as name, mock.patch("server.ANDROID_RUNTIME", False):
            job = Path(name)
            write_json(job / "analysis.json", {"filename": "private-app.apk", "package_name": "test.private.app"})
            write_json(job / "state.json", {"status": "error"})
            error = RuntimeError("private-app.apk --ks-pass pass:secret başarısız oldu (1)")
            write_json(job / "diagnostic.json", failure_diagnostic(error))
            preview = diagnostic_report(job)
            self.assertNotIn("private-app.apk", preview)
            self.assertNotIn("test.private.app", preview)
            self.assertNotIn("pass:secret", preview)
            self.assertIn("Gömülü araç çıkış kodu: 1", preview)
            opted_in = diagnostic_report(job, include_identifiers=True)
            self.assertIn("private-app.apk", opted_in)
            self.assertIn("test.private.app", opted_in)

    def test_remote_client_cannot_open_diagnostic_report(self):
        handler = StudioHandler.__new__(StudioHandler)
        handler.path = "/api/diagnostic"
        handler.client_address = ("10.10.30.45", 12345)
        handler.headers = {"Host": "10.10.30.33:8080", "X-Client-ID": "remote-client-123"}
        with mock.patch.object(handler, "send_json") as send_json, mock.patch.object(handler, "send_diagnostic") as send_diagnostic:
            handler.do_GET()
        self.assertEqual(send_json.call_args.args[1], 403)
        send_diagnostic.assert_not_called()

    def handler(self, host: str, origin: str | None = None):
        instance = StudioHandler.__new__(StudioHandler)
        instance.headers = {"Host": host}
        if origin is not None:
            instance.headers["Origin"] = origin
        return instance

    def test_loopback_and_private_network_origins_are_allowed(self):
        self.assertTrue(self.handler("127.0.0.1:8080", "http://127.0.0.1:8080").request_origin_allowed())
        self.assertTrue(self.handler("10.10.30.33:8080", "http://10.10.30.33:8080").request_origin_allowed())

    def test_foreign_origin_and_public_host_are_rejected(self):
        self.assertFalse(self.handler("127.0.0.1:8080", "https://example.com").request_origin_allowed())
        self.assertFalse(self.handler("example.com", "https://example.com").request_origin_allowed())

    def test_non_browser_local_request_without_origin_is_allowed(self):
        self.assertTrue(self.handler("localhost:8080").request_origin_allowed())

    def test_loopback_identity_is_stable_across_http_https_browser_ids(self):
        http_id = client_identity("127.0.0.1", {"X-Client-ID": "http-client-1234"})
        https_id = client_identity("127.0.0.1", {"X-Client-ID": "https-client-5678"})
        ipv6_id = client_identity("::1", {})
        self.assertEqual(http_id, https_id)
        self.assertEqual(http_id, ipv6_id)

    def test_tls_probe_does_not_create_a_client_session(self):
        handler = StudioHandler.__new__(StudioHandler)
        handler.path = "/api/status?tls_probe=1"
        handler.client_address = ("127.0.0.1", 12345)
        handler.headers = {
            "Host": "127.0.0.1:8080",
            "Origin": "http://127.0.0.1:8080",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/123",
        }
        with mock.patch.object(handler, "send_json") as send_json, mock.patch("server.record_client") as record:
            handler.do_GET()
        record.assert_not_called()
        send_json.assert_called_once_with({"ok": True, "tls": True})

    def test_remote_client_cannot_read_another_jobs_state_report_or_apk(self):
        with tempfile.TemporaryDirectory() as name, mock.patch("server.JOBS", Path(name)):
            job_id = "a" * 32
            job = Path(name) / job_id
            job.mkdir()
            owner = client_identity("10.10.30.44", {"X-Client-ID": "owner-client-123"})
            write_json(job / "analysis.json", {"owner_id": owner})
            for action in ("state", "report", "download"):
                handler = StudioHandler.__new__(StudioHandler)
                handler.path = f"/api/jobs/{job_id}/{action}"
                handler.client_address = ("10.10.30.45", 12345)
                handler.headers = {"Host": "10.10.30.33:8080", "X-Client-ID": "other-client-123"}
                with mock.patch.object(handler, "send_json") as send_json, mock.patch.object(handler, "send_file") as send_file:
                    handler.do_GET()
                self.assertEqual(send_json.call_args.args[1], 403, action)
                send_file.assert_not_called()
            handler = StudioHandler.__new__(StudioHandler)
            handler.path = f"/api/jobs/{job_id}/reuse"
            handler.client_address = ("10.10.30.45", 12345)
            handler.headers = {"Host": "10.10.30.33:8080", "X-Client-ID": "other-client-123"}
            with mock.patch.object(handler, "send_json") as send_json:
                handler.do_POST()
            self.assertEqual(send_json.call_args.args[1], 403)

    def test_client_cookie_matches_header_identity_and_blocks_full_interface(self):
        client_value = "blocked-browser-123"
        client_id = client_identity("10.10.30.44", {"X-Client-ID": client_value})
        cookie_id = client_identity("10.10.30.44", {"Cookie": f"apk_cleaner_client_id={client_value}"})
        self.assertEqual(client_id, cookie_id)
        handler = StudioHandler.__new__(StudioHandler)
        handler.client_address = ("10.10.30.44", 12345)
        handler.headers = {"Cookie": f"apk_cleaner_client_id={client_value}"}
        with _CLIENTS_LOCK:
            _BLOCKED_CLIENTS.add(client_id)
        try:
            self.assertTrue(handler.requester_is_blocked())
        finally:
            with _CLIENTS_LOCK:
                _BLOCKED_CLIENTS.discard(client_id)

    def test_captured_client_id_is_not_portable_to_another_network_address(self):
        headers = {"X-Client-ID": "captured-client-123"}
        self.assertNotEqual(
            client_identity("10.10.30.44", headers),
            client_identity("10.10.30.45", headers),
        )

    def test_generic_keenetic_proxy_origin_is_allowed_only_from_local_router(self):
        handler = self.handler("10.10.30.33:8080", "https://studio-test.keenetic.link")
        handler.headers["X-Forwarded-Host"] = "studio-test.keenetic.link"
        handler.client_address = ("10.10.30.1", 12345)
        with mock.patch.dict(os.environ, {"APK_CLEANER_TRUSTED_PROXY": "10.10.30.1"}):
            self.assertTrue(handler.request_origin_allowed())
        handler.client_address = ("8.8.8.8", 12345)
        self.assertFalse(handler.request_origin_allowed())

    def test_trusted_https_proxy_origin_is_learned_for_lan_upgrade(self):
        with tempfile.TemporaryDirectory() as name, mock.patch("server._PUBLIC_HTTPS_ORIGIN", ""):
            headers = {
                "Host": "10.10.30.33:8080",
                "X-Forwarded-Host": "studio-test.keenetic.link",
                "X-Forwarded-Proto": "https",
            }
            with mock.patch.dict(os.environ, {"APK_CLEANER_TRUSTED_PROXY": "10.10.30.1"}):
                self.assertEqual(observe_public_origin("10.10.30.1", headers), "https://studio-test.keenetic.link/")
            self.assertFalse((Path(name) / "public-origin.json").exists())
            self.assertEqual(observe_public_origin("10.10.30.1", {**headers, "X-Forwarded-Proto": "http"}), "")
            self.assertEqual(observe_public_origin("8.8.8.8", headers), "")
            self.assertEqual(observe_public_origin("10.10.30.1", {**headers, "X-Forwarded-Host": "example.com"}), "")

    def test_only_public_reverse_proxy_http_is_upgraded_to_https(self):
        public_headers = {
            "Host": "10.10.30.36:8080",
            "X-Forwarded-Host": "studio-test.keenetic.link",
            "X-Forwarded-Proto": "http",
        }
        self.assertEqual(
            public_https_target(public_headers, "/api/status?fresh=1"),
            "https://studio-test.keenetic.link/api/status?fresh=1",
        )
        self.assertEqual(public_https_target({"Host": "127.0.0.1:8080"}, "/"), "")
        self.assertEqual(public_https_target({**public_headers, "X-Forwarded-Proto": "https"}, "/"), "")

    def test_direct_local_http_is_upgraded_on_the_same_port(self):
        self.assertEqual(
            direct_https_target(False, {"Host": "127.0.0.1:8080"}, "/api/status?fresh=1"),
            "https://127.0.0.1:8080/api/status?fresh=1",
        )
        self.assertEqual(direct_https_target(True, {"Host": "127.0.0.1:8080"}, "/"), "")
        self.assertEqual(direct_https_target(False, {"Host": "127.0.0.1:8080", "X-Forwarded-Proto": "https"}, "/"), "")
        self.assertEqual(direct_https_target(False, {"Host": "example.com"}, "/"), "")

    def test_local_ca_bootstrap_download_is_not_redirected(self):
        handler = StudioHandler.__new__(StudioHandler)
        handler.path = "/local-ca.crt"
        self.assertFalse(handler.redirect_secure_http())

    def test_lan_http_remains_available_without_forced_https(self):
        handler = self.handler("10.10.30.33:8080")
        handler.path = "/"
        self.assertFalse(handler.redirect_secure_http())

    def test_lan_http_uses_only_the_locally_learned_https_origin(self):
        headers = {"Host": "10.10.30.36:8080"}
        with mock.patch("server._PUBLIC_HTTPS_ORIGIN", "https://studio-test.keenetic.link/"):
            self.assertEqual(
                lan_https_target("10.10.30.37", headers, "/api/status?fresh=1"),
                "https://studio-test.keenetic.link/api/status?fresh=1",
            )
            self.assertEqual(
                lan_https_target("127.0.0.1", {"Host": "127.0.0.1:8080"}, "/"),
                "https://studio-test.keenetic.link/",
            )
            self.assertEqual(preferred_browser_url("http://127.0.0.1:8080/"), "https://studio-test.keenetic.link/")
        with mock.patch("server._PUBLIC_HTTPS_ORIGIN", ""):
            self.assertEqual(lan_https_target("10.10.30.37", headers, "/"), "")
            self.assertEqual(preferred_browser_url("http://127.0.0.1:8080/"), "http://127.0.0.1:8080/")

    def test_trusted_local_proxy_exposes_public_client_ip_without_accepting_public_spoofing(self):
        proxy = {"X-Forwarded-Host": "studio-test.keenetic.link", "X-Forwarded-For": "1.1.1.1"}
        with mock.patch.dict(os.environ, {"APK_CLEANER_TRUSTED_PROXY": "10.10.30.1"}):
            self.assertEqual(effective_client_address("10.10.30.1", proxy), "1.1.1.1")
            self.assertEqual(effective_client_address("10.10.30.1", {**proxy, "X-Forwarded-For": "9.9.9.9, 1.1.1.1"}), "1.1.1.1")
        self.assertEqual(effective_client_address("10.10.30.1", {"X-Forwarded-For": "1.1.1.1"}), "10.10.30.1")
        self.assertEqual(effective_client_address("8.8.8.8", {"X-Forwarded-For": "1.1.1.1"}), "8.8.8.8")

    def test_remote_client_cannot_trigger_tool_installation(self):
        handler = StudioHandler.__new__(StudioHandler)
        handler.path = "/api/setup"
        handler.client_address = ("10.10.30.45", 12345)
        handler.headers = {"Host": "10.10.30.33:8080", "X-Client-ID": "remote-client-123"}
        with mock.patch.object(handler, "send_json") as send_json, mock.patch("server.install_tools") as install:
            handler.do_POST()
        self.assertEqual(send_json.call_args.args[1], 403)
        install.assert_not_called()

    def test_main_document_security_policy_blocks_frames_plugins_and_inline_script(self):
        handler = StudioHandler.__new__(StudioHandler)
        with mock.patch.object(handler, "send_header") as send_header:
            handler.security_headers(html=True)
        headers = dict(call.args for call in send_header.call_args_list)
        policy = headers["Content-Security-Policy"]
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertIn("object-src 'none'", policy)
        self.assertNotIn("'unsafe-inline'", policy)

    def test_multipart_upload_is_streamed_to_the_job_directory(self):
        boundary = "----apkcleanertestboundary"
        payload = b"PK\x03\x04" + (b"binary-data\r\n" * 200_000)
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="package"; filename="../../sample.apk"\r\n'
            "Content-Type: application/vnd.android.package-archive\r\n\r\n"
        ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
        handler = StudioHandler.__new__(StudioHandler)
        handler.headers = {
            "Content-Length": str(len(body)),
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }
        handler.rfile = io.BytesIO(body)
        with tempfile.TemporaryDirectory() as name:
            filename, destination, digest = handler.receive_multipart_upload(Path(name))
            self.assertEqual(filename, "sample.apk")
            self.assertEqual(destination.read_bytes(), payload)
            self.assertEqual(digest, hashlib.sha256(payload).hexdigest())

    def test_client_sessions_are_memory_only_and_report_first_last_seen(self):
        with _CLIENTS_LOCK:
            _CLIENTS.clear()
        headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit Chrome/123 Safari/537.36"}
        first = record_client("10.10.30.44", headers, now=1000.0)
        latest = record_client("10.10.30.44", headers, now=1060.0)
        self.assertEqual(len(first), 1)
        self.assertEqual(latest[0]["address"], "10.10.30.44")
        self.assertEqual(latest[0]["description"], "Android · Google Chrome")
        self.assertEqual(latest[0]["first_seen"], 1000.0)
        self.assertEqual(latest[0]["last_seen"], 1060.0)
        self.assertEqual(latest[0]["requests"], 2)
        with _CLIENTS_LOCK:
            _CLIENTS.clear()

    def test_loopback_requests_with_different_ids_are_one_device(self):
        with _CLIENTS_LOCK:
            _CLIENTS.clear()
        first_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/123", "X-Client-ID": "http-client-1234"}
        second_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/123", "X-Client-ID": "https-client-5678"}
        record_client("127.0.0.1", first_headers, now=1000.0)
        rows = record_client("127.0.0.1", second_headers, now=1001.0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["requests"], 2)
        with _CLIENTS_LOCK:
            _CLIENTS.clear()

    def test_model_code_becomes_marketing_name_and_presence_expires(self):
        with _CLIENTS_LOCK:
            _CLIENTS.clear()
        phone_headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) Chrome/123", "X-Client-ID": "phone-client-1234"}
        pc_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/123", "X-Client-ID": "desktop-client-12"}
        record_client("10.10.30.44", phone_headers, now=1000.0, details={"model": "SM-S928B"})
        record_client("10.10.30.45", pc_headers, now=1030.0)
        rows = record_client("127.0.0.1", {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/123"}, now=1030.0)
        phone = next(row for row in rows if row["address"] == "10.10.30.44")
        desktop = next(row for row in rows if row["address"] == "10.10.30.45")
        self.assertEqual(phone["display_name"], "Samsung Galaxy S24 Ultra")
        self.assertEqual(phone["model_name"], "Samsung Galaxy S24 Ultra")
        self.assertFalse(phone["online"])
        self.assertTrue(desktop["online"])
        with _CLIENTS_LOCK:
            _CLIENTS.clear()

    def test_unknown_remote_android_keeps_manual_rename_and_stale_rows_expire(self):
        with _CLIENTS_LOCK:
            _CLIENTS.clear()
            _BLOCKED_CLIENTS.clear()
        phone_headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) Chrome/123", "X-Client-ID": "unnamed-phone-123"}
        phone = record_client("10.10.30.44", phone_headers, now=1000.0)[0]
        self.assertTrue(phone["can_rename"])
        self.assertNotIn("needs_name", phone)
        host_rows = record_client("127.0.0.1", {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/123"}, now=1301.0)
        self.assertNotIn("10.10.30.44", {row["address"] for row in host_rows})
        with _CLIENTS_LOCK:
            _CLIENTS.clear()

    def test_browser_reported_public_ip_replaces_router_address_in_display_only(self):
        with _CLIENTS_LOCK:
            _CLIENTS.clear()
        headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) Chrome/123", "X-Client-ID": "proxy-phone-1234"}
        phone = record_client("10.10.30.1", headers, now=1000.0, details={"public_ip": "1.1.1.1"})[0]
        self.assertEqual(phone["address"], "1.1.1.1")
        self.assertTrue(phone["can_rename"])
        with _CLIENTS_LOCK:
            _CLIENTS[phone["id"]]["hostname"] = "KEENETIC"
        phone = record_client("10.10.30.1", headers, now=1000.5, details={"public_ip": "1.1.1.1"})[0]
        self.assertEqual(phone["display_name"], "Android · cihaz adı alınamadı")
        self.assertNotEqual(phone["display_name"], "KEENETIC")
        phone = record_client("2a09:bac1:72a0:f00::150", headers, now=1001.0, details={"public_ip": "1.0.0.1"})[0]
        self.assertEqual(phone["address"], "1.0.0.1")
        phone = record_client("2a09:bac1:72a0:f00::150", headers, now=1002.0, details={"public_ip": "2a09:bac1:72a0:f00::151"})[0]
        self.assertEqual(phone["address"], "1.0.0.1")
        with _CLIENTS_LOCK:
            _CLIENTS.clear()

    def test_host_can_persistently_block_unblock_and_delete_remote_sessions(self):
        with tempfile.TemporaryDirectory() as name:
            blocklist = Path(name) / "blocked-clients.json"
            with _CLIENTS_LOCK:
                _CLIENTS.clear()
                _BLOCKED_CLIENTS.clear()
            headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) Chrome/123", "X-Client-ID": "managed-phone-123"}
            remote = record_client("10.10.30.44", headers, now=1000.0)[0]
            target_id = remote["id"]
            with mock.patch("server.CLIENT_BLOCKLIST_PATH", blocklist):
                manage_client(target_id, "block", True)
                self.assertIn(target_id, _BLOCKED_CLIENTS)
                self.assertEqual(read_json(blocklist)["clients"][0]["id"], target_id)
                host_rows = record_client("127.0.0.1", {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/123"}, now=1001.0)
                blocked = next(row for row in host_rows if row["id"] == target_id)
                self.assertTrue(blocked["blocked"])
                self.assertFalse(blocked["online"])
                self.assertTrue(blocked["can_manage"])
                request_client_access("10.10.30.44", headers)
                self.assertIn("access_requested_at", _CLIENTS[target_id])
                self.assertIn("access_requested_at", read_json(blocklist)["clients"][0])
                record_blocked_client_details("10.10.30.44", headers, {"model": "SM-G998B", "browser": "Brave"})
                self.assertEqual(_CLIENTS[target_id]["model"], "SM-G998B")
                self.assertEqual(_CLIENTS[target_id]["reported_browser"], "Brave")
                self.assertEqual(read_json(blocklist)["clients"][0]["model"], "SM-G998B")
                manage_client(target_id, "deny", True)
                self.assertNotIn("access_requested_at", _CLIENTS[target_id])
                self.assertIn(target_id, _BLOCKED_CLIENTS)
                with self.assertRaises(PermissionError):
                    manage_client(target_id, "unblock", False)
                manage_client(target_id, "unblock", True)
                self.assertNotIn(target_id, _BLOCKED_CLIENTS)
                manage_client(target_id, "block", True)
                manage_client(target_id, "delete", True)
                self.assertNotIn(target_id, _CLIENTS)
                self.assertNotIn(target_id, _BLOCKED_CLIENTS)
            with _CLIENTS_LOCK:
                _CLIENTS.clear()
                _BLOCKED_CLIENTS.clear()

    def test_remote_devices_see_only_themselves_but_host_sees_every_session(self):
        with _CLIENTS_LOCK:
            _CLIENTS.clear()
        first_headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) Chrome/123", "X-Client-ID": "remote-first-123"}
        second_headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) Chrome/123", "X-Client-ID": "remote-second-12"}
        first_rows = record_client("10.10.30.37", first_headers, now=1000.0)
        second_rows = record_client("10.10.30.38", second_headers, now=1001.0)
        host_rows = record_client("127.0.0.1", {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/123"}, now=1002.0)
        self.assertEqual([row["address"] for row in first_rows], ["10.10.30.37"])
        self.assertEqual([row["address"] for row in second_rows], ["10.10.30.38"])
        self.assertEqual({row["address"] for row in host_rows}, {"10.10.30.37", "10.10.30.38", "127.0.0.1"})
        with _CLIENTS_LOCK:
            _CLIENTS.clear()

    def test_model_client_hint_is_used_when_javascript_cannot_supply_it(self):
        with _CLIENTS_LOCK:
            _CLIENTS.clear()

    def test_index_requests_android_model_as_a_critical_client_hint(self):
        handler = StudioHandler.__new__(StudioHandler)
        handler.headers = {"Host": "127.0.0.1:8080"}
        sent = []
        handler.send_header = lambda name, value: sent.append((name, value))
        handler.cors()
        headers = dict(sent)
        self.assertIn("Sec-CH-UA-Model", headers["Accept-CH"])
        self.assertIn("ch-ua-high-entropy-values=(self)", headers["Permissions-Policy"])
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) Chrome/123",
            "X-Client-ID": "hint-client-12345",
            "Sec-CH-UA-Model": '"SM-S928B"',
        }
        rows = record_client("10.10.30.37", headers, now=1000.0)
        self.assertEqual(rows[0]["display_name"], "Samsung Galaxy S24 Ultra")
        self.assertEqual(rows[0]["model"], "SM-S928B")
        with _CLIENTS_LOCK:
            _CLIENTS.clear()

    def test_block_page_retries_client_hint_and_collects_model_safely(self):
        handler = StudioHandler.__new__(StudioHandler)
        handler.headers = {"Host": "10.10.30.33:8080"}
        handler.wfile = io.BytesIO()
        sent = []
        handler.send_response = lambda status: None
        handler.send_header = lambda name, value: sent.append((name, value))
        handler.end_headers = lambda: None
        handler.send_blocked_page()
        headers = dict(sent)
        body = handler.wfile.getvalue().decode("utf-8")
        self.assertEqual(headers["Critical-CH"], "Sec-CH-UA-Model")
        self.assertIn("Sec-CH-UA-Model", headers["Accept-CH"])
        self.assertIn("/api/client/identify", body)
        self.assertIn('getHighEntropyValues(["model","platform","platformVersion","formFactors"])', body)

    def test_browser_name_distinguishes_brave_edge_and_persists_client_report(self):
        with _CLIENTS_LOCK:
            _CLIENTS.clear()
        edge_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) AppleWebKit Chrome/123 Safari/537.36 Edg/123.0", "X-Client-ID": "edge-client-1234"}
        edge = record_client("10.10.30.20", edge_headers, now=1000.0)[0]
        self.assertEqual(edge["description"], "Windows · Microsoft Edge")
        brave_headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit Chrome/123 Safari/537.36", "X-Client-ID": "brave-client-123"}
        brave = record_client("10.10.30.21", brave_headers, now=1001.0, details={"browser": "Brave"})[0]
        self.assertEqual(brave["description"], "Android · Brave")
        brave = record_client("10.10.30.21", brave_headers, now=1002.0)[0]
        self.assertEqual(brave["description"], "Android · Brave")
        with _CLIENTS_LOCK:
            _CLIENTS.clear()

    def test_hidden_model_message_uses_each_clients_own_browser(self):
        cases = (
            ("brave", "Mozilla/5.0 (Linux; Android 14) AppleWebKit Chrome/123 Safari/537.36", {"browser": "Brave"}, "Brave"),
            ("chrome", "Mozilla/5.0 (Linux; Android 14) AppleWebKit Chrome/123 Safari/537.36", {}, "Google Chrome"),
            ("edge", "Mozilla/5.0 (Linux; Android 14) AppleWebKit Chrome/123 EdgA/123.0", {}, "Microsoft Edge"),
            ("samsung", "Mozilla/5.0 (Linux; Android 14) AppleWebKit Chrome/123 SamsungBrowser/25.0", {}, "Samsung Internet"),
        )
        for index, (key, user_agent, details, expected_browser) in enumerate(cases):
            with self.subTest(browser=key):
                with _CLIENTS_LOCK:
                    _CLIENTS.clear()
                headers = {"User-Agent": user_agent, "X-Client-ID": f"browser-{key}-12345"}
                row = record_client(f"10.10.30.{40 + index}", headers, now=1100.0 + index, details=details)[0]
                self.assertEqual(row["description"], f"Android · {expected_browser}")
                self.assertEqual(row["display_name"], "Android · cihaz adı alınamadı")
        with _CLIENTS_LOCK:
            _CLIENTS.clear()

    def test_history_is_scoped_to_the_requesting_device(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            owner_headers = {"X-Client-ID": "owner-client-123"}
            other_headers = {"X-Client-ID": "other-client-123"}
            owner_id = client_identity("10.0.0.20", owner_headers)
            for job_id, job_owner in (("a" * 32, owner_id), ("b" * 32, client_identity("10.0.0.21", other_headers))):
                job = root / job_id
                job.mkdir()
                (job / "source.apk").write_bytes(b"PK")
                write_json(job / "analysis.json", {"owner_id": job_owner, "filename": f"{job_id[0]}.apk", "source_path": "source.apk", "created_at": 1000})
                write_json(job / "state.json", {"status": "ready"})
            with mock.patch("server.JOBS", root):
                own = list_job_history(owner_id, False)
                local = list_job_history("local", True)
            self.assertEqual([row["job_id"] for row in own], ["a" * 32])
            self.assertEqual(len(local), 2)

    def test_history_delete_is_owner_scoped_and_refuses_active_jobs(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            owner_id = client_identity("10.0.0.20", {"X-Client-ID": "owner-client-123"})
            other_id = client_identity("10.0.0.21", {"X-Client-ID": "other-client-123"})
            done_id, active_id = "c" * 32, "d" * 32
            for job_id, status in ((done_id, "done"), (active_id, "working")):
                job = root / job_id
                job.mkdir()
                write_json(job / "analysis.json", {"owner_id": owner_id})
                write_json(job / "state.json", {"status": status})
            with mock.patch("server.JOBS", root):
                with self.assertRaises(PermissionError):
                    delete_job_history(done_id, other_id, False)
                with self.assertRaises(ValueError):
                    delete_job_history(active_id, owner_id, False)
                delete_job_history(done_id, owner_id, False)
            self.assertFalse((root / done_id).exists())
            self.assertTrue((root / active_id).exists())

    def test_history_reuse_clones_original_source_into_a_fresh_ready_job(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            owner_id = client_identity("10.0.0.20", {"X-Client-ID": "owner-client-123"})
            original_id = "9" * 32
            original = root / original_id
            original.mkdir()
            (original / "sample.apk").write_bytes(b"unchanged-source")
            write_json(original / "analysis.json", {
                "owner_id": owner_id,
                "filename": "sample.apk",
                "source_path": "sample.apk",
                "prepared_path": "sample.apk",
                "approved_message_targets": ["classes.dex:old"],
                "created_at": 1000,
            })
            write_json(original / "state.json", {"status": "done", "result": {"output": "old.apk"}})
            (original / "output").mkdir()
            (original / "output" / "old.apk").write_bytes(b"patched-output")

            with mock.patch("server.JOBS", root):
                reused_id, analysis = clone_job_for_reuse(original_id, owner_id, False)

            self.assertNotEqual(reused_id, original_id)
            reused = root / reused_id
            self.assertEqual((reused / "sample.apk").read_bytes(), b"unchanged-source")
            self.assertTrue((reused / "sample.apk").stat().st_mode & stat.S_IWUSR)
            self.assertFalse((reused / "output").exists())
            self.assertEqual(read_json(reused / "state.json")["status"], "ready")
            self.assertEqual(analysis["prepared_path"], "sample.apk")
            self.assertNotIn("approved_message_targets", analysis)

    def test_clean_job_is_claimed_once_and_retries_return_existing_state(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            job_id = "e" * 32
            job = root / job_id
            job.mkdir()
            write_json(job / "analysis.json", {"filename": "sample.apk"})
            write_json(job / "state.json", {"status": "ready"})
            fake_thread = mock.Mock()
            with _ACTIVE_JOBS_LOCK:
                _ACTIVE_JOBS.clear()
            with mock.patch("server.JOBS", root), mock.patch("server.threading.Thread", return_value=fake_thread) as thread_class:
                first_status, first_result = start_clean_job(job_id, {"operation": "patch"})
                retry_status, retry_result = start_clean_job(job_id, {"operation": "patch"})
                self.assertEqual((first_status, first_result), ("working", None))
                self.assertEqual((retry_status, retry_result), ("working", None))
                self.assertEqual(thread_class.call_count, 1)
                fake_thread.start.assert_called_once()
                self.assertEqual(read_json(job / "state.json")["message"], "İşlem sıraya alındı")
                with _ACTIVE_JOBS_LOCK:
                    _ACTIVE_JOBS.discard(job_id)
                result = {"output": "sample-clean.apk"}
                write_json(job / "state.json", {"status": "done", "result": result})
                done_status, done_result = start_clean_job(job_id, {"operation": "patch"})
                self.assertEqual((done_status, done_result), ("done", result))
                self.assertEqual(thread_class.call_count, 1)
            with _ACTIVE_JOBS_LOCK:
                _ACTIVE_JOBS.clear()

    def test_stale_jobs_are_removed_but_recent_jobs_are_preserved(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            stale = root / ("a" * 32)
            recent = root / ("b" * 32)
            unrelated = root / "keep-me"
            stale.mkdir(); recent.mkdir(); unrelated.mkdir()
            old = time.time() - 3600
            os.utime(stale, (old, old))
            removed = cleanup_stale_jobs(root, max_age_seconds=60)
            self.assertEqual(removed, 1)
            self.assertFalse(stale.exists())
            self.assertTrue(recent.exists())
            self.assertTrue(unrelated.exists())

    def test_active_job_can_be_cancelled_only_by_its_owner(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            job_id = "f" * 32
            owner_id = client_identity("10.0.0.20", {"X-Client-ID": "owner-client-123"})
            other_id = client_identity("10.0.0.21", {"X-Client-ID": "other-client-123"})
            job = root / job_id
            job.mkdir()
            write_json(job / "analysis.json", {"owner_id": owner_id, "filename": "sample.apk"})
            write_json(job / "state.json", {"status": "working", "progress": 37, "filename": "sample.apk"})
            with _ACTIVE_JOBS_LOCK:
                _ACTIVE_JOBS.add(job_id)
                _JOB_CANCEL_EVENTS[job_id] = threading.Event()
                _JOB_THREADS[job_id] = 12345
            try:
                with mock.patch("server.JOBS", root), mock.patch("server.terminate_active_tools") as terminate:
                    with self.assertRaises(PermissionError):
                        cancel_clean_job(job_id, other_id, False)
                    self.assertTrue(cancel_clean_job(job_id, owner_id, False))
                    self.assertTrue(_JOB_CANCEL_EVENTS[job_id].is_set())
                    terminate.assert_called_once_with(12345)
                    self.assertEqual(read_json(job / "state.json")["status"], "cancelling")
            finally:
                with _ACTIVE_JOBS_LOCK:
                    _ACTIVE_JOBS.discard(job_id)
                    _JOB_CANCEL_EVENTS.pop(job_id, None)
                    _JOB_THREADS.pop(job_id, None)

    def test_local_state_is_replaced_atomically_and_corrupt_json_falls_back(self):
        with tempfile.TemporaryDirectory() as name:
            state = Path(name) / "state.json"
            write_json(state, {"status": "working", "progress": 42})
            self.assertEqual(read_json(state)["progress"], 42)
            self.assertFalse(state.with_suffix(".json.tmp").exists())
            state.write_text("{broken", encoding="utf-8")
            self.assertEqual(read_json(state, {"status": "unknown"}), {"status": "unknown"})

    def test_concurrent_state_writers_leave_one_complete_document(self):
        with tempfile.TemporaryDirectory() as name:
            state = Path(name) / "state.json"
            errors = []

            def write(index):
                try:
                    write_json(state, {"writer": index, "payload": "x" * 2048})
                except Exception as exc:  # pragma: no cover - asserted below
                    errors.append(exc)

            with ThreadPoolExecutor(max_workers=12) as pool:
                list(pool.map(write, range(240)))

            self.assertEqual(errors, [])
            final = read_json(state)
            self.assertIn(final["writer"], range(240))
            self.assertEqual(final["payload"], "x" * 2048)
            self.assertEqual(list(Path(name).glob("*.tmp")), [])

    def test_cancelled_browser_download_does_not_escape_as_server_error(self):
        with tempfile.TemporaryDirectory() as name:
            payload = Path(name) / "output.apk"
            payload.write_bytes(b"x" * 4096)
            handler = StudioHandler.__new__(StudioHandler)
            handler.send_response = mock.Mock()
            handler.send_header = mock.Mock()
            handler.cors = mock.Mock()
            handler.end_headers = mock.Mock()
            handler.wfile = mock.Mock()
            handler.wfile.write.side_effect = ConnectionAbortedError(10053, "istemci bağlantıyı kapattı")
            handler.send_file(payload)
            handler.wfile.write.assert_called_once()


if __name__ == "__main__":
    unittest.main()
