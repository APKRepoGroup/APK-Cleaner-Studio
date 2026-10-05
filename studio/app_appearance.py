"""Validated, optional launcher presentation changes; no third-party image codec."""
from __future__ import annotations

import base64
import binascii
import struct
import zlib

MAX_ICON_BYTES = 512 * 1024


def validate_appearance(value) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict) or set(value) - {"name", "icon"}:
        raise ValueError("Uygulama görünümü seçimi geçersiz.")
    name, icon = value.get("name", ""), value.get("icon", "")
    if not isinstance(name, str) or not isinstance(icon, str):
        raise ValueError("Uygulama adı veya simgesi geçersiz.")
    name = name.strip()
    if len(name) > 80 or any(ord(char) < 32 or 0x7f <= ord(char) <= 0x9f or 0xd800 <= ord(char) <= 0xdfff for char in name):
        raise ValueError("Uygulama adı en fazla 80 karakter olmalı ve kontrol karakteri içermemeli.")
    if icon:
        if not icon.startswith("data:image/png;base64,") or len(icon) > MAX_ICON_BYTES * 4 // 3 + 30:
            raise ValueError("Simge geçersiz veya 512 KB sınırını aşıyor.")
        try:
            data = base64.b64decode(icon.split(",", 1)[1], validate=True)
            validate_png(data)
        except (ValueError, binascii.Error, struct.error, zlib.error) as exc:
            raise ValueError("Simge okunamadı. PNG, JPEG veya WebP dosyasını yeniden seç.") from exc
    return {"name": name, "icon": icon} if name or icon else {}


def validate_png(data: bytes) -> None:
    if not 45 <= len(data) <= MAX_ICON_BYTES or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Geçersiz PNG.")
    cursor, compressed, dimensions, ended = 8, bytearray(), None, False
    while cursor + 12 <= len(data):
        length = struct.unpack_from(">I", data, cursor)[0]
        kind, end = data[cursor + 4:cursor + 8], cursor + 12 + length
        if end > len(data):
            raise ValueError("Eksik PNG.")
        payload = data[cursor + 8:end - 4]
        if zlib.crc32(kind + payload) & 0xffffffff != struct.unpack_from(">I", data, end - 4)[0]:
            raise ValueError("Bozuk PNG.")
        if dimensions is None:
            if kind != b"IHDR" or length != 13:
                raise ValueError("Eksik PNG başlığı.")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            if not (1 <= width <= 512 and 1 <= height <= 512 and depth == 8 and color in (2, 6)
                    and compression == filtering == interlace == 0):
                raise ValueError("Simge biçimi desteklenmiyor.")
            dimensions = (width, height, 4 if color == 6 else 3)
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            if length or end != len(data):
                raise ValueError("Geçersiz PNG sonu.")
            ended = True
            break
        elif kind == b"IHDR" or kind == b"acTL" or kind[:1].isupper() and kind != b"PLTE":
            raise ValueError("Desteklenmeyen PNG bölümü.")
        cursor = end
    if not dimensions or not ended or not compressed:
        raise ValueError("Eksik simge.")
    width, height, channels = dimensions
    row = 1 + width * channels
    decoder = zlib.decompressobj()
    pixels = decoder.decompress(bytes(compressed), row * height + 1)
    if len(pixels) != row * height or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("Geçersiz simge verisi.")
    if any(pixels[index] > 4 for index in range(0, len(pixels), row)):
        raise ValueError("Geçersiz simge filtresi.")
