"""Bounded malformed-package checks; no large allocation or release build."""
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'studio'))
import engine
import server


class InputResilienceTests(unittest.TestCase):
    def test_corrupt_and_incomplete_archives_fail_in_turkish_without_modifying_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = []
            raw = root / 'raw.apk'; raw.write_bytes(b'not an archive'); cases.append((raw, engine.inspect_apk))
            truncated = root / 'truncated.apk'
            with zipfile.ZipFile(truncated, 'w') as archive:
                archive.writestr('classes.dex', b'dex fixture')
            truncated.write_bytes(truncated.read_bytes()[:-16]); cases.append((truncated, engine.inspect_apk))
            missing_dex = root / 'missing-dex.apk'
            with zipfile.ZipFile(missing_dex, 'w') as archive:
                archive.writestr('AndroidManifest.xml', b'<manifest/>')
            cases.append((missing_dex, engine.inspect_apk))
            for name, contents in (('empty.apks', None), ('broken-base.apks', b'bad apk')):
                split = root / name
                with zipfile.ZipFile(split, 'w') as archive:
                    if contents is not None:
                        archive.writestr('base.apk', contents)
                cases.append((split, engine.inspect_split_package))
            for source, inspect in cases:
                with self.subTest(source=source.name):
                    before = source.read_bytes()
                    with self.assertRaises((ValueError, RuntimeError, zipfile.BadZipFile)) as raised:
                        inspect(source)
                    message = server.public_error(raised.exception)
                    self.assertTrue(any(word in message.lower() for word in ('paket', 'apk', 'split', 'arşiv')))
                    self.assertNotIn('There is no item', message)
                    self.assertEqual(source.read_bytes(), before)

    def test_huge_archive_metadata_is_rejected_without_extracting_or_allocating_it(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'large.apk'
            with zipfile.ZipFile(source, 'w') as archive:
                archive.writestr('classes.dex', b'small fixture')
            def entry(name, size):
                item = zipfile.ZipInfo(name); item.file_size = size; item.compress_size = size
                return item
            cases = [([entry('classes.dex', engine.MAX_ARCHIVE_ENTRY_BYTES + 1)], 'tek dosya'),
                     ([entry(f'classes{i}.dex', 1024 ** 3) for i in range(4)], 'boyut sınırını')]
            for entries, expected in cases:
                with self.subTest(expected=expected), mock.patch.object(engine.zipfile, 'ZipFile') as archive:
                    archive.return_value.__enter__.return_value.infolist.return_value = entries
                    with self.assertRaisesRegex(ValueError, expected):
                        engine.validate_package_archive(source)
                    archive.return_value.__enter__.return_value.extractall.assert_not_called()

    def test_oversized_upload_is_rejected_before_reading_any_body_bytes(self):
        handler = server.StudioHandler.__new__(server.StudioHandler)
        handler.headers = {'Content-Length': str(server.MAX_UPLOAD + 1)}
        handler.rfile = mock.Mock(spec=io.BytesIO)
        with self.assertRaisesRegex(ValueError, '1 GB'):
            handler.receive_multipart_upload(Path('unused-job'))
        handler.rfile.read.assert_not_called(); handler.rfile.readline.assert_not_called()
