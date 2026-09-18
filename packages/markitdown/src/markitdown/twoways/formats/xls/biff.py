from __future__ import annotations

from hashlib import sha256
import math
import struct

from .cfb import parse_cfb
from .limits import XlsLimits
from .model import (
    BiffRecord,
    CfbPhysicalRange,
    CfbStream,
    ParsedXls,
    XlsFormatError,
    XlsNumberOwner,
    XlsSheet,
)

_BOF = 0x0809
_EOF = 0x000A
_FORMULA = 0x0006
_FILEPASS = 0x002F
_WSBOOL = 0x0081
_BOUNDSHEET8 = 0x0085
_NUMBER = 0x0203
_MAX_BIFF_PAYLOAD = 8224

_BIFF8_VERSION = 0x0600
_WORKBOOK_GLOBALS = 0x0005
_WORKSHEET_OR_DIALOG = 0x0010

_BLOCKER_ORDER = (
    "xls.container.competing_book_stream",
    "xls.workbook.encrypted",
    "xls.workbook.formulas_present",
    "xls.sheet.unsupported_type",
    "xls.cell.duplicate_owner",
    "xls.cell.non_finite",
)


def _u16(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def logical_slice_ranges(
    stream: CfbStream,
    *,
    offset: int,
    length: int,
) -> tuple[CfbPhysicalRange, ...]:
    if offset < 0 or length < 0 or offset + length > stream.stream_size:
        raise XlsFormatError("XLS logical range is outside Workbook stream")
    wanted_start = offset
    wanted_end = offset + length
    logical_cursor = 0
    result: list[CfbPhysicalRange] = []
    for physical in stream.physical_ranges:
        logical_start = logical_cursor
        logical_end = logical_cursor + physical.length
        overlap_start = max(wanted_start, logical_start)
        overlap_end = min(wanted_end, logical_end)
        if overlap_start < overlap_end:
            result.append(
                CfbPhysicalRange(
                    start=physical.start + (overlap_start - logical_start),
                    length=overlap_end - overlap_start,
                )
            )
        logical_cursor = logical_end
    if sum(item.length for item in result) != length:
        raise XlsFormatError("XLS logical-to-physical mapping is incomplete")
    return tuple(result)


def _scan_records(data: bytes, *, limits: XlsLimits) -> tuple[BiffRecord, ...]:
    records: list[BiffRecord] = []
    offset = 0
    while offset < len(data):
        if len(records) >= limits.max_biff_records:
            raise XlsFormatError("XLS BIFF record count exceeds resource limit")
        if offset + 4 > len(data):
            raise XlsFormatError("XLS BIFF record header is truncated")
        record_type, payload_size = struct.unpack_from("<HH", data, offset)
        if payload_size > _MAX_BIFF_PAYLOAD:
            raise XlsFormatError("XLS BIFF record payload exceeds format limit")
        end = offset + 4 + payload_size
        if end > len(data):
            raise XlsFormatError("XLS BIFF record payload is truncated")
        raw = data[offset:end]
        records.append(
            BiffRecord(
                index=len(records),
                record_type=record_type,
                header_offset=offset,
                payload_offset=offset + 4,
                payload_size=payload_size,
                end_offset=end,
                raw=raw,
                raw_sha256=sha256(raw).hexdigest(),
            )
        )
        offset = end
    return tuple(records)


def _bof_identity(record: BiffRecord) -> tuple[int, int]:
    if record.record_type != _BOF or record.payload_size < 4:
        raise XlsFormatError("XLS expected a valid BOF record")
    payload = record.raw[4:]
    return _u16(payload), _u16(payload, 2)


def _decode_boundsheet(record: BiffRecord) -> tuple[int, int, int, str]:
    payload = record.raw[4:]
    if len(payload) < 8:
        raise XlsFormatError("XLS BoundSheet8 record is truncated")
    bof_offset = _u32(payload)
    hidden_state = payload[4] & 0x03
    if hidden_state not in {0, 1, 2}:
        raise XlsFormatError("XLS BoundSheet8 hidden state is invalid")
    sheet_type = payload[5]
    if sheet_type not in {0x00, 0x01, 0x02, 0x06}:
        raise XlsFormatError("XLS BoundSheet8 sheet type is invalid")
    cch = payload[6]
    flags = payload[7]
    if not 1 <= cch <= 31:
        raise XlsFormatError("XLS BoundSheet8 sheet name length is invalid")
    if flags & 0xFE:
        raise XlsFormatError("XLS BoundSheet8 string flags are unsupported")
    high_byte = bool(flags & 0x01)
    encoded_length = cch * (2 if high_byte else 1)
    if len(payload) != 8 + encoded_length:
        raise XlsFormatError("XLS BoundSheet8 sheet name is truncated or extended")
    raw_name = payload[8:]
    try:
        name = raw_name.decode("utf-16-le" if high_byte else "latin-1")
    except UnicodeDecodeError as exc:
        raise XlsFormatError("XLS BoundSheet8 sheet name encoding is invalid") from exc
    if (
        "\x00" in name
        or "\x03" in name
        or any(char in name for char in ":\\*?/[ ]".replace(" ", ""))
        or name.startswith("'")
        or name.endswith("'")
    ):
        raise XlsFormatError("XLS BoundSheet8 sheet name is invalid")
    return bof_offset, hidden_state, sheet_type, name


def _sheet_records(
    records: tuple[BiffRecord, ...],
    *,
    start_index: int,
) -> tuple[BiffRecord, ...]:
    result: list[BiffRecord] = []
    for record in records[start_index:]:
        result.append(record)
        if record.record_type == _EOF:
            return tuple(result)
    raise XlsFormatError("XLS sheet substream is missing EOF")


def _parse_number_owner(
    record: BiffRecord,
    *,
    workbook_stream: CfbStream,
) -> XlsNumberOwner:
    if record.payload_size != 14:
        raise XlsFormatError("XLS Number record has invalid payload size")
    payload = record.raw[4:]
    row, column, xf_index = struct.unpack_from("<HHH", payload, 0)
    value = struct.unpack_from("<d", payload, 6)[0]
    value_offset = record.payload_offset + 6
    value_raw = payload[6:14]
    return XlsNumberOwner(
        row=row,
        column=column,
        xf_index=xf_index,
        value=value,
        record=record,
        value_logical_offset=value_offset,
        value_physical_ranges=logical_slice_ranges(
            workbook_stream,
            offset=value_offset,
            length=8,
        ),
        record_sha256=record.raw_sha256,
        value_sha256=sha256(value_raw).hexdigest(),
    )


def _ordered_blockers(values: list[str]) -> tuple[str, ...]:
    present = set(values)
    ordered = [reason for reason in _BLOCKER_ORDER if reason in present]
    ordered.extend(sorted(present - set(ordered)))
    return tuple(ordered)


def parse_xls(data: bytes, *, limits: XlsLimits | None = None) -> ParsedXls:
    active_limits = limits or XlsLimits()
    cfb = parse_cfb(data, limits=active_limits)
    workbook_stream = cfb.stream("Workbook", parent_id=0)
    if workbook_stream.stream_size > active_limits.max_workbook_bytes:
        raise XlsFormatError("XLS Workbook stream exceeds resource limit")

    blockers: list[str] = []
    if any(stream.parent_id == 0 and stream.name == "Book" for stream in cfb.streams):
        blockers.append("xls.container.competing_book_stream")

    records = _scan_records(workbook_stream.logical_bytes, limits=active_limits)
    if not records:
        raise XlsFormatError("XLS Workbook stream contains no BIFF records")

    version, doc_type = _bof_identity(records[0])
    if version != _BIFF8_VERSION:
        raise XlsFormatError("XLS workbook uses an unsupported BIFF version")
    if doc_type != _WORKBOOK_GLOBALS:
        raise XlsFormatError("XLS first BOF is not the workbook globals substream")

    globals_eof_index: int | None = None
    for index, record in enumerate(records[1:], start=1):
        if record.record_type == _EOF:
            globals_eof_index = index
            break
    if globals_eof_index is None:
        raise XlsFormatError("XLS workbook globals substream is missing EOF")

    globals_records = records[: globals_eof_index + 1]
    bound_records = tuple(
        record for record in globals_records if record.record_type == _BOUNDSHEET8
    )
    if len(bound_records) > active_limits.max_sheets:
        raise XlsFormatError("XLS sheet count exceeds resource limit")
    if any(record.record_type == _FILEPASS for record in records):
        blockers.append("xls.workbook.encrypted")
    if any(record.record_type == _FORMULA for record in records):
        blockers.append("xls.workbook.formulas_present")

    offset_to_index = {
        record.header_offset: index for index, record in enumerate(records)
    }
    if len(offset_to_index) != len(records):
        raise XlsFormatError("XLS BIFF record offsets are ambiguous")

    decoded_bounds = [_decode_boundsheet(record) for record in bound_records]
    names_seen: set[str] = set()
    pointers_seen: set[int] = set()
    sheets: list[XlsSheet] = []
    number_owner_count = 0

    for bof_offset, hidden_state, sheet_type, name in decoded_bounds:
        folded = name.casefold()
        if folded in names_seen:
            raise XlsFormatError("XLS BoundSheet8 sheet names are duplicated")
        names_seen.add(folded)
        if bof_offset in pointers_seen:
            raise XlsFormatError("XLS BoundSheet8 BOF pointers are duplicated")
        pointers_seen.add(bof_offset)

        start_index = offset_to_index.get(bof_offset)
        if start_index is None:
            raise XlsFormatError("XLS BoundSheet8 pointer does not resolve to a BOF")
        version, sheet_doc_type = _bof_identity(records[start_index])
        if version != _BIFF8_VERSION:
            raise XlsFormatError("XLS sheet BOF uses an unsupported BIFF version")

        expected_doc_type = {
            0x00: _WORKSHEET_OR_DIALOG,
            0x01: 0x0040,
            0x02: 0x0020,
            0x06: 0x0040,
        }[sheet_type]
        if sheet_doc_type != expected_doc_type:
            raise XlsFormatError(
                "XLS BoundSheet8 pointer resolves to mismatched BOF type"
            )

        substream = _sheet_records(records, start_index=start_index)
        is_dialog = False
        if sheet_type == 0:
            wsbool_records = tuple(
                record for record in substream if record.record_type == _WSBOOL
            )
            if len(wsbool_records) != 1 or wsbool_records[0].payload_size != 2:
                raise XlsFormatError(
                    "XLS worksheet must contain one valid WsBool record"
                )
            wsbool_value = _u16(wsbool_records[0].raw, 4)
            is_dialog = bool(wsbool_value & 0x0010)
            if is_dialog:
                blockers.append("xls.sheet.unsupported_type")
        else:
            blockers.append("xls.sheet.unsupported_type")

        owners: list[XlsNumberOwner] = []
        coordinate_set: set[tuple[int, int]] = set()
        if sheet_type == 0 and not is_dialog:
            for record in substream:
                if record.record_type != _NUMBER:
                    continue
                owner = _parse_number_owner(record, workbook_stream=workbook_stream)
                coordinate = (owner.row, owner.column)
                if coordinate in coordinate_set:
                    blockers.append("xls.cell.duplicate_owner")
                coordinate_set.add(coordinate)
                if not math.isfinite(owner.value):
                    blockers.append("xls.cell.non_finite")
                owners.append(owner)
                number_owner_count += 1
                if number_owner_count > active_limits.max_number_owners:
                    raise XlsFormatError(
                        "XLS NUMBER owner count exceeds resource limit"
                    )

        sheets.append(
            XlsSheet(
                name=name,
                hidden_state=hidden_state,
                sheet_type=sheet_type,
                bof_offset=bof_offset,
                eof_offset=substream[-1].header_offset,
                is_dialog=is_dialog,
                records=substream,
                number_owners=tuple(owners),
            )
        )

    if len(sheets) != len(bound_records):
        raise XlsFormatError("XLS sheet discovery is incomplete")

    topology_parts = tuple(
        (record.index, record.record_type, record.header_offset, record.payload_size)
        for record in records
    )
    sheet_parts = tuple(
        (
            sheet.name.casefold(),
            sheet.hidden_state,
            sheet.sheet_type,
            sheet.bof_offset,
            sheet.eof_offset,
        )
        for sheet in sheets
    )
    topology_sha256 = sha256(
        repr((topology_parts, sheet_parts)).encode("utf-8")
    ).hexdigest()
    return ParsedXls(
        cfb=cfb,
        workbook_stream=workbook_stream,
        records=records,
        sheets=tuple(sheets),
        blockers=_ordered_blockers(blockers),
        biff_topology_sha256=topology_sha256,
    )
