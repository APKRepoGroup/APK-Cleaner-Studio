import unittest
import re
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


class AndroidStringDefaultsTests(unittest.TestCase):
    def test_turkish_strings_have_one_default_source(self):
        resources = ROOT / "android/app/src/main/res"
        self.assertFalse((resources / "values-tr/strings.xml").exists())
        strings = {node.get("name"): node.text for node in ET.parse(resources / "values/strings.xml").getroot()}
        self.assertEqual(len(strings), 26)
        self.assertEqual(strings["engine_stop"], "Durdur")
        self.assertEqual(strings["save_failed"], "Çıktı kaydedilemedi.")
        self.assertEqual(strings["splash_tagline"], "Yerel Android paket stüdyosu")
        for source in (ROOT / "android/app/src/main/java").rglob("*.java"):
            for name in re.findall(r"(?<!android\.)R\.string\.(\w+)", source.read_text(encoding="utf-8")):
                self.assertIn(name, strings, source.name)
