"""Completed-output access guards; all fixtures are disposable, not release packages."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'studio'))
import server


class OutputAccessTests(unittest.TestCase):
    def fixture(self, root, status, output='result.apk'):
        job = root / ('a' * 32)
        server.write_json(job / 'analysis.json', {'owner_id': server.client_identity('127.0.0.1', {})})
        server.write_json(job / 'state.json', {'status': status})
        server.write_json(job / 'output/report.json', {'output': output})
        (job / 'output/result.apk').write_bytes(b'fixture-output')
        (job / 'output/report.txt').write_text('Sonuç raporu', encoding='utf-8')
        (job / 'source.apk').write_bytes(b'original-source')
        return job

    def request(self, job, action):
        handler = server.StudioHandler.__new__(server.StudioHandler)
        handler.path = f'/api/jobs/{job.name}/{action}'
        handler.client_address = ('127.0.0.1', 12345)
        handler.headers = {'Host': '127.0.0.1:8080'}
        with mock.patch.object(server, 'JOBS', job.parent), mock.patch.object(handler, 'send_file') as file, mock.patch.object(handler, 'send_json') as response:
            handler.do_GET()
        return file, response

    def test_incomplete_outputs_cannot_be_downloaded_by_direct_or_stale_links(self):
        for status in ('ready', 'working', 'cancelling', 'cancelled', 'error'):
            for action in ('download', 'report'):
                with self.subTest(status=status, action=action), tempfile.TemporaryDirectory() as directory:
                    job = self.fixture(Path(directory), status)
                    file, response = self.request(job, action)
                    file.assert_not_called()
                    self.assertEqual(response.call_args.args[1], 409)
                    self.assertIn('tamamlanmadı', response.call_args.args[0]['error'])
                    self.assertEqual((job / 'source.apk').read_bytes(), b'original-source')
                    self.assertTrue((job / 'output/result.apk').is_file())

    def test_completed_outputs_remain_available(self):
        with tempfile.TemporaryDirectory() as directory:
            job = self.fixture(Path(directory), 'done')
            for action, name in (('download', 'result.apk'), ('report', 'report.txt')):
                file, response = self.request(job, action)
                self.assertEqual(file.call_args.args[0], job / 'output' / name)
                response.assert_not_called()

    def test_invalid_recorded_paths_and_missing_output_never_expose_other_files(self):
        for name in ('../source.apk', 'nested/result.apk', '', None, 123, 'result.exe'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                job = self.fixture(Path(directory), 'done', name)
                file, response = self.request(job, 'download')
                file.assert_not_called()
                self.assertEqual(response.call_args.args[1], 404)

    def test_failed_processing_can_be_retried_without_changing_the_original_source(self):
        class InlineWorker:
            def __init__(self, target, args, **_): self.target, self.args = target, args
            def start(self): self.target(*self.args)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = self.fixture(root, 'ready')
            analysis = server.read_json(job / 'analysis.json')
            analysis.update(source_path='source.apk', prepared_path='source.apk', filename='Source.apk')
            server.write_json(job / 'analysis.json', analysis)
            attempts = []
            def process(_source, output, *_args, **_kwargs):
                attempts.append(True)
                if len(attempts) == 1:
                    (output / 'partial.apk').write_bytes(b'unfinished')
                    server.write_json(output / 'report.json', {'output': 'partial.apk'})
                    raise RuntimeError('Örnek çıktı doğrulanamadı.')
                result = {'output': 'result.apk', 'signed': True}
                (output / 'result.apk').write_bytes(b'completed retry')
                server.write_json(output / 'report.json', result)
                return result
            with mock.patch.object(server, 'JOBS', root), mock.patch.object(server, '_ACTIVE_JOBS', set()), mock.patch.object(server, '_SCANNING_JOBS', set()), mock.patch.object(server, '_JOB_CANCEL_EVENTS', {}), mock.patch.object(server, '_JOB_THREADS', {}), mock.patch.object(server.threading, 'Thread', InlineWorker), mock.patch.object(server, 'process_apk', side_effect=process):
                server.start_clean_job(job.name, {'patch_ads': False})
                self.assertEqual(server.read_json(job / 'state.json')['status'], 'error')
                self.assertNotIn(job.name, server._ACTIVE_JOBS)
                file, response = self.request(job, 'download')
                file.assert_not_called(); self.assertEqual(response.call_args.args[1], 409)
                server.start_clean_job(job.name, {'patch_ads': False})
                self.assertEqual(server.read_json(job / 'state.json')['status'], 'done')
                self.assertNotIn(job.name, server._ACTIVE_JOBS)
                file, response = self.request(job, 'download')
                self.assertEqual(file.call_args.args[0], job / 'output/result.apk')
            self.assertEqual(len(attempts), 2)
            self.assertEqual((job / 'source.apk').read_bytes(), b'original-source')
