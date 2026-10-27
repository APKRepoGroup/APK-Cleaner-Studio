import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "studio"))
from processing_profiles import export_profile_document
import server


def document(profiles=None):
    return {"format": "apk-cleaner-processing-profiles", "version": 1,
            "profiles": profiles if profiles is not None else [{"name": "Dengeli", "options": {"operation": "patch", "profile": "balanced", "patchAds": True}}]}


class ProcessingProfilesTests(unittest.TestCase):
    def test_clean_document_roundtrips_without_job_or_identity(self):
        result = json.loads(export_profile_document(json.dumps(document())))
        self.assertEqual(result["profiles"][0]["options"]["patchAds"], True)
        self.assertEqual(result["profiles"][0]["options"]["restrictStoreUpdates"], False)
        self.assertEqual(set(result), {"format", "version", "profiles"})

    def test_rejects_unknown_fields_types_versions_and_unbounded_documents(self):
        invalid = [[], {}, document([]), {**document(), "version": True}, {**document(), "version": 2}, {**document(), "apk": "secret"},
                   document([{"name": "A", "options": {"operation": "patch", "profile": "balanced", "patchAds": "false"}}]),
                   document([{"name": "A", "options": {"operation": "clone", "profile": "safe", "clone_package_name": "private"}}]),
                   document([{"name": "A\nB", "options": {"operation": "patch", "profile": "safe"}}])]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                export_profile_document(json.dumps(value))
        with self.assertRaises(ValueError):
            export_profile_document(" " * 16385)

    def test_export_http_endpoint_downloads_a_fixed_named_no_store_json(self):
        handler = server.StudioHandler.__new__(server.StudioHandler)
        handler.path = "/api/profiles/export?profiles=" + quote(json.dumps(document()))
        handler.client_address = ("127.0.0.1", 12345)
        handler.headers = {"Host": "127.0.0.1:8080"}
        handler.request_origin_allowed = Mock(return_value=True)
        handler.requester_is_blocked = Mock(return_value=False)
        handler.redirect_secure_http = Mock(return_value=False)
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.security_headers = Mock()
        handler.cors = Mock()
        handler.end_headers = Mock()
        handler.wfile = io.BytesIO()
        handler.do_GET()
        handler.send_response.assert_called_once_with(200)
        handler.send_header.assert_any_call("Cache-Control", "no-store")
        handler.send_header.assert_any_call("Content-Disposition", 'attachment; filename="APK-Cleaner-Studio-islem-profilleri.json"')
        self.assertEqual(json.loads(handler.wfile.getvalue())["profiles"][0]["name"], "Dengeli")


if __name__ == "__main__":
    unittest.main()
