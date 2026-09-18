from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import struct

from .limits import MsgLimits
from .model import (
    CfbDirectoryEntry,
    CfbHeader,
    CfbPhysicalRange,
    CfbStream,
    MsgFormatError,
    ParsedCfb,
)

_CFB_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
_FREESECT = 0xFFFFFFFF
_ENDOFCHAIN = 0xFFFFFFFE
_FATSECT = 0xFFFFFFFD
_DIFSECT = 0xFFFFFFFC
_NOSTREAM = 0xFFFFFFFF

_REGULAR_SECTOR_MARKERS = frozenset({_FREESECT, _ENDOFCHAIN, _FATSECT, _DIFSECT})


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _u64(data: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def _sector_offset(sector_id: int, sector_size: int, sector_count: int) -> int:
    if sector_id < 0 or sector_id >= sector_count:
        raise MsgFormatError("CFB sector is outside source bounds")
    return (sector_id + 1) * sector_size


def _sector_bytes(
    data: bytes,
    sector_id: int,
    *,
    sector_size: int,
    sector_count: int,
) -> bytes:
    start = _sector_offset(sector_id, sector_size, sector_count)
    end = start + sector_size
    if end > len(data):
        raise MsgFormatError("CFB sector is truncated")
    return data[start:end]


def _walk_chain(
    start_sector: int,
    table: tuple[int, ...],
    *,
    sector_count: int,
    max_sectors: int,
    label: str,
) -> tuple[int, ...]:
    if start_sector in {_ENDOFCHAIN, _FREESECT}:
        return ()
    chain: list[int] = []
    seen: set[int] = set()
    sector = start_sector
    while sector != _ENDOFCHAIN:
        if sector in seen:
            raise MsgFormatError(f"CFB {label} chain cycle detected")
        if sector in _REGULAR_SECTOR_MARKERS or sector >= sector_count:
            raise MsgFormatError(f"CFB {label} chain sector is outside bounds")
        if len(chain) >= max_sectors:
            raise MsgFormatError(f"CFB {label} chain exceeds resource limit")
        if sector >= len(table):
            raise MsgFormatError(f"CFB {label} chain table is truncated")
        seen.add(sector)
        chain.append(sector)
        next_sector = table[sector]
        if next_sector == _FREESECT:
            raise MsgFormatError(f"CFB {label} chain terminates in a free sector")
        if next_sector in {_FATSECT, _DIFSECT}:
            raise MsgFormatError(f"CFB {label} chain enters structural sector")
        sector = next_sector
    return tuple(chain)


def _ranges_overlap(
    first: tuple[CfbPhysicalRange, ...],
    second: tuple[CfbPhysicalRange, ...],
) -> bool:
    for left in first:
        for right in second:
            if left.start < right.end and right.start < left.end:
                return True
    return False


def _read_regular_stream(
    data: bytes,
    *,
    start_sector: int,
    stream_size: int,
    fat_entries: tuple[int, ...],
    sector_size: int,
    sector_count: int,
    limits: MsgLimits,
    label: str,
) -> tuple[bytes, tuple[int, ...], tuple[CfbPhysicalRange, ...]]:
    if stream_size < 0 or stream_size > limits.max_stream_bytes:
        raise MsgFormatError(f"CFB {label} stream exceeds resource limit")
    if stream_size == 0:
        if start_sector not in {_ENDOFCHAIN, _FREESECT, 0}:
            raise MsgFormatError(f"CFB empty {label} stream has invalid start sector")
        return b"", (), ()

    chain = _walk_chain(
        start_sector,
        fat_entries,
        sector_count=sector_count,
        max_sectors=limits.max_chain_sectors,
        label=label,
    )
    expected_sectors = (stream_size + sector_size - 1) // sector_size
    if len(chain) != expected_sectors:
        raise MsgFormatError(f"CFB {label} stream chain size mismatch")

    remaining = stream_size
    chunks: list[bytes] = []
    ranges: list[CfbPhysicalRange] = []
    for sector_id in chain:
        raw = _sector_bytes(
            data,
            sector_id,
            sector_size=sector_size,
            sector_count=sector_count,
        )
        take = min(remaining, sector_size)
        start = _sector_offset(sector_id, sector_size, sector_count)
        chunks.append(raw[:take])
        ranges.append(CfbPhysicalRange(start=start, length=take))
        remaining -= take
    if remaining:
        raise MsgFormatError(f"CFB {label} stream is truncated")
    return b"".join(chunks), chain, tuple(ranges)


def _read_ministream(
    *,
    root_bytes: bytes,
    root_chain: tuple[int, ...],
    start_mini_sector: int,
    stream_size: int,
    minifat_entries: tuple[int, ...],
    mini_sector_size: int,
    sector_size: int,
    sector_count: int,
    limits: MsgLimits,
    label: str,
) -> tuple[bytes, tuple[int, ...], tuple[CfbPhysicalRange, ...]]:
    if stream_size <= 0:
        raise MsgFormatError(f"CFB {label} mini stream has invalid size")
    if stream_size > limits.max_stream_bytes:
        raise MsgFormatError(f"CFB {label} stream exceeds resource limit")

    mini_sector_count = (len(root_bytes) + mini_sector_size - 1) // mini_sector_size
    chain: list[int] = []
    seen: set[int] = set()
    mini_sector = start_mini_sector
    while mini_sector != _ENDOFCHAIN:
        if mini_sector in seen:
            raise MsgFormatError(f"CFB MiniFAT {label} chain cycle detected")
        if mini_sector in _REGULAR_SECTOR_MARKERS or mini_sector >= mini_sector_count:
            raise MsgFormatError(f"CFB MiniFAT {label} sector is outside bounds")
        if mini_sector >= len(minifat_entries):
            raise MsgFormatError(f"CFB MiniFAT {label} table is truncated")
        if len(chain) >= limits.max_chain_sectors:
            raise MsgFormatError(f"CFB MiniFAT {label} chain exceeds resource limit")
        seen.add(mini_sector)
        chain.append(mini_sector)
        next_sector = minifat_entries[mini_sector]
        if next_sector == _FREESECT:
            raise MsgFormatError(
                f"CFB MiniFAT {label} chain terminates in a free sector"
            )
        if next_sector in {_FATSECT, _DIFSECT}:
            raise MsgFormatError(f"CFB MiniFAT {label} chain uses invalid marker")
        mini_sector = next_sector

    expected_sectors = (stream_size + mini_sector_size - 1) // mini_sector_size
    if len(chain) != expected_sectors:
        raise MsgFormatError(f"CFB MiniFAT {label} chain size mismatch")

    remaining = stream_size
    chunks: list[bytes] = []
    ranges: list[CfbPhysicalRange] = []
    for mini_sector_id in chain:
        logical_start = mini_sector_id * mini_sector_size
        if logical_start >= len(root_bytes):
            raise MsgFormatError(f"CFB MiniFAT {label} range is outside root stream")
        root_sector_index = logical_start // sector_size
        within_sector = logical_start % sector_size
        if root_sector_index >= len(root_chain):
            raise MsgFormatError(f"CFB MiniFAT {label} root chain is truncated")
        take = min(remaining, mini_sector_size)
        if logical_start + take > len(root_bytes):
            raise MsgFormatError(f"CFB MiniFAT {label} range is truncated")
        absolute_start = (
            root_chain[root_sector_index] + 1
        ) * sector_size + within_sector
        chunks.append(root_bytes[logical_start : logical_start + take])
        ranges.append(CfbPhysicalRange(start=absolute_start, length=take))
        remaining -= take
    return b"".join(chunks), tuple(chain), tuple(ranges)


def _parse_directory_entry(
    raw: bytes,
    *,
    directory_id: int,
    entry_offset: int,
) -> CfbDirectoryEntry:
    object_type = raw[66]
    name_length = _u16(raw, 64)
    if object_type == 0:
        name = ""
        if name_length not in {0, 2}:
            raise MsgFormatError("CFB empty directory entry has invalid name length")
    else:
        if name_length < 2 or name_length > 64 or name_length % 2:
            raise MsgFormatError("CFB directory entry has invalid name length")
        name_raw = raw[: name_length - 2]
        terminator = raw[name_length - 2 : name_length]
        if terminator != b"\x00\x00":
            raise MsgFormatError("CFB directory entry name is not terminated")
        try:
            name = name_raw.decode("utf-16-le", errors="strict")
        except UnicodeDecodeError as exc:
            raise MsgFormatError(
                "CFB directory entry name is invalid UTF-16LE"
            ) from exc
        if "\x00" in name:
            raise MsgFormatError("CFB directory entry name contains embedded NUL")
    if object_type not in {0, 1, 2, 5}:
        raise MsgFormatError("CFB directory entry has invalid object type")

    return CfbDirectoryEntry(
        directory_id=directory_id,
        name=name,
        object_type=object_type,
        left_sibling_id=_u32(raw, 68),
        right_sibling_id=_u32(raw, 72),
        child_id=_u32(raw, 76),
        start_sector=_u32(raw, 116),
        stream_size=_u64(raw, 120),
        parent_id=None,
        entry_offset=entry_offset,
        directory_entry_sha256=sha256(raw).hexdigest(),
    )


def _assign_directory_parents(
    entries: tuple[CfbDirectoryEntry, ...],
) -> tuple[CfbDirectoryEntry, ...]:
    if not entries or entries[0].object_type != 5:
        raise MsgFormatError("CFB root directory entry is missing")
    parents: dict[int, int | None] = {0: None}
    visiting: set[int] = set()

    def visit_tree(entry_id: int, parent_id: int) -> None:
        if entry_id == _NOSTREAM:
            return
        if entry_id >= len(entries):
            raise MsgFormatError("CFB directory sibling id is outside bounds")
        if entry_id in visiting:
            raise MsgFormatError("CFB directory topology cycle detected")
        entry = entries[entry_id]
        if entry.object_type == 0:
            raise MsgFormatError("CFB directory tree references an empty entry")
        existing_parent = parents.get(entry_id)
        if existing_parent is not None or entry_id in parents:
            if existing_parent != parent_id:
                raise MsgFormatError("CFB directory entry has ambiguous ownership")
            return

        visiting.add(entry_id)
        visit_tree(entry.left_sibling_id, parent_id)
        parents[entry_id] = parent_id
        if entry.object_type in {1, 5}:
            visit_tree(entry.child_id, entry_id)
        visit_tree(entry.right_sibling_id, parent_id)
        visiting.remove(entry_id)

    visit_tree(entries[0].child_id, 0)

    for entry in entries[1:]:
        if entry.object_type != 0 and entry.directory_id not in parents:
            raise MsgFormatError("CFB directory contains unreachable allocated entry")

    return tuple(
        replace(entry, parent_id=parents.get(entry.directory_id)) for entry in entries
    )


def _topology_digest(
    header: CfbHeader,
    entries: tuple[CfbDirectoryEntry, ...],
    streams: tuple[CfbStream, ...],
    *,
    fat_sector_ids: tuple[int, ...],
    difat_sector_ids: tuple[int, ...],
    directory_chain: tuple[int, ...],
    minifat_chain: tuple[int, ...],
    root_chain: tuple[int, ...],
) -> str:
    parts = [
        (
            "header",
            header.major_version,
            header.minor_version,
            header.sector_size,
            header.mini_sector_size,
            header.mini_stream_cutoff,
        ),
        ("fat", fat_sector_ids),
        ("difat", difat_sector_ids),
        ("directory", directory_chain),
        ("minifat", minifat_chain),
        ("root", root_chain),
    ]
    parts.extend(
        (
            "dir",
            entry.directory_id,
            entry.parent_id,
            entry.name,
            entry.object_type,
            entry.left_sibling_id,
            entry.right_sibling_id,
            entry.child_id,
            entry.start_sector,
            entry.stream_size,
            entry.directory_entry_sha256,
        )
        for entry in entries
        if entry.object_type != 0
    )
    parts.extend(
        (
            "stream",
            stream.directory_id,
            stream.parent_id,
            stream.name,
            stream.chain_kind,
            stream.chain,
            stream.stream_size,
            tuple((r.start, r.length) for r in stream.physical_ranges),
            stream.sha256,
        )
        for stream in streams
    )
    return sha256(repr(parts).encode("utf-8")).hexdigest()


def parse_cfb(data: bytes, *, limits: MsgLimits | None = None) -> ParsedCfb:
    active_limits = limits or MsgLimits()
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("CFB source must be bytes")
    source = bytes(data)
    if len(source) > active_limits.max_source_bytes:
        raise MsgFormatError("CFB source exceeds resource limit")
    if len(source) < 512:
        raise MsgFormatError("CFB source is too small or truncated")
    if source[:8] != _CFB_SIGNATURE:
        raise MsgFormatError("CFB signature is invalid")

    minor_version = _u16(source, 24)
    major_version = _u16(source, 26)
    byte_order = _u16(source, 28)
    sector_shift = _u16(source, 30)
    mini_sector_shift = _u16(source, 32)
    if byte_order != 0xFFFE:
        raise MsgFormatError("CFB byte order is unsupported")
    if major_version == 3:
        if sector_shift != 9:
            raise MsgFormatError("CFB version 3 sector shift is invalid")
    elif major_version == 4:
        if sector_shift != 12:
            raise MsgFormatError("CFB version 4 sector shift is invalid")
    else:
        raise MsgFormatError("CFB major version is unsupported")
    if mini_sector_shift != 6:
        raise MsgFormatError("CFB mini sector shift is invalid")

    sector_size = 1 << sector_shift
    mini_sector_size = 1 << mini_sector_shift
    if len(source) < sector_size or (len(source) - sector_size) % sector_size:
        raise MsgFormatError("CFB source size is truncated or not sector aligned")
    if major_version == 4 and any(source[512:sector_size]):
        raise MsgFormatError("CFB version 4 extended header bytes are nonzero")
    sector_count = (len(source) - sector_size) // sector_size

    number_of_directory_sectors = _u32(source, 40)
    number_of_fat_sectors = _u32(source, 44)
    first_directory_sector = _u32(source, 48)
    mini_stream_cutoff = _u32(source, 56)
    first_minifat_sector = _u32(source, 60)
    number_of_minifat_sectors = _u32(source, 64)
    first_difat_sector = _u32(source, 68)
    number_of_difat_sectors = _u32(source, 72)
    if major_version == 3 and number_of_directory_sectors != 0:
        raise MsgFormatError("CFB version 3 directory-sector count must be zero")
    if mini_stream_cutoff != 0x1000:
        raise MsgFormatError("CFB mini stream cutoff is unsupported")
    if (
        number_of_fat_sectors <= 0
        or number_of_fat_sectors > active_limits.max_fat_sectors
    ):
        raise MsgFormatError("CFB FAT sector count exceeds resource limit")
    if number_of_difat_sectors > active_limits.max_difat_sectors:
        raise MsgFormatError("CFB DIFAT sector count exceeds resource limit")
    if number_of_minifat_sectors > active_limits.max_minifat_sectors:
        raise MsgFormatError("CFB MiniFAT sector count exceeds resource limit")

    header = CfbHeader(
        major_version=major_version,
        minor_version=minor_version,
        sector_size=sector_size,
        mini_sector_size=mini_sector_size,
        mini_stream_cutoff=mini_stream_cutoff,
        number_of_directory_sectors=number_of_directory_sectors,
        number_of_fat_sectors=number_of_fat_sectors,
        first_directory_sector=first_directory_sector,
        first_minifat_sector=first_minifat_sector,
        number_of_minifat_sectors=number_of_minifat_sectors,
        first_difat_sector=first_difat_sector,
        number_of_difat_sectors=number_of_difat_sectors,
    )

    fat_sector_ids: list[int] = [
        sector_id
        for sector_id in struct.unpack_from("<109I", source, 76)
        if sector_id != _FREESECT
    ]
    difat_sector_ids: list[int] = []
    next_difat = first_difat_sector
    difat_entries_per_sector = sector_size // 4 - 1
    for _ in range(number_of_difat_sectors):
        if next_difat in difat_sector_ids:
            raise MsgFormatError("CFB DIFAT chain cycle detected")
        raw = _sector_bytes(
            source,
            next_difat,
            sector_size=sector_size,
            sector_count=sector_count,
        )
        difat_sector_ids.append(next_difat)
        values = struct.unpack_from(
            f"<{difat_entries_per_sector + 1}I",
            raw,
            0,
        )
        fat_sector_ids.extend(
            sector_id for sector_id in values[:-1] if sector_id != _FREESECT
        )
        next_difat = values[-1]
    if number_of_difat_sectors == 0:
        if first_difat_sector not in {_ENDOFCHAIN, _FREESECT}:
            raise MsgFormatError("CFB DIFAT start is inconsistent")
    elif next_difat != _ENDOFCHAIN:
        raise MsgFormatError("CFB DIFAT chain does not terminate")
    if len(fat_sector_ids) != number_of_fat_sectors:
        raise MsgFormatError("CFB FAT sector count does not match DIFAT")
    if len(set(fat_sector_ids)) != len(fat_sector_ids):
        raise MsgFormatError("CFB FAT sector ownership is duplicated")
    if set(fat_sector_ids) & set(difat_sector_ids):
        raise MsgFormatError("CFB FAT and DIFAT sectors overlap")
    for sector_id in (*fat_sector_ids, *difat_sector_ids):
        _sector_offset(sector_id, sector_size, sector_count)

    entries_per_fat_sector = sector_size // 4
    fat_values: list[int] = []
    for fat_sector_id in fat_sector_ids:
        raw = _sector_bytes(
            source,
            fat_sector_id,
            sector_size=sector_size,
            sector_count=sector_count,
        )
        fat_values.extend(struct.unpack_from(f"<{entries_per_fat_sector}I", raw, 0))
    fat_entries = tuple(fat_values)
    if len(fat_entries) < sector_count:
        raise MsgFormatError("CFB FAT is truncated")
    for fat_sector_id in fat_sector_ids:
        if fat_entries[fat_sector_id] != _FATSECT:
            raise MsgFormatError("CFB FAT sector marker is invalid")
    for difat_sector_id in difat_sector_ids:
        if fat_entries[difat_sector_id] != _DIFSECT:
            raise MsgFormatError("CFB DIFAT sector marker is invalid")

    directory_chain = _walk_chain(
        first_directory_sector,
        fat_entries,
        sector_count=sector_count,
        max_sectors=active_limits.max_chain_sectors,
        label="directory FAT",
    )
    if not directory_chain:
        raise MsgFormatError("CFB directory chain is missing")
    if major_version == 4 and len(directory_chain) != number_of_directory_sectors:
        raise MsgFormatError("CFB directory sector count mismatch")
    directory_bytes = b"".join(
        _sector_bytes(
            source,
            sector_id,
            sector_size=sector_size,
            sector_count=sector_count,
        )
        for sector_id in directory_chain
    )
    directory_slot_count = len(directory_bytes) // 128
    if directory_slot_count > active_limits.max_directory_entries:
        raise MsgFormatError("CFB directory entry count exceeds resource limit")

    parsed_entries: list[CfbDirectoryEntry] = []
    for directory_id in range(directory_slot_count):
        logical_offset = directory_id * 128
        raw = directory_bytes[logical_offset : logical_offset + 128]
        chain_index = logical_offset // sector_size
        within_sector = logical_offset % sector_size
        entry_offset = (
            _sector_offset(
                directory_chain[chain_index],
                sector_size,
                sector_count,
            )
            + within_sector
        )
        parsed_entries.append(
            _parse_directory_entry(
                raw,
                directory_id=directory_id,
                entry_offset=entry_offset,
            )
        )
    directory_entries = _assign_directory_parents(tuple(parsed_entries))
    root = directory_entries[0]

    minifat_chain: tuple[int, ...] = ()
    minifat_entries: tuple[int, ...] = ()
    if number_of_minifat_sectors:
        minifat_chain = _walk_chain(
            first_minifat_sector,
            fat_entries,
            sector_count=sector_count,
            max_sectors=active_limits.max_minifat_sectors,
            label="MiniFAT",
        )
        if len(minifat_chain) != number_of_minifat_sectors:
            raise MsgFormatError("CFB MiniFAT sector count mismatch")
        minifat_bytes = b"".join(
            _sector_bytes(
                source,
                sector_id,
                sector_size=sector_size,
                sector_count=sector_count,
            )
            for sector_id in minifat_chain
        )
        minifat_entries = struct.unpack_from(
            f"<{len(minifat_bytes) // 4}I",
            minifat_bytes,
            0,
        )
    elif first_minifat_sector not in {_ENDOFCHAIN, _FREESECT}:
        raise MsgFormatError("CFB MiniFAT start is inconsistent")

    if root.stream_size > active_limits.max_total_owned_stream_bytes:
        raise MsgFormatError("CFB root mini stream exceeds resource limit")
    root_bytes, root_chain, root_ranges = _read_regular_stream(
        source,
        start_sector=root.start_sector,
        stream_size=root.stream_size,
        fat_entries=fat_entries,
        sector_size=sector_size,
        sector_count=sector_count,
        limits=active_limits,
        label="root mini",
    )
    structural_sector_ids = (
        set(fat_sector_ids)
        | set(difat_sector_ids)
        | set(directory_chain)
        | set(minifat_chain)
    )
    if set(root_chain) & structural_sector_ids:
        raise MsgFormatError("CFB root mini stream overlaps structural sectors")

    streams: list[CfbStream] = []
    total_stream_bytes = 0
    for entry in directory_entries:
        if entry.object_type != 2:
            continue
        if entry.parent_id is None:
            raise MsgFormatError("CFB stream has no directory owner")
        if entry.stream_size > active_limits.max_stream_bytes:
            raise MsgFormatError("CFB stream exceeds resource limit")
        total_stream_bytes += entry.stream_size
        if total_stream_bytes > active_limits.max_total_owned_stream_bytes:
            raise MsgFormatError("CFB owned stream bytes exceed resource limit")

        if entry.stream_size < mini_stream_cutoff:
            if not minifat_entries:
                raise MsgFormatError("CFB mini stream exists without MiniFAT")
            logical_bytes, chain, physical_ranges = _read_ministream(
                root_bytes=root_bytes,
                root_chain=root_chain,
                start_mini_sector=entry.start_sector,
                stream_size=entry.stream_size,
                minifat_entries=tuple(minifat_entries),
                mini_sector_size=mini_sector_size,
                sector_size=sector_size,
                sector_count=sector_count,
                limits=active_limits,
                label=entry.name or f"directory-{entry.directory_id}",
            )
            chain_kind = "mini"
        else:
            logical_bytes, chain, physical_ranges = _read_regular_stream(
                source,
                start_sector=entry.start_sector,
                stream_size=entry.stream_size,
                fat_entries=fat_entries,
                sector_size=sector_size,
                sector_count=sector_count,
                limits=active_limits,
                label=entry.name or f"directory-{entry.directory_id}",
            )
            chain_kind = "fat"
            regular_sectors = set(chain)
            if regular_sectors & structural_sector_ids:
                raise MsgFormatError("CFB stream overlaps structural sectors")
            if regular_sectors & set(root_chain):
                raise MsgFormatError("CFB stream overlaps root mini stream")

        stream = CfbStream(
            directory_id=entry.directory_id,
            parent_id=entry.parent_id,
            name=entry.name,
            chain_kind=chain_kind,
            chain=chain,
            stream_size=entry.stream_size,
            logical_bytes=logical_bytes,
            physical_ranges=physical_ranges,
            sha256=sha256(logical_bytes).hexdigest(),
            directory_entry_sha256=entry.directory_entry_sha256,
        )
        for other in streams:
            if _ranges_overlap(stream.physical_ranges, other.physical_ranges):
                raise MsgFormatError("CFB stream physical ranges overlap or alias")
        streams.append(stream)

    stream_tuple = tuple(streams)
    topology_sha256 = _topology_digest(
        header,
        directory_entries,
        stream_tuple,
        fat_sector_ids=tuple(fat_sector_ids),
        difat_sector_ids=tuple(difat_sector_ids),
        directory_chain=directory_chain,
        minifat_chain=minifat_chain,
        root_chain=root_chain,
    )
    return ParsedCfb(
        header=header,
        directory_entries=directory_entries,
        streams=stream_tuple,
        fat_sector_ids=tuple(fat_sector_ids),
        difat_sector_ids=tuple(difat_sector_ids),
        directory_chain=directory_chain,
        minifat_chain=minifat_chain,
        root_chain=root_chain,
        topology_sha256=topology_sha256,
    )
