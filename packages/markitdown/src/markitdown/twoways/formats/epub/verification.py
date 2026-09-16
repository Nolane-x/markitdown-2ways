from __future__ import annotations

from collections.abc import Mapping

from ..._errors import RoundTripVerificationError
from .limits import EpubPackageLimits
from .model import EpubParseError, ParsedEpubSource
from .parser import parse_epub_source


OwnerKey = tuple[str, str]


def _fail(reason: str, *, expected: object = None, actual: object = None) -> None:
    details = {"reason": reason}
    if expected is not None:
        details["expected"] = expected
    if actual is not None:
        details["actual"] = actual
    raise RoundTripVerificationError(
        "EPUB candidate failed publication-preservation verification.",
        details=details,
    )


def _entry_metadata(entry) -> tuple[object, ...]:
    return (
        entry.name,
        entry.compression_method,
        entry.flag_bits,
        entry.date_time,
        entry.comment,
        entry.extra,
        entry.create_system,
        entry.create_version,
        entry.extract_version,
        entry.internal_attr,
        entry.external_attr,
    )


def _owner_map(parsed: ParsedEpubSource) -> dict[OwnerKey, tuple[str, str, str, str]]:
    result: dict[OwnerKey, tuple[str, str, str, str]] = {}
    for owner in parsed.metadata_owners:
        key = (owner.member_path, owner.xml_path)
        if key in result:
            _fail("epub.candidate.duplicate_owner", actual=key)
        result[key] = ("metadata", owner.name, owner.value, owner.raw_digest)
    for owner in parsed.xhtml_text_owners:
        key = (owner.member_path, owner.xml_path)
        if key in result:
            _fail("epub.candidate.duplicate_owner", actual=key)
        result[key] = (
            "xhtml",
            owner.manifest_item_id,
            owner.value,
            owner.raw_digest,
        )
    return result


def verify_epub_candidate(
    original: ParsedEpubSource,
    candidate: bytes,
    *,
    requested: Mapping[OwnerKey, str],
    touched_members: frozenset[str],
    limits: EpubPackageLimits | None = None,
) -> ParsedEpubSource:
    try:
        reread = parse_epub_source(candidate, limits=limits)
    except (EpubParseError, TypeError, ValueError) as exc:
        raise RoundTripVerificationError(
            "EPUB candidate could not be re-read strictly.",
            details={"reason": "epub.candidate_reread_failed"},
        ) from exc

    requested = dict(requested)
    requested_members = frozenset(member for member, _ in requested)
    if touched_members != requested_members:
        _fail(
            "epub.candidate.touched_member_set",
            expected=tuple(sorted(requested_members)),
            actual=tuple(sorted(touched_members)),
        )

    before_entries = original.package.entries
    after_entries = reread.package.entries
    before_names = tuple(entry.name for entry in before_entries)
    after_names = tuple(entry.name for entry in after_entries)
    if after_names != before_names:
        _fail(
            "epub.candidate.member_inventory",
            expected=before_names,
            actual=after_names,
        )
    if reread.package.archive_comment != original.package.archive_comment:
        _fail(
            "epub.candidate.archive_comment",
            expected=original.package.archive_comment,
            actual=reread.package.archive_comment,
        )

    after_by_name = reread.package.entry_by_name
    for before in before_entries:
        after = after_by_name[before.name]
        if _entry_metadata(after) != _entry_metadata(before):
            _fail(
                "epub.candidate.member_metadata",
                expected=_entry_metadata(before),
                actual=_entry_metadata(after),
            )
        if (
            before.name not in touched_members
            and after.uncompressed_sha256 != before.uncompressed_sha256
        ):
            _fail(
                "epub.candidate.untouched_member_content",
                expected=before.uncompressed_sha256,
                actual=after.uncompressed_sha256,
            )

    protected = {"mimetype", "META-INF/container.xml"}
    for name in protected:
        before = original.package.entry_by_name.get(name)
        after = after_by_name.get(name)
        if before is None or after is None:
            _fail("epub.candidate.protected_member_missing", actual=name)
        if after.uncompressed_sha256 != before.uncompressed_sha256:
            _fail(
                "epub.candidate.protected_member_content",
                expected=before.uncompressed_sha256,
                actual=after.uncompressed_sha256,
            )

    graph_checks = (
        ("rootfiles", original.rootfiles, reread.rootfiles),
        ("package_path", original.package_path, reread.package_path),
        ("package_version", original.package_version, reread.package_version),
        (
            "unique_identifier_id",
            original.unique_identifier_id,
            reread.unique_identifier_id,
        ),
        (
            "unique_identifier_value",
            original.unique_identifier_value,
            reread.unique_identifier_value,
        ),
        ("manifest", original.manifest, reread.manifest),
        ("spine", original.spine, reread.spine),
    )
    for label, expected, actual in graph_checks:
        if actual != expected:
            _fail(
                f"epub.candidate.{label}",
                expected=expected,
                actual=actual,
            )
    if not reread.writable_version:
        _fail("epub.candidate.writable_version", expected=True, actual=False)

    before_owners = _owner_map(original)
    after_owners = _owner_map(reread)
    if set(after_owners) != set(before_owners):
        _fail(
            "epub.candidate.owner_inventory",
            expected=tuple(sorted(before_owners)),
            actual=tuple(sorted(after_owners)),
        )
    unknown_requested = sorted(set(requested) - set(before_owners))
    if unknown_requested:
        _fail("epub.candidate.unknown_requested_owner", actual=tuple(unknown_requested))

    for key, before in before_owners.items():
        after = after_owners[key]
        if after[:2] != before[:2]:
            _fail(
                "epub.candidate.owner_identity",
                expected=before[:2],
                actual=after[:2],
            )
        if key in requested:
            expected_value = requested[key]
            if after[2] != expected_value:
                _fail(
                    "epub.candidate.requested_value",
                    expected=expected_value,
                    actual=after[2],
                )
            continue
        if after[2] != before[2]:
            _fail(
                "epub.candidate.unrequested_value",
                expected=before[2],
                actual=after[2],
            )
        if key[0] in touched_members and after[3] != before[3]:
            _fail(
                "epub.candidate.unrequested_owner_raw",
                expected=before[3],
                actual=after[3],
            )

    return reread
