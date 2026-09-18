from __future__ import annotations

from dataclasses import dataclass


class MsgFormatError(ValueError):
    pass


@dataclass(frozen=True)
class CfbPhysicalRange:
    start: int
    length: int

    @property
    def end(self) -> int:
        return self.start + self.length


@dataclass(frozen=True)
class CfbHeader:
    major_version: int
    minor_version: int
    sector_size: int
    mini_sector_size: int
    mini_stream_cutoff: int
    number_of_directory_sectors: int
    number_of_fat_sectors: int
    first_directory_sector: int
    first_minifat_sector: int
    number_of_minifat_sectors: int
    first_difat_sector: int
    number_of_difat_sectors: int


@dataclass(frozen=True)
class CfbDirectoryEntry:
    directory_id: int
    name: str
    object_type: int
    left_sibling_id: int
    right_sibling_id: int
    child_id: int
    start_sector: int
    stream_size: int
    parent_id: int | None
    entry_offset: int
    directory_entry_sha256: str


@dataclass(frozen=True)
class CfbStream:
    directory_id: int
    parent_id: int
    name: str
    chain_kind: str
    chain: tuple[int, ...]
    stream_size: int
    logical_bytes: bytes
    physical_ranges: tuple[CfbPhysicalRange, ...]
    sha256: str
    directory_entry_sha256: str


@dataclass(frozen=True)
class ParsedCfb:
    header: CfbHeader
    directory_entries: tuple[CfbDirectoryEntry, ...]
    streams: tuple[CfbStream, ...]
    fat_sector_ids: tuple[int, ...]
    difat_sector_ids: tuple[int, ...]
    directory_chain: tuple[int, ...]
    minifat_chain: tuple[int, ...]
    root_chain: tuple[int, ...]
    topology_sha256: str

    def stream(self, name: str, *, parent_id: int = 0) -> CfbStream:
        matches = tuple(
            stream
            for stream in self.streams
            if stream.parent_id == parent_id and stream.name == name
        )
        if not matches:
            raise MsgFormatError(
                f"CFB stream {name!r} is missing under directory {parent_id}"
            )
        if len(matches) != 1:
            raise MsgFormatError(
                f"CFB stream {name!r} is ambiguous or duplicate under directory "
                f"{parent_id}"
            )
        return matches[0]
