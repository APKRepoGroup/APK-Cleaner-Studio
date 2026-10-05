"""Best-effort, bounded launcher-icon previews; never modify or decode the APK.

Only the manifest's icon resource is followed, not filenames guessed from res/.
Android renders adaptive/vector drawables natively; elsewhere raster variants
are used. Missing, unsupported or malformed icons are optional metadata.
Binary layout reference: AOSP androidfw/ResourceTypes.h.
"""
from __future__ import annotations

import base64
import os
import re
import struct
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

MAX_ICON_BYTES = 512 * 1024
MAX_RESOURCE_BYTES = 32 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_ICON_DIMENSION = 2048
ANDROID_NS = "http://schemas.android.com/apk/res/android"


def _u16(data, offset):
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def _chunks(data, start, end):
    count = 0
    while start < end:
        kind, header, size = struct.unpack_from("<HHI", data, start)
        if header < 8 or size < header or start + size > end or count >= 100_000:
            raise ValueError("Invalid resource chunk")
        yield kind, start, header, size
        start += size
        count += 1


class _Strings:
    def __init__(self, data, offset, header, size):
        self.data, self.offset, self.end = data, offset, offset + size
        self.count = _u32(data, offset + 8)
        self.utf8 = bool(_u32(data, offset + 16) & 0x100)
        self.indices = offset + header
        self.start = offset + _u32(data, offset + 20)
        if header < 28 or self.indices + self.count * 4 > self.start or self.start > self.end:
            raise ValueError("Invalid string pool")

    def get(self, index):
        if index >= self.count:
            raise ValueError("Invalid string index")
        cursor = self.start + _u32(self.data, self.indices + index * 4)

        def length():
            nonlocal cursor
            width, flag = (1, 0x80) if self.utf8 else (2, 0x8000)
            if cursor + width > self.end:
                raise ValueError("Invalid string length")
            value = self.data[cursor] if width == 1 else _u16(self.data, cursor)
            cursor += width
            if value & flag:
                if cursor + width > self.end:
                    raise ValueError("Invalid string length")
                tail = self.data[cursor] if width == 1 else _u16(self.data, cursor)
                cursor += width
                value = ((value & (flag - 1)) << (8 if width == 1 else 16)) | tail
            return value

        size = length()
        if self.utf8:
            size = length()
        else:
            size *= 2
        if cursor + size > self.end or size > 8192:
            raise ValueError("Invalid resource string")
        return self.data[cursor:cursor + size].decode("utf-8" if self.utf8 else "utf-16le")


def _manifest_icon(data):
    if data.lstrip().startswith(b"<"):
        app = ET.fromstring(data).find("application")
        if app is None:
            return ""
        value = app.get(f"{{{ANDROID_NS}}}icon", "")
        return int(value[1:], 16) if value.startswith("@0x") else value
    strings = None
    for kind, offset, header, size in _chunks(data, 8, len(data)):
        if kind == 1:
            strings = _Strings(data, offset, header, size)
        elif kind == 0x102 and strings:
            ext = offset + header
            if ext + 20 > offset + size or strings.get(_u32(data, ext + 4)) != "application":
                continue
            start, stride, count = struct.unpack_from("<HHH", data, ext + 8)
            if start < 20 or stride < 20 or ext + start + count * stride > offset + size:
                raise ValueError("Invalid application attributes")
            for i in range(count):
                attr = ext + start + i * stride
                namespace = _u32(data, attr)
                if namespace == 0xffffffff or strings.get(namespace) != ANDROID_NS:
                    continue
                if strings.get(_u32(data, attr + 4)) == "icon":
                    value = _u32(data, attr + 16)
                    return value if data[attr + 15] == 1 else strings.get(value) if data[attr + 15] == 3 else ""
            return ""
    return ""


def read_manifest_identity(data: bytes) -> dict:
    """Read optional presentation metadata without starting Java or modifying APKs.

    Resource references are deliberately not guessed. Long version codes travel
    as decimal strings so JavaScript cannot round their 64-bit value.
    """
    unknown = {"package_name": None, "version_code": None}
    try:
        if not data or len(data) > MAX_MANIFEST_BYTES:
            return unknown
        values = {}
        if data.lstrip().startswith(b"<"):
            root = ET.fromstring(data)
            if root.tag != "manifest":
                return unknown
            values["package"] = root.get("package")
            for key in ("versionCode", "versionCodeMajor"):
                value = root.get(f"{{{ANDROID_NS}}}{key}")
                if value is not None:
                    values[key] = value
        else:
            kind, header, size = struct.unpack_from("<HHI", data)
            if kind != 3 or header != 8 or size != len(data):
                return unknown
            strings = None
            for kind, offset, header, size in _chunks(data, 8, len(data)):
                if kind == 1:
                    strings = _Strings(data, offset, header, size)
                elif kind == 0x102 and strings:
                    ext, end = offset + header, offset + size
                    if ext + 20 > end or strings.get(_u32(data, ext + 4)) != "manifest":
                        return unknown
                    start, stride, count = struct.unpack_from("<HHH", data, ext + 8)
                    if start < 20 or stride < 20 or ext + start + count * stride > end:
                        return unknown
                    for i in range(count):
                        attr = ext + start + i * stride
                        namespace, key = _u32(data, attr), strings.get(_u32(data, attr + 4))
                        if not (key == "package" and namespace == 0xffffffff or
                                key in {"versionCode", "versionCodeMajor"} and namespace != 0xffffffff and strings.get(namespace) == ANDROID_NS):
                            continue
                        if _u16(data, attr + 12) != 8:
                            return unknown
                        value_type, value = data[attr + 15], _u32(data, attr + 16)
                        values[key] = strings.get(value) if value_type == 3 else value if value_type in {0x10, 0x11} else None
                    break
        package = values.get("package")
        if not isinstance(package, str) or len(package) > 512 or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+", package):
            package = None

        def number(value, maximum):
            if isinstance(value, int):
                return value if 0 <= value <= maximum else None
            if isinstance(value, str) and re.fullmatch(r"(?:\d{1,10}|0[xX][0-9a-fA-F]{1,8})", value, re.ASCII):
                parsed = int(value, 16 if value.lower().startswith("0x") else 10)
                return parsed if parsed <= maximum else None
            return None

        low = number(values.get("versionCode"), 0xffffffff)
        major = number(values.get("versionCodeMajor", 0), 0x7fffffff)
        code = str((major << 32) | low) if low is not None and major is not None else None
        return {"package_name": package, "version_code": code}
    except (ValueError, TypeError, IndexError, struct.error, UnicodeError, ET.ParseError):
        return unknown


def _entry_value(data, offset, header, size, index):
    end = offset + size
    flags, count, start = data[offset + 9], _u32(data, offset + 12), _u32(data, offset + 16)
    if header < 24 or count > 65536 or start < header or start > size:
        raise ValueError("Invalid resource type")
    indices = offset + header
    width = 2 if flags & 2 else 4
    if indices + count * width > offset + start:
        raise ValueError("Invalid resource offsets")
    if flags & 1:
        relative = None
        for i in range(count):
            key, value = struct.unpack_from("<HH", data, indices + i * 4)
            if key == index:
                relative = value * 4
                break
    elif index >= count:
        relative = None
    elif flags & 2:
        value = _u16(data, indices + index * 2)
        relative = None if value == 0xffff else value * 4
    else:
        value = _u32(data, indices + index * 4)
        relative = None if value == 0xffffffff else value
    if relative is None:
        return None
    entry = offset + start + relative
    if entry + 8 > end:
        raise ValueError("Invalid resource entry")
    entry_size, entry_flags = struct.unpack_from("<HH", data, entry)
    if entry_flags & 1:
        return None
    if entry_flags & 8:
        return entry_flags >> 8, _u32(data, entry + 4)
    if entry_size < 8 or entry + entry_size + 8 > end:
        raise ValueError("Invalid resource value")
    value = entry + entry_size
    return data[value + 3], _u32(data, value + 4)


def _resource_paths(data, resource_id):
    strings, packages = None, []
    for kind, offset, header, size in _chunks(data, 12, len(data)):
        if kind == 1:
            strings = _Strings(data, offset, header, size)
        elif kind == 0x200 and header >= 284:
            packages.append((offset, header, size))
    if not strings:
        return []
    pending, visited, paths = [resource_id], set(), []
    while pending and len(visited) < 12:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        for package, package_header, package_size in packages:
            if _u32(data, package + 8) != current >> 24:
                continue
            type_offset = _u32(data, package + 284) if package_header >= 288 else 0
            for kind, offset, header, size in _chunks(data, package + package_header, package + package_size):
                if kind != 0x201 or data[offset + 8] + type_offset != (current >> 16) & 0xff:
                    continue
                value = _entry_value(data, offset, header, size, current & 0xffff)
                if value and value[0] == 3:
                    paths.append(strings.get(value[1]))
                elif value and value[0] == 1:
                    pending.append(value[1])
    return list(dict.fromkeys(paths))[:32]


def _read(archive, name, limit):
    entry = archive.getinfo(name)
    if entry.file_size > limit or entry.compress_size and entry.file_size / entry.compress_size > 500:
        raise ValueError("Icon metadata exceeds limit")
    return archive.read(entry)


def _raster_uri(data):
    # Only passive raster formats, never arbitrary XML/HTML/SVG from the APK.
    if len(data) < 24 or len(data) > MAX_ICON_BYTES:
        return ""
    mime, width, height = "", 0, 0
    if data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR":
        mime = "png"
        width, height = struct.unpack_from(">II", data, 16)
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        mime = "webp"
        if data[12:16] == b"VP8X" and len(data) >= 30:
            width = 1 + int.from_bytes(data[24:27], "little")
            height = 1 + int.from_bytes(data[27:30], "little")
        elif data[12:16] == b"VP8L" and len(data) >= 25 and data[20] == 0x2f:
            bits = _u32(data, 21)
            width, height = (bits & 0x3fff) + 1, ((bits >> 14) & 0x3fff) + 1
        elif data[12:16] == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
            width, height = _u16(data, 26) & 0x3fff, _u16(data, 28) & 0x3fff
    elif data.startswith(b"\xff\xd8"):
        mime, cursor = "jpeg", 2
        while cursor + 4 < len(data):
            if data[cursor] != 0xff:
                break
            marker = data[cursor + 1]
            if marker == 0xff:
                cursor += 1
                continue
            size = int.from_bytes(data[cursor + 2:cursor + 4], "big")
            if size < 2 or cursor + 2 + size > len(data):
                break
            if marker in {0xc0, 0xc1, 0xc2} and size >= 7:
                height, width = struct.unpack_from(">HH", data, cursor + 5)
                break
            cursor += size + 2
    if not mime:
        return ""
    if not 0 < width <= MAX_ICON_DIMENSION or not 0 < height <= MAX_ICON_DIMENSION:
        return ""
    return f"data:image/{mime};base64," + base64.b64encode(data).decode("ascii")


def _archive_icon(archive, reference):
    paths = _resource_paths(_read(archive, "resources.arsc", MAX_RESOURCE_BYTES), reference) if isinstance(reference, int) else [reference]
    # Density-independent adaptive XML is skipped in favor of the same icon's
    # legacy PNG variant. Never choose unrelated res/ images by their names.
    for path in reversed(paths):
        if not path.startswith("res/") or not path.lower().endswith((".png", ".webp", ".jpg", ".jpeg")):
            continue
        try:
            icon = _raster_uri(_read(archive, path, MAX_ICON_BYTES))
            if icon:
                return icon
        except (KeyError, ValueError, zipfile.BadZipFile):
            continue
    return ""


def extract_apk_icon(path: Path) -> str:
    try:
        if os.environ.get("APK_CLEANER_ANDROID") == "1":
            try:
                from java import jclass
                icon = str(jclass("com.apkcleaner.studio.EmbeddedToolRunner").inspectArchiveIcon(str(path)) or "")
                if icon.startswith("data:image/png;base64,") and len(icon) <= MAX_ICON_BYTES * 4 // 3 + 32:
                    payload = base64.b64decode(icon.split(",", 1)[1], validate=True)
                    native_icon = _raster_uri(payload)
                    if native_icon:
                        return native_icon
            except Exception:
                pass
        with zipfile.ZipFile(path) as archive:
            reference = _manifest_icon(_read(archive, "AndroidManifest.xml", MAX_MANIFEST_BYTES))
            return _archive_icon(archive, reference) if reference else ""
    except Exception:
        # Cosmetic metadata must not turn a valid analysis into a failed job.
        return ""


def extract_split_icon(source: Path, inventory: dict) -> str:
    try:
        modules = inventory.get("modules", [])
        base = next((item["name"] for item in modules if item.get("kind") == "base"), None)
        if not base:
            return ""
        with zipfile.ZipFile(source) as outer:
            if outer.getinfo(base).file_size > 64 * 1024 * 1024:
                return ""
            with outer.open(base) as stream, zipfile.ZipFile(stream) as archive:
                reference = _manifest_icon(_read(archive, "AndroidManifest.xml", MAX_MANIFEST_BYTES))
                if not reference:
                    return ""
            densities = [item["name"] for item in modules if item.get("kind") == "density"][:8]
            for name in [base, *reversed(densities)]:
                if outer.getinfo(name).file_size > 64 * 1024 * 1024:
                    continue
                try:
                    with outer.open(name) as stream, zipfile.ZipFile(stream) as archive:
                        icon = _archive_icon(archive, reference)
                        if icon:
                            return icon
                except Exception:
                    continue
    except Exception:
        pass
    return ""
