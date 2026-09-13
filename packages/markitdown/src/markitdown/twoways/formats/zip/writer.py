from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from hashlib import sha256
from io import BytesIO
from typing import BinaryIO
from zipfile import BadZipFile, ZipFile

from ..._errors import (
    PatchPreconditionError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from ..._results import FidelityEvidence, FidelityReport, FidelityStatus, WriterResult
from ...capabilities import CapabilityState, capabilities_for_node
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.serialization import validate_document
from .limits import ZipRecursiveLimits
from .package import build_zip_candidate, read_zip_member, snapshot_zip_package
from .parser import parse_zip_source
from .routing import ZipRoutedEdit, resolve_zip_edit
from .verification import verify_zip_candidate


def _read_source_bytes(source_stream: BinaryIO) -> bytes:
    source = source_stream.read()
    if not isinstance(source, bytes):
        raise TypeError("ZIP source stream must produce bytes")
    return source


def _source_mismatch(reason: str, *, expected: object, actual: object) -> None:
    raise SourcePackageMismatchError(
        "ZIP source does not match the DocumentIR source authority.",
        details={"reason": reason, "expected": expected, "actual": actual},
    )


def _validate_source_authority(document: DocumentIR, source: bytes) -> None:
    descriptor = document.source
    if descriptor is None:
        _source_mismatch("missing_source_descriptor", expected="zip", actual=None)
    assert descriptor is not None
    if descriptor.format != "zip":
        _source_mismatch("source_format", expected="zip", actual=descriptor.format)
    digest = sha256(source).hexdigest()
    if digest != descriptor.sha256:
        _source_mismatch("source_sha256", expected=descriptor.sha256, actual=digest)
    if len(source) != descriptor.size_bytes:
        _source_mismatch(
            "source_size",
            expected=descriptor.size_bytes,
            actual=len(source),
        )


def _validate_edit_set(edits: Sequence[EditOperation]) -> None:
    operation_counts = Counter(edit.operation_id for edit in edits)
    duplicate_operation_ids = sorted(
        operation_id
        for operation_id, count in operation_counts.items()
        if count > 1
    )
    if duplicate_operation_ids:
        raise UnsupportedEditError(
            "ZIP transaction contains contradictory operation identifiers.",
            details={
                "reason": "zip.edit.duplicate_operation_id",
                "operation_ids": duplicate_operation_ids,
            },
        )

    targets = [edit.target_node_id for edit in edits if edit.target_node_id is not None]
    target_counts = Counter(targets)
    duplicate_targets = sorted(
        target for target, count in target_counts.items() if count > 1
    )
    if duplicate_targets:
        raise UnsupportedEditError(
            "ZIP transaction contains multiple edits for one logical target.",
            details={
                "reason": "zip.edit.duplicate_logical_target",
                "target_node_ids": duplicate_targets,
            },
        )


def _read_chain_member(source: bytes, chain: tuple[str, ...]) -> bytes:
    current = source
    for part in chain:
        try:
            with ZipFile(BytesIO(current), "r") as archive:
                current = archive.read(part)
        except (BadZipFile, KeyError, RuntimeError, ValueError) as exc:
            raise PatchPreconditionError(
                "Unable to resolve ZIP member chain against fresh source bytes.",
                details={"reason": "zip.member_chain.read", "member_chain": chain},
            ) from exc
    return current


def _read_inner(adapter_key: str, source: bytes, filename: str) -> DocumentIR:
    stream = BytesIO(source)
    if adapter_key == "json":
        from ..json import read_json_ir

        return read_json_ir(stream, filename=filename)
    if adapter_key == "epub":
        from ..epub import read_epub_ir

        return read_epub_ir(stream, filename=filename)
    if adapter_key == "docx":
        from ..docx import read_docx_ir

        return read_docx_ir(stream)
    if adapter_key == "pptx":
        from ..pptx import read_pptx_ir

        return read_pptx_ir(stream)
    if adapter_key == "xlsx":
        from ..xlsx import read_xlsx_ir

        return read_xlsx_ir(stream)
    raise UnsupportedEditError(
        "ZIP nested writer has no typed adapter for the requested member.",
        details={"reason": "zip.writer.adapter", "adapter_key": adapter_key},
    )


def _patch_inner(
    adapter_key: str,
    document: DocumentIR,
    source: bytes,
    edits: tuple[EditOperation, ...],
) -> bytes:
    output = BytesIO()
    source_stream = BytesIO(source)
    if adapter_key == "json":
        from ..json import patch_json

        patch_json(document, source_stream, output, edits=edits)
    elif adapter_key == "epub":
        from ..epub import patch_epub

        patch_epub(document, source_stream, output, edits=edits)
    elif adapter_key == "docx":
        from ..docx import patch_docx

        patch_docx(document, source_stream, output, edits=edits)
    elif adapter_key == "pptx":
        from ..pptx import patch_pptx

        patch_pptx(document, source_stream, output, edits=edits)
    elif adapter_key == "xlsx":
        from ..xlsx import patch_xlsx

        patch_xlsx(document, source_stream, output, edits=edits)
    else:
        raise UnsupportedEditError(
            "ZIP nested writer has no typed patch adapter for the requested member.",
            details={"reason": "zip.writer.adapter", "adapter_key": adapter_key},
        )
    return output.getvalue()


def _prepare_terminal_replacement(
    root_source: bytes,
    chain: tuple[str, ...],
    routed: tuple[ZipRoutedEdit, ...],
) -> bytes:
    adapter_keys = {item.adapter_key for item in routed}
    if len(adapter_keys) != 1:
        raise PatchPreconditionError(
            "ZIP terminal member was routed to multiple typed adapters.",
            details={
                "reason": "zip.writer.adapter_conflict",
                "member_chain": chain,
                "adapter_keys": tuple(sorted(adapter_keys)),
            },
        )
    adapter_key = next(iter(adapter_keys))
    source = _read_chain_member(root_source, chain)
    fresh = _read_inner(adapter_key, source, chain[-1])

    inner_edits: list[EditOperation] = []
    for item in routed:
        target_id = item.inner_operation.target_node_id
        if target_id is None or target_id not in fresh.nodes:
            raise PatchPreconditionError(
                "ZIP nested edit target no longer exists in the fresh inner document.",
                details={
                    "reason": "zip.writer.inner_target_missing",
                    "operation_id": item.operation.operation_id,
                    "member_chain": chain,
                    "target_node_id": target_id,
                },
            )
        target = fresh.nodes[target_id]
        capability = capabilities_for_node(target).for_operation(
            item.inner_operation.type
        )
        if capability.state is not CapabilityState.WRITABLE:
            raise UnsupportedEditError(
                "ZIP fresh inner target is read-only for the requested operation.",
                details={
                    "reason": "zip.writer.inner_target_read_only",
                    "operation_id": item.operation.operation_id,
                    "member_chain": chain,
                    "operation_type": item.inner_operation.type,
                },
            )
        inner_edits.append(item.inner_operation)

    return _patch_inner(adapter_key, fresh, source, tuple(inner_edits))


def _needs_descendant(
    prefix: tuple[str, ...],
    terminal_replacements: dict[tuple[str, ...], bytes],
) -> bool:
    return any(
        len(chain) > len(prefix) and chain[: len(prefix)] == prefix
        for chain in terminal_replacements
    )


def _rebuild_archive(
    source: bytes,
    *,
    prefix: tuple[str, ...],
    terminal_replacements: dict[tuple[str, ...], bytes],
    limits: ZipRecursiveLimits,
) -> bytes:
    snapshot = snapshot_zip_package(source, limits=limits)
    replacements: dict[str, bytes] = {}
    for entry in snapshot.entries:
        chain = prefix + (entry.name,)
        direct = terminal_replacements.get(chain)
        descendant = _needs_descendant(chain, terminal_replacements)
        if direct is not None and descendant:
            raise PatchPreconditionError(
                "ZIP transaction targets both a member and its descendant.",
                details={
                    "reason": "zip.writer.overlapping_member_chains",
                    "member_chain": chain,
                },
            )
        if direct is not None:
            replacements[entry.name] = direct
            continue
        if descendant:
            if entry.is_directory:
                raise PatchPreconditionError(
                    "ZIP descendant edit traverses a directory entry.",
                    details={
                        "reason": "zip.writer.directory_traversal",
                        "member_chain": chain,
                    },
                )
            child = read_zip_member(source, entry.name)
            replacements[entry.name] = _rebuild_archive(
                child,
                prefix=chain,
                terminal_replacements=terminal_replacements,
                limits=limits,
            )
    if not replacements:
        return source
    return build_zip_candidate(
        snapshot,
        source,
        replacements=replacements,
        limits=limits,
    )


def _passed(check_code: str, description: str) -> FidelityEvidence:
    return FidelityEvidence(
        check_code=check_code,
        status=FidelityStatus.PASSED,
        description=description,
    )


def _exact_result(source: bytes) -> WriterResult:
    return WriterResult(
        format="zip",
        mode="patch",
        bytes_written=len(source),
        fidelity=FidelityReport(
            claimed_tier="exact-preserve",
            evidence=(
                _passed(
                    "zip.source_authority",
                    "Root ZIP source digest and size matched the DocumentIR authority.",
                ),
                _passed(
                    "zip.zero_edit_identity",
                    "Zero-edit transaction reused the exact root ZIP source bytes.",
                ),
                _passed(
                    "zip.global_budget_recheck",
                    "Fresh recursive parse satisfied the configured global budgets.",
                ),
            ),
        ),
    )


def _mutation_result(candidate: bytes) -> WriterResult:
    evidence = (
        _passed(
            "zip.source_authority",
            "Root ZIP source digest and size matched the DocumentIR authority.",
        ),
        _passed(
            "zip.member_chain_authority",
            "Every routed edit matched fresh recursive member-chain evidence.",
        ),
        _passed(
            "zip.inner_writer_verification",
            "Existing typed inner writers produced all terminal replacements.",
        ),
        _passed(
            "zip.ordered_inventory",
            "Recursive verification preserved ordered archive inventories.",
        ),
        _passed(
            "zip.untouched_member_content",
            "Untouched recursive member content remained byte-identical after expansion.",
        ),
        _passed(
            "zip.recursive_candidate_reread",
            "The complete root candidate passed a fresh recursive parse and verification.",
        ),
        _passed(
            "zip.global_budget_recheck",
            "The final recursive candidate satisfied the configured global budgets.",
        ),
    )
    return WriterResult(
        format="zip",
        mode="patch",
        bytes_written=len(candidate),
        fidelity=FidelityReport(claimed_tier="high", evidence=evidence),
    )


def patch_zip(
    document: DocumentIR,
    source_stream: BinaryIO,
    destination: BinaryIO,
    *,
    edits: Sequence[EditOperation],
    limits: ZipRecursiveLimits | None = None,
) -> WriterResult:
    validate_document(document)
    source = _read_source_bytes(source_stream)
    _validate_source_authority(document, source)
    limits = limits or ZipRecursiveLimits()
    parsed = parse_zip_source(
        source,
        filename=document.source.filename if document.source is not None else None,
        limits=limits,
    )
    edit_tuple = tuple(edits)
    _validate_edit_set(edit_tuple)

    if not edit_tuple:
        destination.write(source)
        return _exact_result(source)

    routed = tuple(resolve_zip_edit(document, parsed, edit) for edit in edit_tuple)
    grouped: dict[tuple[str, ...], list[ZipRoutedEdit]] = defaultdict(list)
    for item in routed:
        grouped[item.member_chain].append(item)

    terminal_replacements: dict[tuple[str, ...], bytes] = {}
    for chain in sorted(grouped):
        terminal_replacements[chain] = _prepare_terminal_replacement(
            source,
            chain,
            tuple(grouped[chain]),
        )

    candidate = _rebuild_archive(
        source,
        prefix=(),
        terminal_replacements=terminal_replacements,
        limits=limits,
    )
    verify_zip_candidate(
        parsed,
        candidate,
        requested=routed,
        touched_chains=terminal_replacements,
        limits=limits,
    )

    destination.write(candidate)
    return _mutation_result(candidate)
