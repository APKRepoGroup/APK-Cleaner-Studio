import re
import struct
import unittest
from html.parser import HTMLParser
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "studio/web"
SMALL_SIZES = (16, 20, 24, 32)


class FaviconLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.icons = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "link" and attrs.get("rel") == "icon":
            self.icons[attrs["href"].split("?", 1)[0]] = attrs.get("sizes")


class BrandIconsTests(unittest.TestCase):
    def test_header_frames_share_the_old_theme_aware_outline_without_resizing(self):
        for path, selector in ((WEB / "theme.css", ".brand > span"),
                               (ROOT / "app/theme.css", ".brand-mark")):
            with self.subTest(path=path):
                css = path.read_text(encoding="utf-8")
                rule = re.search(rf"^{re.escape(selector)} \{{([^}}]+)\}}", css, re.MULTILINE)
                self.assertIsNotNone(rule)
                self.assertIn("width: 42px;", rule[1])
                self.assertIn("height: 42px;", rule[1])
                self.assertIn("border-radius: 12px;", rule[1])
                self.assertIn("inset 0 0 0 1px var(--brand-frame-edge, color-mix(in srgb, var(--green) 45%, #0d1515))", rule[1])
                self.assertNotRegex(rule[1], r"\b(?:padding|border):")
                dark_palette = re.search(r'^html\[data-theme="dark"\] \{([^}]+--brand-frame-edge:[^}]+)\}', css, re.MULTILINE)
                self.assertIsNotNone(dark_palette)
                self.assertIn("--brand-frame-edge: #34443f;", dark_palette[1])
                self.assertIn("--brand-frame-fill: #070c0b;", dark_palette[1])

    def test_header_icon_dimensions_do_not_depend_on_theme(self):
        studio_css = (WEB / "theme.css").read_text(encoding="utf-8")
        landing_css = (ROOT / "app/theme.css").read_text(encoding="utf-8")
        self.assertNotRegex(studio_css, r'\[data-theme[^\]]*\][^\n{]*\.brand\s*>\s*span')
        self.assertNotRegex(landing_css, r'\[data-theme[^\]]*\][^\n{]*\.brand-mark')
        self.assertRegex(studio_css, r'@media \(max-width: 620px\) \{\s*\.topbar[^\n]*\n\s*\.brand > span \{ width: 38px; height: 38px; \}')

    def test_web_copies_and_size_specific_links(self):
        document = FaviconLinks()
        document.feed((WEB / "index.html").read_text(encoding="utf-8"))
        for size in SMALL_SIZES:
            with self.subTest(size=size):
                name = f"favicon-{size}.svg"
                self.assertEqual(document.icons[f"/{name}"], f"{size}x{size}")
                svg = ET.parse(WEB / name).getroot()
                self.assertEqual(svg.get("viewBox"), f"0 0 {size} {size}")
        for name in ("favicon.ico", "favicon.png", "favicon.svg", *(f"favicon-{size}.svg" for size in SMALL_SIZES)):
            self.assertEqual((WEB / name).read_bytes(), (ROOT / "public" / name).read_bytes())

    def test_windows_ico_carries_distinct_native_frames(self):
        ico = (ROOT / "public/favicon.ico").read_bytes()
        self.assertEqual(struct.unpack_from("<HHH", ico), (0, 1, 8))
        sizes = []
        for entry in range(8):
            width, height, _, _, _, depth, length, offset = struct.unpack_from("<BBBBHHII", ico, 6 + entry * 16)
            self.assertEqual(width, height)
            self.assertEqual(depth, 32)
            self.assertLessEqual(offset + length, len(ico))
            self.assertEqual(ico[offset:offset + 8], b"\x89PNG\r\n\x1a\n")
            size = width or 256
            self.assertEqual(struct.unpack_from(">II", ico, offset + 16), (size, size))
            sizes.append(size)
        self.assertEqual(sizes, [16, 20, 24, 32, 48, 64, 128, 256])
