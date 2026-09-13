from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import re
import stat
from zipfile import BadZipFile, ZIP_STORED, ZipFile

from .limits import EpubPackageLimits
from .model import EpubPackageEntry, EpubPackageSnapshot, EpubParseError


_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_XML_SUFFIXES = (".xml", ".opf", ".xhtml", ".html", ".htm")
_EPUB_MIMETYPE = b"application/epub+zip"


def _fail(reason: str, message: str, **details: object) -> None:
    raise EpubParseError(message, reason=reason, details=details)


def validate_member_name(name: str) -> None:
    if not name or "\\" in name or name.startswith("/") or _DRIVE_RE.match(name):
        _fail(
            "epub.package.unsafe_member_path",
            "EPUB package contains an unsafe member path.",
            member=name,
        )
    parts = name.split("/")
    if any(part in {".", ".."} for part in parts) or any(
        part == "" for part in parts[:-1]
    ):
        _fail(
            "epub.package.unsafe_member_path",
            "EPUB package contains an unsafe member path.",
            member=name,
        )


def _is_symlink(create_system: int, external_attr: int) -> bool:
    if create_system != 3:
        return False
    mode = (external_attr >> 16) & 0xFFFF
    return stat.S_IFMT(mode) == stat.S_IFLNK


def snapshot_epub_package(
    source: bytes,
    *,
    limits: EpubPackageLimits | None = None,
) -> EpubPackageSnapshot:
    limits = limits or EpubPackageLimits()
    try:
        archive = ZipFile(BytesIO(source), "r")
    except (BadZipFile, ValueError) as exc:
        raise EpubParseError(
            "Invalid EPUB ZIP package.",
            reason="epub.package.malformed_zip",
        ) from exc

    with archive:
        infos = archive.infolist()
        if not infos:
            _fail("epub.package.empty", "EPUB package contains no members.")
        if len(infos) > limits.max_members:
            _fail(
                "epub.package.too_many_members",
                "EPUB package exceeds the configured member limit.",
                members=len(infos),
                limit=limits.max_members,
            )

        first = infos[0]
        if first.filename != "mimetype":
            _fail(
                "epub.ocf.mimetype_not_first",
                "EPUB OCF mimetype member must be first.",
                first_member=first.filename,
            )
        if first.compress_type != ZIP_STORED:
            _fail(
                "epub.ocf.mimetype_compressed",
                "EPUB OCF mimetype member must be stored without compression.",
            )
        if first.extra:
            _fail(
                "epub.ocf.mimetype_extra_field",
                "EPUB OCF mimetype member must not carry a ZIP extra field.",
            )

        seen: set[str] = set()
        total = 0
        entries: list[EpubPackageEntry] = []
        for info in infos:
            name = info.filename
            validate_member_name(name)
            if name in seen:
                _fail(
                    "epub.package.duplicate_member",
                    "EPUB package contains duplicate member names.",
                    member=name,
                )
            seen.add(name)
            if info.flag_bits & 0x1:
                _fail(
                    "epub.package.encrypted_member",
                    "Encrypted EPUB members are not supported.",
                    member=name,
                )
            if _is_symlink(info.create_system, info.external_attr):
                _fail(
                    "epub.package.symlink_member",
                    "Symbolic-link EPUB members are not supported.",
                    member=name,
                )
            if info.file_size > limits.max_member_uncompressed_bytes:
                _fail(
                    "epub.package.member_too_large",
                    "EPUB member exceeds the configured size limit.",
                    member=name,
                    size=info.file_size,
                    limit=limits.max_member_uncompressed_bytes,
                )
            if name.lower().endswith(_XML_SUFFIXES) and (
                info.file_size > limits.max_xml_member_bytes
            ):
                _fail(
                    "epub.package.xml_member_too_large",
                    "EPUB XML member exceeds the configured XML size limit.",
                    member=name,
                    size=info.file_size,
                    limit=limits.max_xml_member_bytes,
                )
            total += info.file_size
            if total > limits.max_total_uncompressed_bytes:
                _fail(
                    "epub.package.too_large",
                    "EPUB package exceeds the configured total size limit.",
                    size=total,
                    limit=limits.max_total_uncompressed_bytes,
                )
            if info.file_size:
                if info.compress_size == 0:
                    _fail(
                        "epub.package.compression_ratio_too_high",
                        "EPUB member has an unsafe compression ratio.",
                        member=name,
                    )
                ratio = info.file_size / info.compress_size
                if ratio > limits.max_compression_ratio:
                    _fail(
                        "epub.package.compression_ratio_too_high",
                        "EPUB member exceeds the configured compression-ratio limit.",
                        member=name,
                        ratio=ratio,
                        limit=limits.max_compression_ratio,
                    )
            try:
                content = archive.read(info)
            except (BadZipFile, RuntimeError, ValueError) as exc:
                raise EpubParseError(
                    "Unable to read EPUB package member.",
                    reason="epub.package.member_read_failed",
                    details={"member": name},
                ) from exc
            entries.append(
                EpubPackageEntry(
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
                )
            )

        try:
            mimetype = archive.read(first)
        except (BadZipFile, RuntimeError, ValueError) as exc:
            raise EpubParseError(
                "Unable to read EPUB OCF mimetype member.",
                reason="epub.ocf.mimetype_read_failed",
            ) from exc
        if mimetype != _EPUB_MIMETYPE:
            _fail(
                "epub.ocf.mimetype_payload",
                "EPUB OCF mimetype payload is invalid.",
                actual=mimetype,
            )

        return EpubPackageSnapshot(
            source_sha256=sha256(source).hexdigest(),
            source_size=len(source),
            entries=tuple(entries),
            archive_comment=archive.comment,
        )


def read_epub_member(source: bytes, member_name: str) -> bytes:
    try:
        with ZipFile(BytesIO(source), "r") as archive:
            return archive.read(member_name)
    except (BadZipFile, KeyError, RuntimeError, ValueError) as exc:
        raise EpubParseError(
            "Unable to read required EPUB member.",
            reason="epub.package.required_member_read_failed",
            details={"member": member_name},
        ) from exc
