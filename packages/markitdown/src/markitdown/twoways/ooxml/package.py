from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import re
from typing import BinaryIO, Mapping
from zipfile import BadZipFile, ZipFile, ZipInfo

from .._errors import OOXMLPackageError, SourcePackageMismatchError
from ..ir.document import DocumentIR
from .limits import OOXMLPackageLimits

_DRIVE_RE = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True)
class OOXMLPackageEntry:
    name: str
    uncompressed_sha256: str
    uncompressed_size: int
    compressed_size: int
    compression_method: int
    crc: int
    flag_bits: int


@dataclass(frozen=True)
class OOXMLPackageSnapshot:
    source_sha256: str
    source_size: int
    entries: tuple[OOXMLPackageEntry, ...]
    archive_comment: bytes = b""

    @property
    def entry_by_name(self) -> dict[str, OOXMLPackageEntry]:
        return {entry.name: entry for entry in self.entries}


def _fail(reason: str, message: str, **details: object) -> None:
    raise OOXMLPackageError(message, details={"reason": reason, **details})


def _validate_name(name: str) -> None:
    if not name or "\\" in name or name.startswith("/") or _DRIVE_RE.match(name):
        _fail("unsafe_member_path", "OOXML package contains an unsafe member path.", member=name)
    parts = name.split("/")
    if any(part in {".", ".."} for part in parts) or any(
        part == "" for part in parts[:-1]
    ):
        _fail("unsafe_member_path", "OOXML package contains an unsafe member path.", member=name)



def read_binary_stream(stream: BinaryIO, *, stream_label: str) -> bytes:
    data = stream.read()
    if not isinstance(data, bytes):
        raise TypeError(f"{stream_label} stream must yield bytes")
    return data

def snapshot_package(
    source_bytes: bytes,
    *,
    limits: OOXMLPackageLimits | None = None,
) -> OOXMLPackageSnapshot:
    limits = limits or OOXMLPackageLimits()
    try:
        archive = ZipFile(BytesIO(source_bytes), "r")
    except (BadZipFile, ValueError) as exc:
        raise OOXMLPackageError(
            "Invalid OOXML ZIP package.",
            details={"reason": "malformed_zip"},
        ) from exc

    with archive:
        infos = archive.infolist()
        if len(infos) > limits.max_members:
            _fail(
                "too_many_members",
                "OOXML package exceeds the configured member limit.",
                members=len(infos),
                limit=limits.max_members,
            )

        seen: set[str] = set()
        total = 0
        entries: list[OOXMLPackageEntry] = []
        for info in infos:
            name = info.filename
            _validate_name(name)
            if name in seen:
                _fail(
                    "duplicate_member",
                    "OOXML package contains duplicate member names.",
                    member=name,
                )
            seen.add(name)
            if info.flag_bits & 0x1:
                _fail(
                    "encrypted_member",
                    "Encrypted OOXML members are not supported.",
                    member=name,
                )
            if info.file_size > limits.max_member_uncompressed_bytes:
                _fail(
                    "member_too_large",
                    "OOXML member exceeds the configured size limit.",
                    member=name,
                    size=info.file_size,
                    limit=limits.max_member_uncompressed_bytes,
                )
            if (
                name.lower().endswith((".xml", ".rels"))
                and info.file_size > limits.max_xml_part_bytes
            ):
                _fail(
                    "xml_part_too_large",
                    "OOXML XML part exceeds the configured XML-part size limit.",
                    member=name,
                    size=info.file_size,
                    limit=limits.max_xml_part_bytes,
                )
            total += info.file_size
            if total > limits.max_total_uncompressed_bytes:
                _fail(
                    "package_too_large",
                    "OOXML package exceeds the configured total size limit.",
                    size=total,
                    limit=limits.max_total_uncompressed_bytes,
                )
            if info.file_size and info.compress_size:
                ratio = info.file_size / info.compress_size
                if ratio > limits.max_compression_ratio:
                    _fail(
                        "compression_ratio_too_high",
                        "OOXML member exceeds the configured compression-ratio limit.",
                        member=name,
                        ratio=ratio,
                        limit=limits.max_compression_ratio,
                    )
            try:
                content = archive.read(info)
            except (BadZipFile, RuntimeError, ValueError) as exc:
                raise OOXMLPackageError(
                    "Unable to read OOXML package member.",
                    details={"reason": "member_read_failed", "member": name},
                ) from exc
            entries.append(
                OOXMLPackageEntry(
                    name=name,
                    uncompressed_sha256=sha256(content).hexdigest(),
                    uncompressed_size=info.file_size,
                    compressed_size=info.compress_size,
                    compression_method=info.compress_type,
                    crc=info.CRC,
                    flag_bits=info.flag_bits,
                )
            )

        return OOXMLPackageSnapshot(
            source_sha256=sha256(source_bytes).hexdigest(),
            source_size=len(source_bytes),
            entries=tuple(entries),
            archive_comment=archive.comment,
        )



@dataclass(frozen=True)
class PackagePreservationInspection:
    inventory_matches: bool
    before_names: tuple[str, ...]
    after_names: tuple[str, ...]
    changed_untouched: tuple[str, ...]


def validate_source_authority(
    document: DocumentIR,
    source_bytes: bytes,
    *,
    expected_format: str,
) -> None:
    label = expected_format.upper()
    expected = document.source.sha256 if document.source is not None else None
    actual = sha256(source_bytes).hexdigest()
    if (
        document.source is None
        or document.source.format != expected_format
        or not expected
    ):
        raise SourcePackageMismatchError(
            f"DocumentIR does not contain an authoritative {label} source digest.",
            details={"reason": "missing_source_authority", "actual": actual},
        )
    if expected != actual:
        raise SourcePackageMismatchError(
            f"Provided {label} source does not match the DocumentIR source authority.",
            details={
                "reason": "source_digest_mismatch",
                "expected": expected,
                "actual": actual,
            },
        )


def inspect_package_preservation(
    source_bytes: bytes,
    output_bytes: bytes,
    *,
    touched_parts: tuple[str, ...],
    limits: OOXMLPackageLimits | None = None,
) -> PackagePreservationInspection:
    before = snapshot_package(source_bytes, limits=limits)
    after = snapshot_package(output_bytes, limits=limits)
    before_names = tuple(entry.name for entry in before.entries)
    after_names = tuple(entry.name for entry in after.entries)
    touched = set(touched_parts)
    after_by_name = after.entry_by_name
    changed_untouched = tuple(
        entry.name
        for entry in before.entries
        if entry.name not in touched
        and entry.name in after_by_name
        and after_by_name[entry.name].uncompressed_sha256 != entry.uncompressed_sha256
    )
    return PackagePreservationInspection(
        inventory_matches=before_names == after_names,
        before_names=before_names,
        after_names=after_names,
        changed_untouched=changed_untouched,
    )

def _clone_zip_info(info: ZipInfo) -> ZipInfo:
    clone = ZipInfo(filename=info.filename, date_time=info.date_time)
    clone.compress_type = info.compress_type
    clone.comment = info.comment
    clone.extra = info.extra
    clone.create_system = info.create_system
    clone.create_version = info.create_version
    clone.extract_version = info.extract_version
    clone.reserved = info.reserved
    clone.flag_bits = info.flag_bits & ~0x1
    clone.volume = info.volume
    clone.internal_attr = info.internal_attr
    clone.external_attr = info.external_attr
    if hasattr(info, "_compresslevel"):
        clone._compresslevel = info._compresslevel  # type: ignore[attr-defined]
    return clone


def write_package(
    snapshot: OOXMLPackageSnapshot,
    source_bytes: bytes,
    output: BinaryIO,
    *,
    replacements: Mapping[str, bytes],
) -> int:
    if sha256(source_bytes).hexdigest() != snapshot.source_sha256:
        _fail("source_digest_mismatch", "OOXML package snapshot does not match source bytes.")
    if not replacements:
        written = output.write(source_bytes)
        return len(source_bytes) if written is None else written

    known = {entry.name for entry in snapshot.entries}
    unknown = sorted(set(replacements) - known)
    if unknown:
        _fail(
            "unknown_replacement_member",
            "Sparse OOXML writer cannot add new members in this phase.",
            members=unknown,
        )

    source = ZipFile(BytesIO(source_bytes), "r")
    with source, ZipFile(output, "w") as target:
        target.comment = snapshot.archive_comment
        for info in source.infolist():
            data = replacements.get(info.filename)
            if data is None:
                data = source.read(info)
            target.writestr(_clone_zip_info(info), data)

    try:
        return output.tell()
    except (AttributeError, OSError):
        return 0
