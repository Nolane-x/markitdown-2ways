from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from io import BytesIO
import re
import stat
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from .limits import ZipRecursiveLimits
from .model import ZipPackageEntry, ZipPackageSnapshot, ZipParseError


_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_SUPPORTED_COMPRESSION = frozenset({ZIP_STORED, ZIP_DEFLATED})


def _fail(reason: str, message: str, **details: object) -> None:
    raise ZipParseError(message, reason=reason, details=details)


def validate_member_name(name: str) -> None:
    if not name or "\\" in name or name.startswith("/") or _DRIVE_RE.match(name):
        _fail(
            "zip.package.unsafe_member_path",
            "ZIP package contains an unsafe member path.",
            member=name,
        )
    parts = name.split("/")
    if any(part in {".", ".."} for part in parts) or any(
        part == "" for part in parts[:-1]
    ):
        _fail(
            "zip.package.unsafe_member_path",
            "ZIP package contains an unsafe member path.",
            member=name,
        )


def _is_symlink(info: ZipInfo) -> bool:
    if info.create_system != 3:
        return False
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_IFMT(mode) == stat.S_IFLNK


def snapshot_zip_package(
    source: bytes,
    *,
    limits: ZipRecursiveLimits | None = None,
) -> ZipPackageSnapshot:
    limits = limits or ZipRecursiveLimits()
    try:
        archive = ZipFile(BytesIO(source), "r")
    except (BadZipFile, ValueError) as exc:
        raise ZipParseError(
            "Invalid ZIP package.",
            reason="zip.package.malformed_zip",
        ) from exc

    with archive:
        infos = archive.infolist()
        if len(infos) > limits.max_members_per_archive:
            _fail(
                "zip.package.too_many_members",
                "ZIP package exceeds the configured member limit.",
                members=len(infos),
                limit=limits.max_members_per_archive,
            )

        seen: set[str] = set()
        total = 0
        entries: list[ZipPackageEntry] = []
        for info in infos:
            name = info.filename
            validate_member_name(name)
            if name in seen:
                _fail(
                    "zip.package.duplicate_member",
                    "ZIP package contains duplicate member names.",
                    member=name,
                )
            seen.add(name)
            if info.flag_bits & 0x1:
                _fail(
                    "zip.package.encrypted_member",
                    "Encrypted ZIP members are not supported.",
                    member=name,
                )
            if _is_symlink(info):
                _fail(
                    "zip.package.symlink_member",
                    "Symbolic-link ZIP members are not supported.",
                    member=name,
                )
            if info.compress_type not in _SUPPORTED_COMPRESSION:
                _fail(
                    "zip.package.unsupported_compression",
                    "ZIP member uses an unsupported compression method.",
                    member=name,
                    compression_method=info.compress_type,
                )
            if info.file_size > limits.max_member_uncompressed_bytes:
                _fail(
                    "zip.package.member_too_large",
                    "ZIP member exceeds the configured size limit.",
                    member=name,
                    size=info.file_size,
                    limit=limits.max_member_uncompressed_bytes,
                )
            total += info.file_size
            if total > limits.max_archive_uncompressed_bytes:
                _fail(
                    "zip.package.archive_too_large",
                    "ZIP package exceeds the configured archive size limit.",
                    size=total,
                    limit=limits.max_archive_uncompressed_bytes,
                )
            if info.file_size:
                if info.compress_size == 0:
                    _fail(
                        "zip.package.compression_ratio_too_high",
                        "ZIP member has an unsafe compression ratio.",
                        member=name,
                    )
                ratio = info.file_size / info.compress_size
                if ratio > limits.max_compression_ratio:
                    _fail(
                        "zip.package.compression_ratio_too_high",
                        "ZIP member exceeds the configured compression-ratio limit.",
                        member=name,
                        ratio=ratio,
                        limit=limits.max_compression_ratio,
                    )
            try:
                content = archive.read(info)
            except (BadZipFile, RuntimeError, ValueError) as exc:
                raise ZipParseError(
                    "Unable to read ZIP package member.",
                    reason="zip.package.member_read_failed",
                    details={"member": name},
                ) from exc
            entries.append(
                ZipPackageEntry(
                    name=name,
                    uncompressed_sha256=sha256(content).hexdigest(),
                    uncompressed_size=info.file_size,
                    compressed_size=info.compress_size,
                    compression_method=info.compress_type,
                    crc=info.CRC,
                    flag_bits=info.flag_bits,
                    date_time=info.date_time,
                    comment=info.comment,
                    extra=info.extra,
                    create_system=info.create_system,
                    create_version=info.create_version,
                    extract_version=info.extract_version,
                    internal_attr=info.internal_attr,
                    external_attr=info.external_attr,
                    is_directory=info.is_dir(),
                )
            )

        return ZipPackageSnapshot(
            source_sha256=sha256(source).hexdigest(),
            source_size=len(source),
            entries=tuple(entries),
            archive_comment=archive.comment,
        )


def read_zip_member(source: bytes, member_name: str) -> bytes:
    try:
        with ZipFile(BytesIO(source), "r") as archive:
            return archive.read(member_name)
    except (BadZipFile, KeyError, RuntimeError, ValueError) as exc:
        raise ZipParseError(
            "Unable to read required ZIP member.",
            reason="zip.package.required_member_read_failed",
            details={"member": member_name},
        ) from exc


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


def _validate_replacement_limits(
    snapshot: ZipPackageSnapshot,
    replacements: Mapping[str, bytes],
    limits: ZipRecursiveLimits,
) -> None:
    total = 0
    for entry in snapshot.entries:
        replacement = replacements.get(entry.name)
        size = len(replacement) if replacement is not None else entry.uncompressed_size
        if size > limits.max_member_uncompressed_bytes:
            _fail(
                "zip.package.output_member_too_large",
                "ZIP output member exceeds the configured size limit.",
                member=entry.name,
                size=size,
                limit=limits.max_member_uncompressed_bytes,
            )
        total += size
        if total > limits.max_archive_uncompressed_bytes:
            _fail(
                "zip.package.output_archive_too_large",
                "ZIP output package exceeds the configured archive size limit.",
                size=total,
                limit=limits.max_archive_uncompressed_bytes,
            )


def build_zip_candidate(
    snapshot: ZipPackageSnapshot,
    source: bytes,
    *,
    replacements: Mapping[str, bytes],
    limits: ZipRecursiveLimits | None = None,
) -> bytes:
    if (
        sha256(source).hexdigest() != snapshot.source_sha256
        or len(source) != snapshot.source_size
    ):
        _fail(
            "zip.package.snapshot_source_mismatch",
            "ZIP package snapshot does not match source bytes.",
        )

    replacements = dict(replacements)
    if not replacements:
        return source

    known = snapshot.entry_by_name
    unknown = sorted(set(replacements) - set(known))
    if unknown:
        _fail(
            "zip.package.unknown_replacement_member",
            "Sparse ZIP writer cannot add new members.",
            members=unknown,
        )
    directories = sorted(name for name in replacements if known[name].is_directory)
    if directories:
        _fail(
            "zip.package.directory_replacement",
            "Sparse ZIP writer cannot replace directory members.",
            members=directories,
        )
    for name, payload in replacements.items():
        if not isinstance(payload, bytes):
            raise TypeError(f"ZIP replacement member must be bytes: {name}")

    limits = limits or ZipRecursiveLimits()
    _validate_replacement_limits(snapshot, replacements, limits)

    try:
        source_archive = ZipFile(BytesIO(source), "r")
    except (BadZipFile, ValueError) as exc:
        raise ZipParseError(
            "Unable to reopen ZIP source for sparse writing.",
            reason="zip.package.source_reopen_failed",
        ) from exc

    output = BytesIO()
    with source_archive, ZipFile(output, "w") as target:
        target.comment = snapshot.archive_comment
        for info in source_archive.infolist():
            payload = replacements.get(info.filename)
            if payload is None:
                payload = source_archive.read(info)
            target.writestr(_clone_zip_info(info), payload)

    candidate = output.getvalue()
    candidate_snapshot = snapshot_zip_package(candidate, limits=limits)
    if tuple(entry.name for entry in candidate_snapshot.entries) != tuple(
        entry.name for entry in snapshot.entries
    ):
        _fail(
            "zip.package.output_inventory_drift",
            "Sparse ZIP writer changed the ordered member inventory.",
        )
    return candidate
