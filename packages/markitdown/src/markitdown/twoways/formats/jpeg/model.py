from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping


@dataclass(frozen=True)
class JpegMarker:
    index: int
    code: int
    start: int
    end: int
    payload_start: int
    payload_end: int
    raw_sha256: str


@dataclass(frozen=True)
class JpegExifTextOwner:
    tag_id: int
    tag_name: str
    marker_index: int
    byte_order: str
    ifd_path: str
    entry_offset: int
    tiff_type: int
    count: int
    value_offset: int
    value_length: int
    value: str
    inline_value: bool
    value_slot_sha256: str
    app1_sha256: str
    ambiguous: bool = False

    def with_ambiguity(self) -> "JpegExifTextOwner":
        return replace(self, ambiguous=True)


@dataclass(frozen=True)
class ParsedJpeg:
    markers: tuple[JpegMarker, ...]
    text_owners: tuple[JpegExifTextOwner, ...]
    exif_segment_count: int
    xmp_present: bool
    iptc_present: bool
    trailing_bytes: bytes
    blockers: tuple[str, ...]
    tag_counts: Mapping[int, int]

    def marker(self, index: int) -> JpegMarker:
        return self.markers[index]
