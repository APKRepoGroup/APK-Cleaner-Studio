import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'studio'))
import server


class ProcessingSelectionTests(unittest.TestCase):
    def make_job(self, root):
        job = root / ('a' * 32)
        server.write_json(job / 'analysis.json', {'filename': 'Source.apk'})
        server.write_json(job / 'state.json', {'status': 'ready'})
        return job

    def test_exact_worker_selection_is_saved_privately_without_unrelated_request_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = self.make_job(root)
            payload = {'operation': 'clone', 'profile': 'deep', 'clone_package_name': 'com.example.clone',
                       'patch_ads': True, 'restrict_store_updates': True, 'strip_debug': True,
                       'split_selection': {'abis': ['arm64-v8a'], 'languages': ['tr']}, 'message_targets': ['call-1'],
                       'app_appearance': {'name': 'Selected name'}, 'owner_id': 'not-a-setting', 'unknown': 'ignored'}
            with mock.patch.object(server, 'JOBS', root), mock.patch.object(server, '_ACTIVE_JOBS', set()), mock.patch.object(server, '_SCANNING_JOBS', set()), mock.patch.object(server, '_JOB_CANCEL_EVENTS', {}), mock.patch.object(server.threading, 'Thread') as worker:
                self.assertEqual(server.start_clean_job(job.name, payload)[0], 'working')
                saved = server.read_json(job / 'selection.json')
                self.assertEqual(saved, worker.call_args.kwargs['args'][1])
                self.assertEqual(saved['profile'], 'deep')
                self.assertEqual(saved['split_selection'], payload['split_selection'])
                self.assertEqual(saved['app_appearance']['name'], 'Selected name')
                self.assertNotIn('owner_id', saved)
                self.assertNotIn('unknown', saved)
                # A repeated request must neither relaunch nor overwrite the real settings.
                server.start_clean_job(job.name, {'profile': 'safe'})
                self.assertEqual(server.read_json(job / 'selection.json'), saved)
                self.assertEqual(worker.call_count, 1)

    def test_invalid_or_oversized_configuration_never_claims_or_starts_work(self):
        for payload in ({'profile': 'other'}, {'patch_ads': 'true'}, {'split_selection': {'abis': 'arm64'}},
                        {'message_targets': ['x'] * 1001}, {'app_appearance': {'name': 'x' * 81}}):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                job = self.make_job(root)
                with mock.patch.object(server, 'JOBS', root), mock.patch.object(server, '_ACTIVE_JOBS', set()), mock.patch.object(server, '_SCANNING_JOBS', set()), mock.patch.object(server.threading, 'Thread') as worker:
                    with self.assertRaises(ValueError):
                        server.start_clean_job(job.name, payload)
                    self.assertEqual(server._ACTIVE_JOBS, set())
                    worker.assert_not_called()
                self.assertEqual(server.read_json(job / 'state.json')['status'], 'ready')

    def test_default_split_selection_is_materialized_in_the_worker_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = self.make_job(root)
            server.write_json(job / 'analysis.json', {'filename': 'Source.apks', 'split_merged': True,
                'split_options': {'abis': ['arm64-v8a', 'armeabi-v7a'], 'languages': [{'code': 'tr'}, {'code': 'en'}]}})
            with mock.patch.object(server, 'JOBS', root), mock.patch.object(server, '_ACTIVE_JOBS', set()), mock.patch.object(server, '_SCANNING_JOBS', set()), mock.patch.object(server, '_JOB_CANCEL_EVENTS', {}), mock.patch.object(server.threading, 'Thread'):
                server.start_clean_job(job.name, {'operation': 'convert'})
            self.assertEqual(server.read_json(job / 'selection.json')['split_selection'], {'abis': ['arm64-v8a', 'armeabi-v7a'], 'languages': ['tr', 'en']})

    def test_session_returns_saved_selection_read_only_after_owner_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = self.make_job(root)
            selected = server.processing_selection({'profile': 'deep'})
            server.write_json(job / 'selection.json', selected)
            handler = server.StudioHandler.__new__(server.StudioHandler)
            handler.path = f'/api/jobs/{job.name}/session'
            handler.client_address = ('127.0.0.1', 12345)
            handler.headers = {'Host': '127.0.0.1:8080'}
            server.write_json(job / 'analysis.json', {'filename': 'Source.apk', 'owner_id': server.client_identity(handler.client_address[0], handler.headers)})
            before = (job / 'selection.json').read_bytes()
            with mock.patch.object(server, 'JOBS', root), mock.patch.object(handler, 'send_json') as send:
                handler.do_GET()
            self.assertEqual(send.call_args.args[0]['selection'], selected)
            self.assertEqual((job / 'selection.json').read_bytes(), before)
