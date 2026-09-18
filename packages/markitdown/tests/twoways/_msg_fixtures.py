from __future__ import annotations

import struct
from dataclasses import dataclass

FREESECT = 0xFFFFFFFF
ENDOFCHAIN = 0xFFFFFFFE
FATSECT = 0xFFFFFFFD
NOSTREAM = 0xFFFFFFFF

CFB_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")

PROPERTIES_STREAM = "__properties_version1.0"
SUBJECT_STREAM = "__substg1.0_0037001F"

PROPATTR_READABLE = 0x00000002
PROPATTR_WRITABLE = 0x00000004
STORE_UNICODE_OK = 0x00040000

SUBJECT_TAG = 0x0037001F
ANSI_SUBJECT_TAG = 0x0037001E
SUBJECT_PREFIX_UNICODE_TAG = 0x003D001F
NORMALIZED_SUBJECT_UNICODE_TAG = 0x0E1D001F
STORE_SUPPORT_TAG = 0x340D0003


@dataclass(frozen=True)
class CfbFixture:
    data: bytes
    sector_size: int
    properties_bytes: bytes
    subject_bytes: bytes
    properties_physical_start: int
    subject_physical_start: int


def _directory_entry(
    name: str,
    *,
    object_type: int,
    left: int = NOSTREAM,
    right: int = NOSTREAM,
    child: int = NOSTREAM,
    start_sector: int = ENDOFCHAIN,
    stream_size: int = 0,
) -> bytes:
    raw = bytearray(128)
    name_bytes = (name + "\x00").encode("utf-16-le")
    if len(name_bytes) > 64:
        raise ValueError("directory name is too long")
    raw[: len(name_bytes)] = name_bytes
    struct.pack_into("<H", raw, 64, len(name_bytes))
    raw[66] = object_type
    raw[67] = 1
    struct.pack_into("<III", raw, 68, left, right, child)
    struct.pack_into("<I", raw, 116, start_sector)
    struct.pack_into("<Q", raw, 120, stream_size)
    return bytes(raw)


def _mini_count(size: int) -> int:
    return (size + 63) // 64


def _link_minichain(entries: list[int], start: int, count: int) -> None:
    for index in range(count):
        current = start + index
        entries[current] = current + 1 if index + 1 < count else ENDOFCHAIN


def make_cfb(
    *,
    major_version: int = 3,
    properties_bytes: bytes | None = None,
    subject_bytes: bytes | None = None,
    fat_cycle: bool = False,
    mini_cycle: bool = False,
    directory_sector_out_of_bounds: bool = False,
    overlap_streams: bool = False,
    duplicate_subject_name: bool = False,
) -> CfbFixture:
    if major_version not in {3, 4}:
        raise ValueError("major_version must be 3 or 4")
    sector_size = 512 if major_version == 3 else 4096
    sector_shift = 9 if major_version == 3 else 12

    properties = properties_bytes if properties_bytes is not None else b"P" * 64
    subject = (
        subject_bytes if subject_bytes is not None else "Alpha".encode("utf-16-le")
    )
    if not properties or not subject:
        raise ValueError("Task fixtures require non-empty streams")

    properties_count = _mini_count(len(properties))
    subject_count = _mini_count(len(subject))
    properties_start = 0
    subject_start = 0 if overlap_streams else properties_count
    next_free = max(properties_count, subject_start + subject_count)
    duplicate_start = next_free
    if duplicate_subject_name:
        next_free += subject_count
    root_stream_size = next_free * 64
    if root_stream_size > sector_size:
        raise ValueError("Task fixture mini stream must fit one FAT sector")

    header = bytearray(sector_size)
    header[0:8] = CFB_SIGNATURE
    struct.pack_into("<H", header, 24, 0x003E)
    struct.pack_into("<H", header, 26, major_version)
    struct.pack_into("<H", header, 28, 0xFFFE)
    struct.pack_into("<H", header, 30, sector_shift)
    struct.pack_into("<H", header, 32, 6)
    struct.pack_into("<I", header, 40, 0 if major_version == 3 else 1)
    struct.pack_into("<I", header, 44, 1)
    struct.pack_into(
        "<I",
        header,
        48,
        99 if directory_sector_out_of_bounds else 0,
    )
    struct.pack_into("<I", header, 52, 0)
    struct.pack_into("<I", header, 56, 0x1000)
    struct.pack_into("<I", header, 60, 1)
    struct.pack_into("<I", header, 64, 1)
    struct.pack_into("<I", header, 68, ENDOFCHAIN)
    struct.pack_into("<I", header, 72, 0)
    difat = [3] + [FREESECT] * 108
    struct.pack_into("<109I", header, 76, *difat)

    directory = bytearray(sector_size)
    root = _directory_entry(
        "Root Entry",
        object_type=5,
        child=1,
        start_sector=2,
        stream_size=root_stream_size,
    )
    props = _directory_entry(
        PROPERTIES_STREAM,
        object_type=2,
        right=2,
        start_sector=properties_start,
        stream_size=len(properties),
    )
    subject_right = 3 if duplicate_subject_name else NOSTREAM
    subj = _directory_entry(
        SUBJECT_STREAM,
        object_type=2,
        right=subject_right,
        start_sector=subject_start,
        stream_size=len(subject),
    )
    directory[0:128] = root
    directory[128:256] = props
    directory[256:384] = subj
    if duplicate_subject_name:
        directory[384:512] = _directory_entry(
            SUBJECT_STREAM,
            object_type=2,
            start_sector=duplicate_start,
            stream_size=len(subject),
        )

    minifat = bytearray(sector_size)
    minifat_entries = [FREESECT] * (sector_size // 4)
    _link_minichain(minifat_entries, properties_start, properties_count)
    _link_minichain(minifat_entries, subject_start, subject_count)
    if duplicate_subject_name:
        _link_minichain(minifat_entries, duplicate_start, subject_count)
    if mini_cycle:
        minifat_entries[subject_start + subject_count - 1] = subject_start
    struct.pack_into(
        f"<{len(minifat_entries)}I",
        minifat,
        0,
        *minifat_entries,
    )

    mini_stream = bytearray(sector_size)
    props_offset = properties_start * 64
    subject_offset = subject_start * 64
    mini_stream[props_offset : props_offset + len(properties)] = properties
    mini_stream[subject_offset : subject_offset + len(subject)] = subject
    if duplicate_subject_name:
        duplicate_offset = duplicate_start * 64
        mini_stream[duplicate_offset : duplicate_offset + len(subject)] = subject

    fat = bytearray(sector_size)
    fat_entries = [FREESECT] * (sector_size // 4)
    fat_entries[0] = 0 if fat_cycle else ENDOFCHAIN
    fat_entries[1] = ENDOFCHAIN
    fat_entries[2] = ENDOFCHAIN
    fat_entries[3] = FATSECT
    struct.pack_into(f"<{len(fat_entries)}I", fat, 0, *fat_entries)

    data = bytes(header + directory + minifat + mini_stream + fat)
    root_stream_start = sector_size * 3
    return CfbFixture(
        data=data,
        sector_size=sector_size,
        properties_bytes=properties,
        subject_bytes=subject,
        properties_physical_start=root_stream_start + props_offset,
        subject_physical_start=root_stream_start + subject_offset,
    )


def _property_entry(
    tag: int,
    *,
    flags: int,
    value_or_size: int,
    reserved: int = 0,
) -> bytes:
    return struct.pack("<IIII", tag, flags, value_or_size, reserved)


def make_property_stream(
    subject_bytes: bytes,
    *,
    include_subject: bool = True,
    duplicate_subject: bool = False,
    include_store_support: bool = True,
    duplicate_store_support: bool = False,
    unicode_ok: bool = True,
    subject_flags: int = PROPATTR_READABLE | PROPATTR_WRITABLE,
    store_flags: int = PROPATTR_READABLE,
    include_ansi_subject: bool = False,
    include_subject_prefix: bool = False,
    include_normalized_subject: bool = False,
    subject_size_adjust: int = 0,
) -> bytes:
    entries: list[bytes] = []
    if include_store_support:
        mask = STORE_UNICODE_OK if unicode_ok else 0
        store_entry = _property_entry(
            STORE_SUPPORT_TAG,
            flags=store_flags,
            value_or_size=mask,
        )
        entries.append(store_entry)
        if duplicate_store_support:
            entries.append(store_entry)

    if include_subject:
        subject_entry = _property_entry(
            SUBJECT_TAG,
            flags=subject_flags,
            value_or_size=len(subject_bytes) + 2 + subject_size_adjust,
        )
        entries.append(subject_entry)
        if duplicate_subject:
            entries.append(subject_entry)

    if include_ansi_subject:
        entries.append(
            _property_entry(
                ANSI_SUBJECT_TAG,
                flags=PROPATTR_READABLE,
                value_or_size=2,
            )
        )
    if include_subject_prefix:
        entries.append(
            _property_entry(
                SUBJECT_PREFIX_UNICODE_TAG,
                flags=PROPATTR_READABLE,
                value_or_size=2,
            )
        )
    if include_normalized_subject:
        entries.append(
            _property_entry(
                NORMALIZED_SUBJECT_UNICODE_TAG,
                flags=PROPATTR_READABLE,
                value_or_size=2,
            )
        )

    return b"\x00" * 32 + b"".join(entries)


def make_msg_cfb(
    *,
    subject: str = "Alpha",
    subject_bytes: bytes | None = None,
    **property_options: object,
) -> CfbFixture:
    raw_subject = (
        subject_bytes if subject_bytes is not None else subject.encode("utf-16-le")
    )
    properties = make_property_stream(raw_subject, **property_options)
    return make_cfb(properties_bytes=properties, subject_bytes=raw_subject)


def make_truncated_cfb() -> bytes:
    fixture = make_cfb()
    return fixture.data[:-100]
