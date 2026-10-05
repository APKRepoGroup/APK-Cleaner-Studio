import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'studio'))
from server import JobProgressJournal, _execute_clean_job, read_json, write_json


class ProgressJournalTests(unittest.TestCase):
    def test_bounded_ordered_events_and_elapsed_time(self):
        with mock.patch('server.time.monotonic', return_value=100):
            journal = JobProgressJournal()
        with mock.patch('server.time.monotonic', return_value=102.5):
            for i in range(150):
                journal.record(f'DEX {i} işlendi', i)
        self.assertEqual(len(journal.events), 120)
        self.assertEqual(journal.events[0]['id'], 31)
        self.assertEqual(journal.events[-1]['elapsed_seconds'], 2.5)
        self.assertEqual(journal.events[-1]['progress'], 100)
        journal.record('DEX 149 işlendi', 149)
        self.assertEqual(journal.sequence, 150)
        self.assertLessEqual(len(journal.record('x' * 1000, -3)[-1]['message']), 500)

    def test_each_job_starts_a_new_journal(self):
        first, second = JobProgressJournal(), JobProgressJournal()
        first.record('Önceki işlem', 50)
        self.assertEqual(second.record('Yeni işlem', 4)[0]['id'], 1)

    def run_job(self, processor):
        with tempfile.TemporaryDirectory() as directory, mock.patch('server.JOBS', Path(directory)):
            job_id = 'a' * 32
            job = Path(directory) / job_id
            job.mkdir()
            (job / 'source.apk').write_bytes(b'fixture')
            write_json(job / 'analysis.json', {'filename': 'source.apk', 'prepared_path': 'source.apk'})
            with mock.patch('server.process_apk', side_effect=processor):
                _execute_clean_job(job_id, {'operation': 'patch'})
            return read_json(job / 'state.json')

    def test_finished_state_preserves_steps_that_finish_between_polls(self):
        def process(source, output, mode, progress, **kwargs):
            progress('DEX hazırlanıyor', 12)
            progress('classes.dex işlendi (1/2) · 4 reklam yaması', 38)
            progress('classes2.dex işlendi (2/2) · Değişiklik gerekmedi', 57)
            return {'signed': True}
        state = self.run_job(process)
        self.assertEqual(state['status'], 'done')
        self.assertEqual(len(state['events']), 5)
        self.assertIn('4 reklam yaması', state['events'][2]['message'])
        self.assertEqual(state['events'][-1]['message'], 'Çıktı APK hazır')

    def test_error_keeps_prior_steps_and_never_invents_success(self):
        def process(source, output, mode, progress, **kwargs):
            progress('APK imzalanıyor', 92)
            raise RuntimeError('No space left on device')
        state = self.run_job(process)
        self.assertEqual(state['status'], 'error')
        self.assertEqual(state['events'][-2]['message'], 'APK imzalanıyor')
        self.assertNotIn('Çıktı APK hazır', [event['message'] for event in state['events']])
        self.assertNotIn('No space left', state['events'][-1]['message'])


if __name__ == '__main__':
    unittest.main()
