from __future__ import annotations

import struct
from dataclasses import dataclass

FREESECT = 0xFFFFFFFF
ENDOFCHAIN = 0xFFFFFFFE
FATSECT = 0xFFFFFFFD
NOSTREAM = 0xFFFFFFFF

CFB_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")

BOF = 0x0809
EOF = 0x000A
FORMULA = 0x0006
FILEPASS = 0x002F
WSBOOL = 0x0081
BOUNDSHEET8 = 0x0085
NUMBER = 0x0203


@dataclass(frozen=True)
class XlsFixture:
    data: bytes
    workbook_bytes: bytes
    workbook_physical_start: int
    sheet_offset: int
    number_value_offsets: tuple[int, ...]


def record(record_type: int, payload: bytes = b"") -> bytes:
    return struct.pack("<HH", record_type, len(payload)) + payload


def bof(doc_type: int) -> bytes:
    return record(
        BOF,
        struct.pack(
            "<HHHHII",
            0x0600,
            doc_type,
            0x2013,
            0x07CD,
            0,
            0x00000006,
        ),
    )


def boundsheet8(
    sheet_offset: int,
    name: str = "Sheet1",
    *,
    sheet_type: int = 0,
) -> bytes:
    encoded = name.encode("latin-1")
    if not 1 <= len(encoded) <= 31:
        raise ValueError("fixture sheet name must contain 1..31 compressed characters")
    payload = (
        struct.pack("<IBB", sheet_offset, 0, sheet_type)
        + bytes((len(encoded), 0))
        + encoded
    )
    return record(BOUNDSHEET8, payload)


def number(row: int, column: int, value: float, *, xf_index: int = 0) -> bytes:
    return record(NUMBER, struct.pack("<HHHd", row, column, xf_index, value))


def formula(row: int = 0, column: int = 1, *, xf_index: int = 0) -> bytes:
    payload = struct.pack("<HHH", row, column, xf_index) + b"\x00" * 14
    return record(FORMULA, payload)


def make_workbook(
    *,
    values: tuple[tuple[int, int, float, int], ...] = ((0, 0, 1.5, 0),),
    include_formula: bool = False,
    include_filepass: bool = False,
    duplicate_coordinate: bool = False,
    invalid_sheet_pointer: bool = False,
    sheet_type: int = 0,
    dialog_sheet: bool = False,
) -> tuple[bytes, int, tuple[int, ...]]:
    sheet_records = [bof(0x0010)]
    wsbool_flags = 0x0010 if dialog_sheet else 0
    sheet_records.append(record(WSBOOL, struct.pack("<H", wsbool_flags)))
    value_offsets_in_sheet: list[int] = []
    for row, column, value, xf_index in values:
        before = sum(len(item) for item in sheet_records)
        rec = number(row, column, value, xf_index=xf_index)
        value_offsets_in_sheet.append(before + 4 + 6)
        sheet_records.append(rec)
    if duplicate_coordinate and values:
        row, column, value, xf_index = values[0]
        before = sum(len(item) for item in sheet_records)
        rec = number(row, column, value + 1.0, xf_index=xf_index)
        value_offsets_in_sheet.append(before + 4 + 6)
        sheet_records.append(rec)
    if include_formula:
        sheet_records.append(formula())
    sheet_records.append(record(EOF))
    sheet = b"".join(sheet_records)

    globals_bof = bof(0x0005)
    placeholder = boundsheet8(0, sheet_type=sheet_type)
    encrypted = record(FILEPASS, b"\x00" * 4) if include_filepass else b""
    globals_eof = record(EOF)
    sheet_offset = (
        len(globals_bof) + len(placeholder) + len(encrypted) + len(globals_eof)
    )
    pointer = sheet_offset + 1 if invalid_sheet_pointer else sheet_offset
    globals_bytes = (
        globals_bof
        + boundsheet8(pointer, sheet_type=sheet_type)
        + encrypted
        + globals_eof
    )
    workbook = globals_bytes + sheet
    return (
        workbook,
        sheet_offset,
        tuple(sheet_offset + value_offset for value_offset in value_offsets_in_sheet),
    )


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
        raise ValueError("directory name too long")
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


def make_cfb_with_streams(
    streams: tuple[tuple[str, bytes], ...],
) -> tuple[bytes, dict[str, int]]:
    if not streams or len(streams) > 3:
        raise ValueError("fixture supports 1..3 streams")
    sector_size = 512
    minifat_entries = [FREESECT] * (sector_size // 4)
    mini_stream = bytearray(sector_size)
    next_mini = 0
    stream_meta: list[tuple[str, bytes, int, int]] = []
    physical: dict[str, int] = {}

    root_physical_start = 3 * sector_size
    for name, data in streams:
        if not data:
            raise ValueError("fixture streams must be non-empty")
        count = _mini_count(len(data))
        if next_mini + count > 8:
            raise ValueError("fixture mini stream exceeds one sector")
        start = next_mini
        for index in range(count):
            current = start + index
            minifat_entries[current] = (
                current + 1 if index + 1 < count else ENDOFCHAIN
            )
        offset = start * 64
        mini_stream[offset : offset + len(data)] = data
        physical.setdefault(name, root_physical_start + offset)
        stream_meta.append((name, data, start, count))
        next_mini += count

    root_stream_size = next_mini * 64

    header = bytearray(sector_size)
    header[:8] = CFB_SIGNATURE
    struct.pack_into("<H", header, 24, 0x003E)
    struct.pack_into("<H", header, 26, 3)
    struct.pack_into("<H", header, 28, 0xFFFE)
    struct.pack_into("<H", header, 30, 9)
    struct.pack_into("<H", header, 32, 6)
    struct.pack_into("<I", header, 40, 0)
    struct.pack_into("<I", header, 44, 1)
    struct.pack_into("<I", header, 48, 0)
    struct.pack_into("<I", header, 52, 0)
    struct.pack_into("<I", header, 56, 0x1000)
    struct.pack_into("<I", header, 60, 1)
    struct.pack_into("<I", header, 64, 1)
    struct.pack_into("<I", header, 68, ENDOFCHAIN)
    struct.pack_into("<I", header, 72, 0)
    struct.pack_into("<109I", header, 76, 3, *([FREESECT] * 108))

    directory = bytearray(sector_size)
    directory[:128] = _directory_entry(
        "Root Entry",
        object_type=5,
        child=1,
        start_sector=2,
        stream_size=root_stream_size,
    )
    for index, (name, data, start, _count) in enumerate(stream_meta, start=1):
        right = index + 1 if index < len(stream_meta) else NOSTREAM
        directory[index * 128 : (index + 1) * 128] = _directory_entry(
            name,
            object_type=2,
            right=right,
            start_sector=start,
            stream_size=len(data),
        )

    minifat = bytearray(sector_size)
    struct.pack_into(
        f"<{len(minifat_entries)}I",
        minifat,
        0,
        *minifat_entries,
    )

    fat = bytearray(sector_size)
    fat_entries = [FREESECT] * (sector_size // 4)
    fat_entries[0] = ENDOFCHAIN
    fat_entries[1] = ENDOFCHAIN
    fat_entries[2] = ENDOFCHAIN
    fat_entries[3] = FATSECT
    struct.pack_into(f"<{len(fat_entries)}I", fat, 0, *fat_entries)

    return bytes(header + directory + minifat + mini_stream + fat), physical


def make_xls_cfb(
    *,
    duplicate_workbook: bool = False,
    competing_book: bool = False,
    **workbook_options: object,
) -> XlsFixture:
    workbook, sheet_offset, number_offsets = make_workbook(**workbook_options)
    streams: list[tuple[str, bytes]] = [("Workbook", workbook)]
    if duplicate_workbook:
        streams.append(("Workbook", workbook))
    if competing_book:
        streams.append(("Book", workbook))
    data, physical = make_cfb_with_streams(tuple(streams))
    return XlsFixture(
        data=data,
        workbook_bytes=workbook,
        workbook_physical_start=physical["Workbook"],
        sheet_offset=sheet_offset,
        number_value_offsets=number_offsets,
    )
