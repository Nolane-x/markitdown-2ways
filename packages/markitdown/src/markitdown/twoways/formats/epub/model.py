from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..._errors import TwoWayError


class EpubParseError(TwoWayError):
    def __init__(
        self,
        message: str,
        *,
        reason: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        merged = {"reason": reason, **dict(details or {})}
        super().__init__("two_way.epub_parse", message, merged)


@dataclass(frozen=True)
class EpubPackageEntry:
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


@dataclass(frozen=True)
class EpubPackageSnapshot:
    source_sha256: str
    source_size: int
    entries: tuple[EpubPackageEntry, ...]
    archive_comment: bytes = b""

    @property
    def entry_by_name(self) -> dict[str, EpubPackageEntry]:
        return {entry.name: entry for entry in self.entries}


@dataclass(frozen=True)
class EpubRootfileEvidence:
    path: str
    media_type: str | None


@dataclass(frozen=True)
class EpubManifestItemEvidence:
    index: int
    item_id: str
    href: str
    media_type: str
    properties: tuple[str, ...]
    resolved_path: str | None
    is_remote: bool
    is_navigation: bool


@dataclass(frozen=True)
class EpubSpineItemEvidence:
    index: int
    idref: str
    linear: str | None


@dataclass(frozen=True)
class EpubMetadataOwnerEvidence:
    name: str
    value: str
    member_path: str
    member_sha256: str
    xml_path: str
    raw_digest: str


@dataclass(frozen=True)
class EpubXhtmlTextEvidence:
    value: str
    member_path: str
    member_sha256: str
    manifest_item_id: str
    xml_path: str
    raw_digest: str


@dataclass(frozen=True)
class ParsedEpubSource:
    package: EpubPackageSnapshot
    rootfiles: tuple[EpubRootfileEvidence, ...]
    package_path: str
    package_version: str | None
    writable_version: bool
    read_only_reason: str | None
    manifest: tuple[EpubManifestItemEvidence, ...]
    spine: tuple[EpubSpineItemEvidence, ...]
    metadata_owners: tuple[EpubMetadataOwnerEvidence, ...]
    xhtml_text_owners: tuple[EpubXhtmlTextEvidence, ...]
    unique_identifier_id: str | None = None
    unique_identifier_value: str | None = None
