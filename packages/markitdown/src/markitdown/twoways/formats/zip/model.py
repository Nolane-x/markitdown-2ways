from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


class ZipParseError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        reason: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.details = dict(details or {})


@dataclass(frozen=True)
class ZipPackageEntry:
    name: str
    uncompressed_sha256: str
    uncompressed_size: int
    compressed_size: int
    compression_method: int
    crc: int
    flag_bits: int
    date_time: tuple[int, int, int, int, int, int]
    comment: bytes
    extra: bytes
    create_system: int
    create_version: int
    extract_version: int
    internal_attr: int
    external_attr: int
    is_directory: bool


@dataclass(frozen=True)
class ZipPackageSnapshot:
    source_sha256: str
    source_size: int
    entries: tuple[ZipPackageEntry, ...]
    archive_comment: bytes = b""
    entry_by_name: Mapping[str, ZipPackageEntry] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(self.entries))
        object.__setattr__(
            self,
            "entry_by_name",
            {entry.name: entry for entry in self.entries},
        )
