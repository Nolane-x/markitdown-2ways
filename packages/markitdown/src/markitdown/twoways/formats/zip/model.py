from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Mapping

if TYPE_CHECKING:
    from ...ir.document import Diagnostic, DocumentIR


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


@dataclass
class ZipBudgetState:
    global_members: int = 0
    global_expanded_bytes: int = 0


@dataclass(frozen=True)
class ZipMemberClassification:
    state: Literal["typed", "opaque", "ambiguous"]
    adapter_key: str | None = None
    probes: tuple[str, ...] = ()
    reason_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "probes", tuple(self.probes))
        if self.state == "typed" and not self.adapter_key:
            raise ValueError("typed ZIP member classification requires adapter_key")
        if self.state != "typed" and self.adapter_key is not None:
            raise ValueError(
                "non-typed ZIP member classification cannot set adapter_key"
            )


@dataclass(frozen=True)
class ZipMemberChain:
    parts: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "parts", tuple(self.parts))
        if not self.parts:
            raise ValueError("ZIP member chain must be non-empty")


@dataclass(frozen=True)
class ZipParsedMember:
    entry: ZipPackageEntry
    chain: tuple[str, ...]
    classification: ZipMemberClassification
    nested_archive: ParsedZipSource | None = None
    inner_document: DocumentIR | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "chain", tuple(self.chain))
        if not self.chain:
            raise ValueError("parsed ZIP member chain must be non-empty")


@dataclass(frozen=True)
class ParsedZipSource:
    snapshot: ZipPackageSnapshot
    members: tuple[ZipParsedMember, ...]
    depth: int
    diagnostics: tuple[Diagnostic, ...] = ()
    member_by_chain: Mapping[tuple[str, ...], ZipParsedMember] = field(
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        members = tuple(self.members)
        diagnostics = tuple(self.diagnostics)
        index: dict[tuple[str, ...], ZipParsedMember] = {}
        for member in members:
            index[member.chain] = member
            if member.nested_archive is not None:
                index.update(member.nested_archive.member_by_chain)
        object.__setattr__(self, "members", members)
        object.__setattr__(self, "diagnostics", diagnostics)
        object.__setattr__(self, "member_by_chain", index)
