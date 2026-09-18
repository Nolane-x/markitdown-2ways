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
    if len(properties) > 64 or len(subject) > 64:
        raise ValueError("Task-1 fixture keeps both streams in one mini sector")

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
    root_stream_size = 192 if duplicate_subject_name else 128
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
        start_sector=0,
        stream_size=len(properties),
    )
    subject_start_mini_sector = 0 if overlap_streams else 1
    subject_right = 3 if duplicate_subject_name else NOSTREAM
    subj = _directory_entry(
        SUBJECT_STREAM,
        object_type=2,
        right=subject_right,
        start_sector=subject_start_mini_sector,
        stream_size=len(subject),
    )
    directory[0:128] = root
    directory[128:256] = props
    directory[256:384] = subj
    if duplicate_subject_name:
        directory[384:512] = _directory_entry(
            SUBJECT_STREAM,
            object_type=2,
            start_sector=2,
            stream_size=len(subject),
        )

    minifat = bytearray(sector_size)
    minifat_entries = [FREESECT] * (sector_size // 4)
    minifat_entries[0] = ENDOFCHAIN
    minifat_entries[1] = 1 if mini_cycle else ENDOFCHAIN
    minifat_entries[2] = ENDOFCHAIN
    struct.pack_into(
        f"<{len(minifat_entries)}I",
        minifat,
        0,
        *minifat_entries,
    )

    mini_stream = bytearray(sector_size)
    mini_stream[0 : len(properties)] = properties
    mini_stream[64 : 64 + len(subject)] = subject
    if duplicate_subject_name:
        mini_stream[128 : 128 + len(subject)] = subject

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
        properties_physical_start=root_stream_start,
        subject_physical_start=root_stream_start + 64,
    )


def make_truncated_cfb() -> bytes:
    fixture = make_cfb()
    return fixture.data[:-100]
