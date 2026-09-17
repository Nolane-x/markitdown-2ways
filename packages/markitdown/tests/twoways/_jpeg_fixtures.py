from __future__ import annotations

import base64
from dataclasses import dataclass


_BASE_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAUDBAQEAwUEBAQFBQUGBwwIBwcHBw8LCwkMEQ8SEhEP"
    "ERETFhwXExQaFRERGCEYGh0dHx8fExciJCIeJBweHx7/2wBDAQUFBQcGBw4ICA4eFBEUHh4eHh4e"
    "Hh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh7/wAARCAACAAIDAREA"
    "AhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQA"
    "AAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3"
    "ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWm"
    "p6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEA"
    "AwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSEx"
    "BhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElK"
    "U1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3"
    "uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDzGvlD"
    "7Y//2Q=="
)


IMAGE_DESCRIPTION = 0x010E
ARTIST = 0x013B


@dataclass(frozen=True)
class ExifTextEntry:
    tag_id: int
    value: str
    capacity: int | None = None
    force_inline: bool = False


def jpeg_segment(marker_code: int, payload: bytes) -> bytes:
    if not 0 <= marker_code <= 0xFF:
        raise ValueError("marker code must fit one byte")
    length = len(payload) + 2
    if length > 0xFFFF:
        raise ValueError("JPEG segment too large")
    return b"\xff" + bytes((marker_code,)) + length.to_bytes(2, "big") + payload


def _u16(value: int, endian: str) -> bytes:
    return value.to_bytes(2, endian)


def _u32(value: int, endian: str) -> bytes:
    return value.to_bytes(4, endian)


def exif_app1(
    entries: tuple[ExifTextEntry, ...],
    *,
    endian: str = "little",
    overlap_external: bool = False,
) -> bytes:
    if endian not in {"little", "big"}:
        raise ValueError("endian must be little or big")

    byte_order = b"II" if endian == "little" else b"MM"
    ifd_offset = 8
    table_size = 2 + 12 * len(entries) + 4
    external_offset = ifd_offset + table_size

    entry_bytes: list[bytes] = []
    external_values = bytearray()
    shared_external_offset: int | None = None

    for spec in entries:
        encoded = spec.value.encode("ascii")
        capacity = spec.capacity if spec.capacity is not None else len(encoded) + 1
        if capacity < len(encoded) + 1:
            raise ValueError("capacity cannot be smaller than the text plus NUL")
        raw_value = encoded + b"\x00" + b"\x00" * (capacity - len(encoded) - 1)

        entry = bytearray()
        entry += _u16(spec.tag_id, endian)
        entry += _u16(2, endian)
        entry += _u32(capacity, endian)

        if capacity <= 4 or spec.force_inline:
            if capacity > 4:
                raise ValueError("forced inline value must fit four bytes")
            entry += raw_value.ljust(4, b"\x00")
        else:
            if overlap_external and shared_external_offset is not None:
                value_offset = shared_external_offset
            else:
                value_offset = external_offset + len(external_values)
                if shared_external_offset is None:
                    shared_external_offset = value_offset
                external_values += raw_value
            entry += _u32(value_offset, endian)
        entry_bytes.append(bytes(entry))

    tiff = bytearray()
    tiff += byte_order
    tiff += _u16(42, endian)
    tiff += _u32(ifd_offset, endian)
    tiff += _u16(len(entries), endian)
    for entry in entry_bytes:
        tiff += entry
    tiff += _u32(0, endian)
    tiff += external_values
    return jpeg_segment(0xE1, b"Exif\x00\x00" + bytes(tiff))


def xmp_app1() -> bytes:
    return jpeg_segment(
        0xE1,
        b"http://ns.adobe.com/xap/1.0/\x00<x:xmpmeta/>",
    )


def iptc_app13() -> bytes:
    return jpeg_segment(0xED, b"Photoshop 3.0\x008BIM\x04\x04\x00\x00\x00\x00")


def make_jpeg(
    *,
    entries: tuple[ExifTextEntry, ...] = (
        ExifTextEntry(IMAGE_DESCRIPTION, "Alpha", capacity=16),
        ExifTextEntry(ARTIST, "Nolane", capacity=16),
    ),
    endian: str = "little",
    extra_segments: tuple[bytes, ...] = (),
    second_exif: bool = False,
    overlap_external: bool = False,
) -> bytes:
    segments = [
        exif_app1(entries, endian=endian, overlap_external=overlap_external),
        *extra_segments,
    ]
    if second_exif:
        segments.append(
            exif_app1(
                (ExifTextEntry(IMAGE_DESCRIPTION, "Second", capacity=16),),
                endian=endian,
            )
        )
    return _BASE_JPEG[:2] + b"".join(segments) + _BASE_JPEG[2:]


def malformed_marker_length_jpeg() -> bytes:
    return b"\xff\xd8\xff\xe1\x00\x01\xff\xd9"


def malformed_tiff_offset_jpeg() -> bytes:
    tiff = b"II" + _u16(42, "little") + _u32(0x7FFFFFFF, "little")
    return _BASE_JPEG[:2] + jpeg_segment(0xE1, b"Exif\x00\x00" + tiff) + _BASE_JPEG[2:]
