import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class NativeErrorLanguageTests(unittest.TestCase):
    def test_real_java_error_messages_do_not_expose_english_exceptions(self):
        java, javac = shutil.which("java"), shutil.which("javac")
        if not java or not javac:
            self.skipTest("JDK unavailable")
        with tempfile.TemporaryDirectory() as name:
            subprocess.run([javac, "-encoding", "UTF-8", "-d", name,
                str(ROOT / "android/app/src/main/java/com/apkcleaner/studio/UserErrorMessages.java"),
                str(ROOT / "tests/UserErrorMessagesFixture.java")], check=True, capture_output=True)
            for raw, expected in (("Permission denied", "erişim izni"), ("Connection refused", "Bağlantı"),
                                  ("No space left on device", "depolama alanı"), ("unknown vendor issue", "İşlem tamamlanamadı"),
                                  ("Paket imzası karşılaştırılamadı.", "Paket imzası karşılaştırılamadı")):
                result = subprocess.run([java, "-Dfile.encoding=UTF-8", "-cp", name,
                        "com.apkcleaner.studio.UserErrorMessagesFixture", raw],
                        check=True, capture_output=True, text=True, encoding="utf-8")
                self.assertIn(expected, result.stdout)
