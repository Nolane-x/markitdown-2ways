from __future__ import annotations

from collections import Counter
from hashlib import sha256

from .limits import JpegLimits
from .model import JpegExifTextOwner, JpegMarker, ParsedJpeg


class JpegFormatError(ValueError):
    """Raised when a JPEG cannot satisfy the bounded H14 structural contract."""


_SOI = 0xD8
_EOI = 0xD9
_SOS = 0xDA
_APP1 = 0xE1
_APP13 = 0xED
_STANDALONE = frozenset({0x01, *range(0xD0, 0xD8)})
_SUPPORTED_TAGS = {
    0x010E: "ImageDescription",
    0x013B: "Artist",
}
_POINTER_TAGS = {
    0x014A,
    0x8769,
    0x8825,
    0xA005,
}
_FIELD_SIZES = {
    1: 1,
    2: 1,
    3: 2,
    4: 4,
    5: 8,
    6: 1,
    7: 1,
    8: 2,
    9: 4,
    10: 8,
    11: 4,
    12: 8,
    13: 4,
}
_EXIF_PREFIX = b"Exif\x00\x00"
_XMP_PREFIXES = (
    b"http://ns.adobe.com/xap/1.0/\x00",
    b"http://ns.adobe.com/xmp/extension/\x00",
)
_PHOTOSHOP_PREFIX = b"Photoshop 3.0\x00"


def _marker(
    data: bytes,
    *,
    index: int,
    code: int,
    start: int,
    end: int,
    payload_start: int,
    payload_end: int,
) -> JpegMarker:
    return JpegMarker(
        index=index,
        code=code,
        start=start,
        end=end,
        payload_start=payload_start,
        payload_end=payload_end,
        raw_sha256=sha256(data[start:end]).hexdigest(),
    )


def _parse_markers(
    data: bytes,
    limits: JpegLimits,
) -> tuple[tuple[JpegMarker, ...], bytes]:
    if len(data) > limits.max_source_bytes:
        raise JpegFormatError("JPEG source exceeds source byte limit")
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        raise JpegFormatError("JPEG source is missing SOI")

    markers = [
        _marker(
            data,
            index=0,
            code=_SOI,
            start=0,
            end=2,
            payload_start=2,
            payload_end=2,
        )
    ]
    position = 2

    while position < len(data):
        if data[position] != 0xFF:
            raise JpegFormatError("JPEG marker prefix is invalid outside scan data")

        marker_start = position
        while position < len(data) and data[position] == 0xFF:
            position += 1
        if position >= len(data):
            raise JpegFormatError("JPEG marker is truncated")

        code = data[position]
        position += 1
        if code == 0x00:
            raise JpegFormatError("JPEG stuffed marker byte is invalid outside scan data")
        if code == _SOI:
            raise JpegFormatError("JPEG contains an unexpected nested SOI")

        if code == _EOI:
            markers.append(
                _marker(
                    data,
                    index=len(markers),
                    code=code,
                    start=marker_start,
                    end=position,
                    payload_start=position,
                    payload_end=position,
                )
            )
            if len(markers) > limits.max_markers:
                raise JpegFormatError("JPEG marker count exceeds configured limit")
            return tuple(markers), data[position:]

        if code in _STANDALONE:
            markers.append(
                _marker(
                    data,
                    index=len(markers),
                    code=code,
                    start=marker_start,
                    end=position,
                    payload_start=position,
                    payload_end=position,
                )
            )
            if len(markers) > limits.max_markers:
                raise JpegFormatError("JPEG marker count exceeds configured limit")
            continue

        if position + 2 > len(data):
            raise JpegFormatError("JPEG segment length is truncated")
        segment_length = int.from_bytes(data[position : position + 2], "big")
        if segment_length < 2:
            raise JpegFormatError("JPEG segment length must be at least two bytes")

        payload_start = position + 2
        segment_end = position + segment_length
        if segment_end > len(data):
            raise JpegFormatError("JPEG segment length extends beyond the source")
        if segment_end - payload_start > limits.max_segment_data_bytes:
            raise JpegFormatError("JPEG segment data exceeds configured limit")

        markers.append(
            _marker(
                data,
                index=len(markers),
                code=code,
                start=marker_start,
                end=segment_end,
                payload_start=payload_start,
                payload_end=segment_end,
            )
        )
        if len(markers) > limits.max_markers:
            raise JpegFormatError("JPEG marker count exceeds configured limit")
        position = segment_end

        if code != _SOS:
            continue

        while position < len(data):
            if data[position] != 0xFF:
                position += 1
                continue

            prefix_start = position
            while position < len(data) and data[position] == 0xFF:
                position += 1
            if position >= len(data):
                raise JpegFormatError("JPEG scan ends with a truncated marker")

            scan_code = data[position]
            if scan_code == 0x00:
                position += 1
                continue
            if 0xD0 <= scan_code <= 0xD7:
                position += 1
                continue

            position = prefix_start
            break
        else:
            raise JpegFormatError("JPEG source is missing terminal EOI")

    raise JpegFormatError("JPEG source is missing terminal EOI")


def _ranges_overlap(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def _parse_exif(
    data: bytes,
    marker: JpegMarker,
    limits: JpegLimits,
) -> tuple[
    list[JpegExifTextOwner],
    list[tuple[int, int, int]],
    list[tuple[int, int]],
    list[str],
]:
    tiff_base = marker.payload_start + len(_EXIF_PREFIX)
    tiff_end = marker.payload_end
    if tiff_end - tiff_base < 8:
        raise JpegFormatError("Exif TIFF header is truncated")

    byte_order_raw = data[tiff_base : tiff_base + 2]
    if byte_order_raw == b"II":
        byte_order = "little"
    elif byte_order_raw == b"MM":
        byte_order = "big"
    else:
        raise JpegFormatError("Exif TIFF byte order is invalid")

    def require_span(start: int, length: int, label: str) -> None:
        if length < 0 or start < tiff_base or start + length > tiff_end:
            raise JpegFormatError(f"Exif {label} points outside the TIFF payload")

    def u16(offset: int, label: str) -> int:
        require_span(offset, 2, label)
        return int.from_bytes(data[offset : offset + 2], byte_order)

    def u32(offset: int, label: str) -> int:
        require_span(offset, 4, label)
        return int.from_bytes(data[offset : offset + 4], byte_order)

    if u16(tiff_base + 2, "magic") != 42:
        raise JpegFormatError("Exif TIFF magic is invalid")
    ifd0_relative = u32(tiff_base + 4, "IFD0 offset")
    if ifd0_relative == 0:
        raise JpegFormatError("Exif IFD0 offset is zero")

    owners: list[JpegExifTextOwner] = []
    external_ranges: list[tuple[int, int, int]] = []
    structural_ranges: list[tuple[int, int]] = [(tiff_base, tiff_base + 8)]
    blockers: list[str] = []
    visited_ifds: set[int] = set()
    total_entries = 0
    app1_digest = sha256(data[marker.start : marker.end]).hexdigest()

    def parse_ifd(relative: int, path: str, depth: int) -> None:
        nonlocal total_entries
        if depth > limits.max_ifd_depth:
            raise JpegFormatError("Exif IFD depth exceeds configured limit")
        if relative in visited_ifds:
            raise JpegFormatError("Exif IFD cycle is not supported")
        visited_ifds.add(relative)

        ifd_start = tiff_base + relative
        require_span(ifd_start, 2, f"{path} entry count")
        entry_count = u16(ifd_start, f"{path} entry count")
        if entry_count > limits.max_ifd_entries:
            raise JpegFormatError("Exif IFD entry count exceeds configured limit")
        total_entries += entry_count
        if total_entries > limits.max_total_ifd_entries:
            raise JpegFormatError("Exif total IFD entries exceed configured limit")

        table_size = 2 + entry_count * 12 + 4
        require_span(ifd_start, table_size, path)
        table_end = ifd_start + table_size
        structural_ranges.append((ifd_start, table_end))
        child_offsets: list[tuple[int, str]] = []

        for index in range(entry_count):
            entry_offset = ifd_start + 2 + index * 12
            tag_id = u16(entry_offset, "IFD tag")
            tiff_type = u16(entry_offset + 2, "IFD type")
            count = u32(entry_offset + 4, "IFD count")
            unit_size = _FIELD_SIZES.get(tiff_type)
            if unit_size is None:
                raise JpegFormatError("Exif TIFF field type is unsupported")
            value_length = count * unit_size
            if value_length > limits.max_tiff_value_bytes:
                raise JpegFormatError("Exif TIFF value exceeds configured limit")

            inline_value = value_length <= 4
            if inline_value:
                value_offset = entry_offset + 8
                require_span(value_offset, value_length, "inline value")
            else:
                relative_value_offset = u32(entry_offset + 8, "value offset")
                value_offset = tiff_base + relative_value_offset
                require_span(value_offset, value_length, "external value")
                external_ranges.append((value_offset, value_offset + value_length, entry_offset))

            if path == "IFD0" and tag_id in _SUPPORTED_TAGS:
                if tiff_type != 2:
                    blockers.append("jpeg.exif.unsupported_type")
                elif count < 2:
                    blockers.append("jpeg.exif.invalid_text_encoding")
                else:
                    raw_value = data[value_offset : value_offset + value_length]
                    nul_index = raw_value.find(b"\x00")
                    if nul_index < 0 or any(raw_value[nul_index + 1 :]):
                        blockers.append("jpeg.exif.invalid_text_encoding")
                    else:
                        try:
                            value = raw_value[:nul_index].decode("ascii")
                        except UnicodeDecodeError:
                            blockers.append("jpeg.exif.invalid_text_encoding")
                        else:
                            if len(value.encode("ascii")) > limits.max_text_value_bytes:
                                raise JpegFormatError(
                                    "Exif text value exceeds configured text limit"
                                )
                            owners.append(
                                JpegExifTextOwner(
                                    tag_id=tag_id,
                                    tag_name=_SUPPORTED_TAGS[tag_id],
                                    marker_index=marker.index,
                                    byte_order=byte_order,
                                    ifd_path=path,
                                    entry_offset=entry_offset,
                                    tiff_type=tiff_type,
                                    count=count,
                                    value_offset=value_offset,
                                    value_length=value_length,
                                    value=value,
                                    inline_value=inline_value,
                                    value_slot_sha256=sha256(raw_value).hexdigest(),
                                    app1_sha256=app1_digest,
                                )
                            )

            if tag_id in _POINTER_TAGS and tiff_type in {4, 13} and count:
                raw_offsets = data[value_offset : value_offset + value_length]
                for offset_index in range(count):
                    start = offset_index * 4
                    child_relative = int.from_bytes(
                        raw_offsets[start : start + 4], byte_order
                    )
                    if child_relative:
                        child_offsets.append(
                            (child_relative, f"{path}.tag-{tag_id:04x}[{offset_index}]")
                        )

        next_relative = u32(table_end - 4, f"{path} next IFD")
        for child_relative, child_path in child_offsets:
            parse_ifd(child_relative, child_path, depth + 1)
        if next_relative:
            parse_ifd(next_relative, f"{path}.next", depth + 1)

    parse_ifd(ifd0_relative, "IFD0", 0)
    return owners, external_ranges, structural_ranges, blockers


def parse_jpeg(source: bytes, *, limits: JpegLimits | None = None) -> ParsedJpeg:
    if not isinstance(source, (bytes, bytearray, memoryview)):
        raise TypeError("JPEG source must be bytes-like")
    data = bytes(source)
    active_limits = limits or JpegLimits()
    markers, trailing_bytes = _parse_markers(data, active_limits)

    exif_markers: list[JpegMarker] = []
    xmp_present = False
    iptc_present = False
    blockers: list[str] = []
    owners: list[JpegExifTextOwner] = []
    external_ranges: list[tuple[int, int, int, int]] = []
    structural_ranges: list[tuple[int, int, int]] = []

    for marker in markers:
        payload = data[marker.payload_start : marker.payload_end]
        if marker.code == _APP1:
            if payload.startswith(_EXIF_PREFIX):
                exif_markers.append(marker)
            elif payload.startswith(_XMP_PREFIXES):
                xmp_present = True
        elif marker.code == _APP13 and payload.startswith(_PHOTOSHOP_PREFIX):
            iptc_present = True

    for marker in exif_markers:
        (
            segment_owners,
            segment_external_ranges,
            segment_structural_ranges,
            segment_blockers,
        ) = _parse_exif(data, marker, active_limits)
        owners.extend(segment_owners)
        external_ranges.extend(
            (start, end, entry_offset, marker.index)
            for start, end, entry_offset in segment_external_ranges
        )
        structural_ranges.extend(
            (start, end, marker.index) for start, end in segment_structural_ranges
        )
        blockers.extend(segment_blockers)

    if not exif_markers:
        blockers.append("jpeg.exif.missing")
    if len(exif_markers) > 1:
        blockers.append("jpeg.exif.multiple_segments")
    if xmp_present:
        blockers.append("jpeg.metadata.xmp_read_only")
    if iptc_present:
        blockers.append("jpeg.metadata.iptc_read_only")
    if trailing_bytes:
        blockers.append("jpeg.structure.trailing_bytes")

    overlapping_entries: set[tuple[int, int]] = set()
    for index, left in enumerate(external_ranges):
        left_range = (left[0], left[1])
        for right in external_ranges[index + 1 :]:
            if left[3] != right[3]:
                continue
            if _ranges_overlap(left_range, (right[0], right[1])):
                overlapping_entries.add((left[3], left[2]))
                overlapping_entries.add((right[3], right[2]))
        for structural_start, structural_end, marker_index in structural_ranges:
            if left[3] != marker_index:
                continue
            if _ranges_overlap(left_range, (structural_start, structural_end)):
                overlapping_entries.add((left[3], left[2]))
    if overlapping_entries:
        blockers.append("jpeg.exif.value_overlap")

    tag_counts = Counter(owner.tag_id for owner in owners)
    final_owners: list[JpegExifTextOwner] = []
    for owner in owners:
        ambiguous = tag_counts[owner.tag_id] != 1 or (
            owner.marker_index,
            owner.entry_offset,
        ) in overlapping_entries
        final_owners.append(owner.with_ambiguity() if ambiguous else owner)

    if any(count != 1 for count in tag_counts.values()):
        blockers.append("jpeg.exif.duplicate_tag")

    return ParsedJpeg(
        markers=markers,
        text_owners=tuple(final_owners),
        exif_segment_count=len(exif_markers),
        xmp_present=xmp_present,
        iptc_present=iptc_present,
        trailing_bytes=trailing_bytes,
        blockers=tuple(dict.fromkeys(blockers)),
        tag_counts=dict(tag_counts),
    )
