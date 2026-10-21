import base64
import hashlib
import io
import os
from pathlib import Path
import sys
import struct
import tempfile
import unittest
from unittest import mock
from xml.etree import ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "studio"))
import windows_vector
import package_icon
from test_package_icon import strings

NS = 'xmlns:android="http://schemas.android.com/apk/res/android"'


def vector(content, attributes=''):
    return ET.fromstring(f'<vector {NS} android:viewportWidth="24" android:viewportHeight="24" {attributes}>{content}</vector>')


class VectorValidationTests(unittest.TestCase):
    def test_binary_float_theme_and_boolean_attributes_are_preserved(self):
        names = ['vector', package_icon.ANDROID_NS, 'viewportWidth', 'viewportHeight', 'tint', 'autoMirrored']
        pool = strings(names)
        attrs = b''.join(struct.pack('<IIIHBBI', 1, key, 0xffffffff, 8, 0, kind, value) for key, kind, value in (
            (2, 4, struct.unpack('<I', struct.pack('<f', 24.5))[0]),
            (3, 4, struct.unpack('<I', struct.pack('<f', 24.5))[0]),
            (4, 2, 0x01010000), (5, 0x12, 1)))
        start = struct.pack('<HHIII', 0x102, 16, 36 + len(attrs), 0, 0xffffffff)
        start += struct.pack('<II6H', 0xffffffff, 0, 20, 20, 4, 0, 0, 0) + attrs
        end = struct.pack('<HHIIIII', 0x103, 16, 24, 0, 0xffffffff, 0xffffffff, 0)
        body = pool + start + end
        tree = package_icon._drawable_xml(struct.pack('<HHI', 3, 8, len(body) + 8) + body)
        self.assertEqual(tree.get(windows_vector.NS + 'viewportWidth'), '24.5')
        self.assertEqual(tree.get(windows_vector.NS + 'tint'), '?0x01010000')
        self.assertEqual(tree.get(windows_vector.NS + 'autoMirrored'), 'true')
        with self.assertRaises(ValueError):
            windows_vector.vector_scene(tree, lambda value: (0, 0, 0, 0))

    def test_supported_scene_colors_transforms_clips_and_curves(self):
        root = vector('<group android:rotation="20.5" android:pivotX="12">'
                      '<clip-path android:pathData="M0,0H24V24H0Z"/>'
                      '<path android:pathData="M2,2 C3,4 5,6 7,8 Q8,9 9,10 A4,4 0 0,1 12,12Z" '
                      'android:fillColor="#fff" android:fillAlpha="0.5" android:strokeWidth="1"/></group>')
        scene = windows_vector.vector_scene(root, lambda value: (255, 255, 255, 255))
        group = scene['children'][0]
        self.assertEqual(group['transform'][4], 20.5)
        self.assertEqual(group['children'][0]['kind'], 'clip-path')
        self.assertEqual(group['children'][1]['fill'], (255, 255, 255, 128))

    def test_unsafe_or_unsupported_features_fail_closed(self):
        for root in (
            vector('<path android:pathData="M0 0LNaN 1"/>'),
            vector('<path android:pathData="M0 0 L1e99 1"/>'),
            vector('<path android:pathData="M0 0 F1 1"/>'),
            vector('<path android:pathData="M0 0"><gradient/></path>'),
            vector('<path android:pathData="M0 0L1 1" android:trimPathEnd="0.5"/>'),
            vector('<image href="https://evil.example"/>'),
            vector('<path android:pathData="M0 0"/>' * 65),
            vector('<group>' * 10 + '</group>' * 10),
            vector('', 'android:tint="?attr/iconColor"'),
        ):
            with self.subTest(root=ET.tostring(root)[:160]), self.assertRaises(ValueError):
                windows_vector.vector_scene(root, lambda value: (0, 0, 0, 0))


@unittest.skipUnless(os.name == 'nt', 'Windows-only WPF renderer')
class VectorRenderingTests(unittest.TestCase):
    def test_compiled_vector_xml_renders_float_viewport_and_color_path(self):
        values = ['vector', package_icon.ANDROID_NS, 'viewportWidth', 'viewportHeight',
                  'path', 'pathData', 'fillColor', 'M4 4H20V20H4Z']
        pool = strings(values)
        def start(name, attributes):
            attrs = b''.join(struct.pack('<IIIHBBI', 1, key, 0xffffffff, 8, 0, kind, value) for key, kind, value in attributes)
            return struct.pack('<HHIII', 0x102, 16, 36 + len(attrs), 0, 0xffffffff) + struct.pack('<II6H', 0xffffffff, name, 20, 20, len(attributes), 0, 0, 0) + attrs
        def end(name):
            return struct.pack('<HHIIIII', 0x103, 16, 24, 0, 0xffffffff, 0xffffffff, name)
        number = struct.unpack('<I', struct.pack('<f', 24))[0]
        body = pool + start(0, [(2, 4, number), (3, 4, number)]) + start(4, [(5, 3, 7), (6, 0x1c, 0xff00ff00)]) + end(4) + end(0)
        data = struct.pack('<HHI', 3, 8, len(body) + 8) + body
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('res/icon.xml', data)
        with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as archive:
            uri = package_icon._archive_icon(archive, 'res/icon.xml')
        from PIL import Image
        with Image.open(io.BytesIO(base64.b64decode(uri.split(',', 1)[1]))) as image:
            self.assertEqual(image.getpixel((128, 128)), (0, 255, 0, 255))

    def test_offscreen_fill_transform_and_group_scoped_clip(self):
        root = vector('<group android:translateX="4"><clip-path android:pathData="M0 0H8V24H0Z"/>'
                      '<path android:pathData="M0 0H24V24H0Z" android:fillColor="#ff0000"/></group>'
                      '<path android:pathData="M18 4H22V20H18Z" android:fillColor="#00ff00"/>')
        image = windows_vector.render_vector(root, lambda value: (255, 0, 0, 255) if value == '#ff0000' else (0, 255, 0, 255), 240)
        self.assertEqual(image.getpixel((60, 120)), (255, 0, 0, 255))
        self.assertEqual(image.getpixel((140, 120))[3], 0)
        self.assertEqual(image.getpixel((200, 120)), (0, 255, 0, 255))

    def test_curve_stroke_alpha_and_even_odd_hole(self):
        root = vector('<path android:pathData="M2 2H22V22H2Z M8 8H16V16H8Z" android:fillType="evenOdd" '
                      'android:fillColor="#fff" android:fillAlpha="0.5"/>'
                      '<path android:pathData="M3 12Q12 2 21 12" android:strokeColor="#fff" '
                      'android:strokeWidth="1" android:strokeLineCap="round"/>')
        image = windows_vector.render_vector(root, lambda value: (255, 255, 255, 255), 240)
        self.assertEqual(image.getpixel((120, 140))[3], 0)
        self.assertTrue(120 <= image.getpixel((40, 180))[3] <= 130)

    def test_vector_apk_and_adaptive_foreground_render_without_modifying_archive(self):
        from PIL import Image
        for adaptive in (False, True):
            with self.subTest(adaptive=adaptive), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'vector.apk'
                drawing = ET.tostring(vector('<path android:pathData="M4 4H20V20H4Z" android:fillColor="#00ff00"/>'))
                with zipfile.ZipFile(path, 'w') as archive:
                    archive.writestr('AndroidManifest.xml', f'<manifest {NS}><application android:icon="res/drawable/icon.xml"/></manifest>')
                    archive.writestr('res/drawable/vector.xml', drawing)
                    archive.writestr('res/drawable/icon.xml', f'<adaptive-icon {NS}><background android:drawable="#ff0000"/>'
                                     '<foreground android:drawable="res/drawable/vector.xml"/></adaptive-icon>' if adaptive else drawing)
                before = hashlib.sha256(path.read_bytes()).digest()
                with zipfile.ZipFile(path) as archive:
                    uri = package_icon._archive_icon(archive, 'res/drawable/icon.xml')
                self.assertTrue(uri.startswith('data:image/png;base64,'))
                with Image.open(io.BytesIO(base64.b64decode(uri.split(',', 1)[1]))) as image:
                    self.assertEqual(image.size, (256, 256))
                    self.assertEqual(image.getpixel((128, 128)), (0, 255, 0, 255))
                self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), before)

    def test_busy_renderer_does_not_queue_more_threads(self):
        with mock.patch.object(windows_vector, '_WORKER') as gate:
            gate.acquire.return_value = False
            with self.assertRaises(ValueError):
                windows_vector.render_vector(vector(''), lambda value: (0, 0, 0, 0))
            gate.release.assert_not_called()


if __name__ == '__main__':
    unittest.main()
