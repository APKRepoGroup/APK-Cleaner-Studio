"""Bounded, read-only package metadata. Signature presence is not verification."""
from __future__ import annotations

import struct
import zipfile
from xml.etree import ElementTree as ET
from package_icon import ANDROID_NS, MAX_MANIFEST_BYTES, _chunks, _Strings, _u16, _u32


def manifest_fields(data: bytes) -> dict:
    result = {"min_sdk": None, "target_sdk": None, "version_name": None, "app_name": None, "permissions": []}
    try:
        if not data or len(data) > MAX_MANIFEST_BYTES:
            return result
        elements = []
        if data.lstrip().startswith(b"<"):
            root = ET.fromstring(data)
            if root.tag != "manifest":
                return result
            elements = [(element.tag, {key[len(ANDROID_NS) + 2:]: value for key, value in element.attrib.items()
                                       if key.startswith("{" + ANDROID_NS + "}")}) for element in root.iter()]
        else:
            kind, header, size = struct.unpack_from("<HHI", data)
            if kind != 3 or header != 8 or size != len(data):
                return result
            strings = None
            for kind, offset, header, size in _chunks(data, 8, len(data)):
                if kind == 1:
                    strings = _Strings(data, offset, header, size)
                elif kind == 0x102 and strings:
                    ext, end = offset + header, offset + size
                    if ext + 20 > end:
                        raise ValueError("Eksik manifest.")
                    start, stride, count = struct.unpack_from("<HHH", data, ext + 8)
                    if start < 20 or stride < 20 or ext + start + stride * count > end:
                        raise ValueError("Geçersiz manifest.")
                    attrs = {}
                    for index in range(count):
                        attr = ext + start + index * stride
                        namespace = _u32(data, attr)
                        if namespace == 0xffffffff or strings.get(namespace) != ANDROID_NS:
                            continue
                        if _u16(data, attr + 12) != 8:
                            raise ValueError("Geçersiz değer.")
                        key, value = strings.get(_u32(data, attr + 4)), _u32(data, attr + 16)
                        attrs[key] = strings.get(value) if data[attr + 15] == 3 else value if data[attr + 15] in (0x10, 0x11) else None
                    elements.append((strings.get(_u32(data, ext + 4)), attrs))
        for tag, attrs in elements:
            if tag == "manifest":
                value = attrs.get("versionName")
                result["version_name"] = value if isinstance(value, str) and not value.startswith("@") else None
            elif tag == "application":
                value = attrs.get("label")
                result["app_name"] = value if isinstance(value, str) and not value.startswith("@") else None
            elif tag == "uses-sdk":
                for key, attr in (("min_sdk", "minSdkVersion"), ("target_sdk", "targetSdkVersion")):
                    value = attrs.get(attr)
                    if isinstance(value, str) and value.isascii() and value.isdecimal() and len(value) <= 5:
                        value = int(value)
                    result[key] = value if isinstance(value, int) and 1 <= value <= 10000 else None
            elif tag in {"uses-permission", "uses-permission-sdk-23"}:
                value = attrs.get("name")
                if isinstance(value, str) and not value.startswith("@") and len(value) <= 300 and len(result["permissions"]) < 500:
                    result["permissions"].append(value)
        result["permissions"] = sorted(set(result["permissions"]))
        return result
    except (ValueError, struct.error, IndexError, TypeError, UnicodeError, ET.ParseError):
        return {"min_sdk": None, "target_sdk": None, "version_name": None, "app_name": None, "permissions": []}


def signature_schemes(path, archive) -> list[str]:
    schemes = []
    names = [name.upper() for name in archive.namelist() if name.upper().startswith("META-INF/")]
    if any(name.endswith((".RSA", ".DSA", ".EC")) for name in names) and any(name.endswith(".SF") for name in names):
        schemes.append("V1")
    # APK signing blocks immediately precede the ZIP central directory. Inspect
    # only pair headers, not certificates or signer payloads, with bounded reads.
    try:
        offset = archive.start_dir
        if offset < 24:
            return schemes
        with open(path, "rb") as source:
            source.seek(offset - 24)
            footer = source.read(24)
            size = struct.unpack_from("<Q", footer)[0]
            if footer[8:] != b"APK Sig Block 42" or not 24 <= size <= min(offset - 8, 32 * 1024 * 1024):
                return schemes
            start, end = offset - size - 8, offset - 24
            source.seek(start)
            if struct.unpack("<Q", source.read(8))[0] != size:
                return schemes
            cursor, detected = start + 8, []
            for _ in range(256):
                if cursor == end:
                    schemes.extend(detected)
                    break
                if cursor + 12 > end:
                    break
                source.seek(cursor)
                length, identity = struct.unpack("<QI", source.read(12))
                if length < 4 or cursor + 8 + length > end:
                    break
                label = {0x7109871a: "V2", 0xf05368c0: "V3", 0x1b93ad61: "V3.1"}.get(identity)
                if label and label not in detected:
                    detected.append(label)
                cursor += 8 + length
    except (OSError, struct.error):
        pass
    return schemes


def inspect_package_info(path) -> dict:
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo("AndroidManifest.xml") if "AndroidManifest.xml" in archive.namelist() else None
        result = manifest_fields(archive.read(info)) if info and info.file_size <= MAX_MANIFEST_BYTES else manifest_fields(b"")
        result["abis"] = sorted({parts[1] for name in archive.namelist()
                                 if len(parts := name.split("/")) == 3 and parts[0] == "lib" and parts[2].endswith(".so")})
        result["signature_schemes"] = signature_schemes(path, archive)
        return result
