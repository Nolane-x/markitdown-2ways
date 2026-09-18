from __future__ import annotations

from hashlib import sha256
import struct

from .cfb import parse_cfb
from .limits import MsgLimits
from .model import (
    CfbPhysicalRange,
    CfbStream,
    MsgFormatError,
    MsgPropertyEntry,
    MsgSubjectOwner,
    ParsedMsg,
)

_PROPERTIES_STREAM = "__properties_version1.0"
_SUBJECT_STREAM = "__substg1.0_0037001F"

_PT_LONG = 0x0003
_PT_STRING8 = 0x001E
_PT_UNICODE = 0x001F

_SUBJECT_TAG = 0x0037001F
_ANSI_SUBJECT_TAG = 0x0037001E
_STORE_SUPPORT_TAG = 0x340D0003
_SUBJECT_PREFIX_ID = 0x003D
_NORMALIZED_SUBJECT_ID = 0x0E1D

_PROPATTR_READABLE = 0x00000002
_PROPATTR_WRITABLE = 0x00000004
_STORE_UNICODE_OK = 0x00040000


def _logical_slice_ranges(
    stream: CfbStream,
    *,
    offset: int,
    length: int,
) -> tuple[CfbPhysicalRange, ...]:
    if offset < 0 or length < 0 or offset + length > stream.stream_size:
        raise MsgFormatError("MSG property entry range is outside property stream")
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
        raise MsgFormatError("MSG property entry physical mapping is incomplete")
    return tuple(result)


def _parse_property_entries(
    stream: CfbStream,
    *,
    limits: MsgLimits,
) -> tuple[MsgPropertyEntry, ...]:
    data = stream.logical_bytes
    if len(data) < 32 or (len(data) - 32) % 16:
        raise MsgFormatError(
            "MSG property stream length is not a 32-byte header plus 16-byte entries"
        )
    count = (len(data) - 32) // 16
    if count > limits.max_property_entries:
        raise MsgFormatError("MSG property entry count exceeds resource limit")

    entries: list[MsgPropertyEntry] = []
    for index in range(count):
        offset = 32 + index * 16
        raw = data[offset : offset + 16]
        property_tag, flags, value_u32, reserved = struct.unpack("<IIII", raw)
        entries.append(
            MsgPropertyEntry(
                index=index,
                property_tag=property_tag,
                property_id=property_tag >> 16,
                property_type=property_tag & 0xFFFF,
                flags=flags,
                value_u32=value_u32,
                reserved=reserved,
                raw=raw,
                raw_sha256=sha256(raw).hexdigest(),
                logical_offset=offset,
                physical_ranges=_logical_slice_ranges(
                    stream,
                    offset=offset,
                    length=16,
                ),
            )
        )
    return tuple(entries)


def _add_blocker(blockers: list[str], reason: str) -> None:
    if reason not in blockers:
        blockers.append(reason)


def parse_msg(data: bytes, *, limits: MsgLimits | None = None) -> ParsedMsg:
    active_limits = limits or MsgLimits()
    cfb = parse_cfb(data, limits=active_limits)
    properties_stream = cfb.stream(_PROPERTIES_STREAM, parent_id=0)
    entries = _parse_property_entries(properties_stream, limits=active_limits)

    blockers: list[str] = []
    subject_entries = tuple(
        entry for entry in entries if entry.property_tag == _SUBJECT_TAG
    )
    store_entries = tuple(
        entry for entry in entries if entry.property_tag == _STORE_SUPPORT_TAG
    )
    subject_streams = tuple(
        stream
        for stream in cfb.streams
        if stream.parent_id == 0 and stream.name == _SUBJECT_STREAM
    )

    if not subject_entries:
        _add_blocker(blockers, "msg.subject.missing")
    elif len(subject_entries) > 1:
        _add_blocker(blockers, "msg.subject.duplicate_property")

    if not subject_streams:
        _add_blocker(blockers, "msg.subject.missing")
    elif len(subject_streams) > 1:
        _add_blocker(blockers, "msg.subject.duplicate_stream")

    store_support_mask = 0
    if len(store_entries) != 1:
        _add_blocker(blockers, "msg.subject.ansi_read_only")
    else:
        store_entry = store_entries[0]
        if store_entry.property_type != _PT_LONG:
            _add_blocker(blockers, "msg.subject.ansi_read_only")
        if not (store_entry.flags & _PROPATTR_READABLE):
            _add_blocker(blockers, "msg.subject.ansi_read_only")
        store_support_mask = store_entry.value_u32
        if not (store_support_mask & _STORE_UNICODE_OK):
            _add_blocker(blockers, "msg.subject.ansi_read_only")

    if any(
        entry.property_type == _PT_STRING8 or entry.property_tag == _ANSI_SUBJECT_TAG
        for entry in entries
    ):
        _add_blocker(blockers, "msg.subject.ansi_read_only")

    if any(
        entry.property_id in {_SUBJECT_PREFIX_ID, _NORMALIZED_SUBJECT_ID}
        for entry in entries
    ):
        _add_blocker(blockers, "msg.subject.competing_semantics")

    subject_entry = subject_entries[0] if len(subject_entries) == 1 else None
    subject_stream = subject_streams[0] if len(subject_streams) == 1 else None
    subject_owner: MsgSubjectOwner | None = None

    if subject_entry is not None:
        if subject_entry.property_type != _PT_UNICODE:
            _add_blocker(blockers, "msg.subject.ansi_read_only")
        required_flags = _PROPATTR_READABLE | _PROPATTR_WRITABLE
        if subject_entry.flags & required_flags != required_flags:
            _add_blocker(blockers, "msg.subject.property_not_writable")

    if subject_entry is not None and subject_stream is not None:
        if subject_stream.stream_size > active_limits.max_subject_bytes:
            raise MsgFormatError("MSG subject stream exceeds resource limit")
        if subject_entry.value_u32 != subject_stream.stream_size + 2:
            _add_blocker(blockers, "msg.subject.size_mismatch")

        raw_subject = subject_stream.logical_bytes
        decoded: str | None = None
        if not raw_subject or len(raw_subject) % 2:
            _add_blocker(blockers, "msg.subject.invalid_utf16")
        else:
            try:
                decoded = raw_subject.decode("utf-16-le", errors="strict")
            except UnicodeDecodeError:
                _add_blocker(blockers, "msg.subject.invalid_utf16")
            if decoded is not None and any(
                0xD800 <= ord(character) <= 0xDFFF for character in decoded
            ):
                decoded = None
                _add_blocker(blockers, "msg.subject.invalid_utf16")

        if decoded is not None and "\x00" in decoded:
            decoded = None
            _add_blocker(blockers, "msg.subject.embedded_nul")

        if decoded is not None:
            subject_owner = MsgSubjectOwner(
                property_id=0x0037,
                property_type=_PT_UNICODE,
                property_tag=_SUBJECT_TAG,
                value=decoded,
                declared_size=subject_entry.value_u32,
                property_entry=subject_entry,
                stream=subject_stream,
            )

    return ParsedMsg(
        cfb=cfb,
        properties_stream=properties_stream,
        property_entries=entries,
        subject_owner=subject_owner,
        store_support_mask=store_support_mask,
        blockers=tuple(blockers),
    )
