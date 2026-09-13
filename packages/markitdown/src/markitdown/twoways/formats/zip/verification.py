from __future__ import annotations

from collections.abc import Collection, Sequence
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from ..._errors import RoundTripVerificationError
from ...ir.document import DocumentIR
from .limits import ZipRecursiveLimits
from .model import ParsedZipSource, ZipPackageEntry
from .parser import parse_zip_source
from .routing import ZipRoutedEdit


def _fail(reason: str, **details: object) -> None:
    raise RoundTripVerificationError(
        "Recursive ZIP candidate verification failed.",
        details={"reason": reason, **details},
    )


def _entry_metadata(entry: ZipPackageEntry) -> tuple[object, ...]:
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
        entry.is_directory,
    )


def _is_touched_prefix(
    chain: tuple[str, ...],
    touched: frozenset[tuple[str, ...]],
) -> bool:
    return any(
        len(chain) <= len(target) and target[: len(chain)] == chain for target in touched
    )


def _compare_archive(
    original: ParsedZipSource,
    candidate: ParsedZipSource,
    *,
    touched: frozenset[tuple[str, ...]],
) -> None:
    if original.snapshot.archive_comment != candidate.snapshot.archive_comment:
        _fail(
            "archive_comment",
            depth=original.depth,
            expected=original.snapshot.archive_comment,
            actual=candidate.snapshot.archive_comment,
        )
    original_names = tuple(entry.name for entry in original.snapshot.entries)
    candidate_names = tuple(entry.name for entry in candidate.snapshot.entries)
    if original_names != candidate_names:
        _fail(
            "ordered_inventory",
            depth=original.depth,
            expected=original_names,
            actual=candidate_names,
        )

    candidate_members = {member.chain: member for member in candidate.members}
    for member in original.members:
        other = candidate_members.get(member.chain)
        if other is None:
            _fail("missing_member", member_chain=member.chain)
        assert other is not None
        if _entry_metadata(member.entry) != _entry_metadata(other.entry):
            _fail(
                "member_metadata",
                member_chain=member.chain,
                expected=_entry_metadata(member.entry),
                actual=_entry_metadata(other.entry),
            )
        touched_prefix = _is_touched_prefix(member.chain, touched)
        if not touched_prefix:
            if member.entry.uncompressed_sha256 != other.entry.uncompressed_sha256:
                _fail(
                    "untouched_member_sha256",
                    member_chain=member.chain,
                    expected=member.entry.uncompressed_sha256,
                    actual=other.entry.uncompressed_sha256,
                )
            if member.entry.uncompressed_size != other.entry.uncompressed_size:
                _fail(
                    "untouched_member_size",
                    member_chain=member.chain,
                    expected=member.entry.uncompressed_size,
                    actual=other.entry.uncompressed_size,
                )
        if member.nested_archive is not None:
            if other.nested_archive is None:
                _fail("nested_archive_missing", member_chain=member.chain)
            assert other.nested_archive is not None
            _compare_archive(
                member.nested_archive,
                other.nested_archive,
                touched=touched,
            )


def _read_chain_member(source: bytes, chain: tuple[str, ...]) -> bytes:
    current = source
    for part in chain:
        try:
            with ZipFile(BytesIO(current), "r") as archive:
                current = archive.read(part)
        except (BadZipFile, KeyError, RuntimeError, ValueError) as exc:
            raise RoundTripVerificationError(
                "Unable to read requested member chain from ZIP candidate.",
                details={"reason": "member_chain_read", "member_chain": chain},
            ) from exc
    return current


def _json_node(document: DocumentIR, pointer: str):
    matches = [
        node
        for node in document.nodes.values()
        if node.metadata.get("json.pointer") == pointer
    ]
    if len(matches) != 1:
        _fail("json_pointer_ownership", pointer=pointer, matches=len(matches))
    return matches[0]


def _verify_requested_semantics(candidate: bytes, routed: ZipRoutedEdit) -> None:
    if routed.adapter_key != "json":
        return
    if routed.inner_path is None:
        _fail(
            "json_pointer_missing",
            operation_id=routed.operation.operation_id,
            member_chain=routed.member_chain,
        )
    from ..json import read_json_ir

    inner_bytes = _read_chain_member(candidate, routed.member_chain)
    inner = read_json_ir(BytesIO(inner_bytes), filename=routed.member_chain[-1])
    node = _json_node(inner, routed.inner_path)
    expected = routed.inner_operation.payload.get("value")
    kind = node.metadata.get("json.kind")
    if kind == "number":
        raw = node.metadata.get("json.raw")
        try:
            actual: object = float(raw) if "." in str(raw) else int(str(raw))
        except ValueError:
            actual = raw
    elif kind == "null":
        actual = None
    else:
        payload = node.payload
        actual = payload.get("value") if isinstance(payload, dict) else None
    if actual != expected:
        _fail(
            "requested_semantics",
            operation_id=routed.operation.operation_id,
            member_chain=routed.member_chain,
            expected=expected,
            actual=actual,
        )


def verify_zip_candidate(
    original: ParsedZipSource,
    candidate: bytes,
    *,
    requested: Sequence[ZipRoutedEdit],
    touched_chains: Collection[tuple[str, ...]],
    limits: ZipRecursiveLimits | None = None,
) -> ParsedZipSource:
    touched = frozenset(tuple(chain) for chain in touched_chains)
    requested_chains = {item.member_chain for item in requested}
    if not requested_chains.issubset(touched):
        _fail(
            "requested_chain_not_touched",
            requested=tuple(sorted(requested_chains)),
            touched=tuple(sorted(touched)),
        )

    parsed = parse_zip_source(candidate, limits=limits)
    _compare_archive(original, parsed, touched=touched)

    for item in requested:
        fresh_member = parsed.member_by_chain.get(item.member_chain)
        if fresh_member is None:
            _fail(
                "requested_member_missing",
                operation_id=item.operation.operation_id,
                member_chain=item.member_chain,
            )
        assert fresh_member is not None
        if (
            fresh_member.classification.state != "typed"
            or fresh_member.classification.adapter_key != item.adapter_key
        ):
            _fail(
                "requested_adapter_drift",
                operation_id=item.operation.operation_id,
                member_chain=item.member_chain,
                expected=item.adapter_key,
                actual=fresh_member.classification.adapter_key,
            )
        _verify_requested_semantics(candidate, item)

    return parsed
