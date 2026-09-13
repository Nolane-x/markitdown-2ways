from __future__ import annotations

from dataclasses import dataclass, replace

from ..._errors import (
    PatchPreconditionError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from ...capabilities import CapabilityState, capabilities_for_node
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.nodes import Node
from ...ir.semantics import validate_edit_preconditions
from .model import ParsedZipSource


@dataclass(frozen=True)
class ZipRoutedEdit:
    operation: EditOperation
    member_chain: tuple[str, ...]
    adapter_key: str
    inner_operation: EditOperation
    inner_path: str | None = None
    terminal_sha256: str | None = None
    terminal_size: int | None = None


def _source_mismatch(reason: str, *, expected: object, actual: object) -> None:
    raise SourcePackageMismatchError(
        "ZIP source does not match the DocumentIR source authority.",
        details={"reason": reason, "expected": expected, "actual": actual},
    )


def _validate_root_authority(document: DocumentIR, parsed: ParsedZipSource) -> None:
    source = document.source
    if source is None:
        _source_mismatch("missing_source_descriptor", expected="zip", actual=None)
    assert source is not None
    if source.format != "zip":
        _source_mismatch("source_format", expected="zip", actual=source.format)
    if source.sha256 != parsed.snapshot.source_sha256:
        _source_mismatch(
            "source_sha256",
            expected=source.sha256,
            actual=parsed.snapshot.source_sha256,
        )
    if source.size_bytes != parsed.snapshot.source_size:
        _source_mismatch(
            "source_size",
            expected=source.size_bytes,
            actual=parsed.snapshot.source_size,
        )


def _fail(reason: str, *, operation_id: str, **details: object) -> None:
    raise PatchPreconditionError(
        "ZIP edit routing evidence no longer matches the source.",
        details={"reason": reason, "operation_id": operation_id, **details},
    )


def _structural_member_nodes(document: DocumentIR) -> dict[tuple[str, ...], Node]:
    result: dict[tuple[str, ...], Node] = {}
    for node in document.nodes.values():
        if node.semantic_role != "zip-member":
            continue
        chain = node.metadata.get("zip.member_chain")
        if (
            not isinstance(chain, tuple)
            or not chain
            or not all(isinstance(part, str) and part for part in chain)
        ):
            continue
        if chain in result:
            raise PatchPreconditionError(
                "ZIP member-chain ownership is ambiguous in the DocumentIR.",
                details={"reason": "duplicate_member_chain", "member_chain": chain},
            )
        result[chain] = node
    return result


def _validate_chain_evidence(
    document: DocumentIR,
    parsed: ParsedZipSource,
    chain: tuple[str, ...],
    *,
    operation_id: str,
) -> None:
    structural = _structural_member_nodes(document)
    fresh = parsed.member_by_chain
    for depth in range(1, len(chain) + 1):
        prefix = chain[:depth]
        recorded = structural.get(prefix)
        actual = fresh.get(prefix)
        if recorded is None or actual is None:
            _fail(
                "member_chain_missing",
                operation_id=operation_id,
                member_chain=prefix,
            )
        assert recorded is not None and actual is not None
        recorded_digest = recorded.metadata.get("zip.member_sha256")
        recorded_size = recorded.metadata.get("zip.member_size")
        if recorded_digest != actual.entry.uncompressed_sha256:
            _fail(
                "member_sha256",
                operation_id=operation_id,
                member_chain=prefix,
                expected=recorded_digest,
                actual=actual.entry.uncompressed_sha256,
            )
        if recorded_size != actual.entry.uncompressed_size:
            _fail(
                "member_size",
                operation_id=operation_id,
                member_chain=prefix,
                expected=recorded_size,
                actual=actual.entry.uncompressed_size,
            )


def resolve_zip_edit(
    document: DocumentIR,
    parsed: ParsedZipSource,
    edit: EditOperation,
) -> ZipRoutedEdit:
    _validate_root_authority(document, parsed)
    if edit.target_node_id is None or edit.target_node_id not in document.nodes:
        _fail(
            "target_missing",
            operation_id=edit.operation_id,
            target_node_id=edit.target_node_id,
        )
    target = document.nodes[edit.target_node_id]
    validate_edit_preconditions(document, target, edit, format_label="zip")

    chain = target.metadata.get("zip.member_chain")
    if (
        not isinstance(chain, tuple)
        or not chain
        or not all(isinstance(part, str) and part for part in chain)
    ):
        _fail(
            "member_chain_metadata",
            operation_id=edit.operation_id,
            target_node_id=target.node_id,
        )
    adapter_key = target.metadata.get("zip.adapter_key")
    if not isinstance(adapter_key, str) or not adapter_key or adapter_key == "zip":
        _fail(
            "adapter_key_metadata",
            operation_id=edit.operation_id,
            target_node_id=target.node_id,
            adapter_key=adapter_key,
        )
    inner_node_id = target.metadata.get("zip.inner_node_id")
    if not isinstance(inner_node_id, str) or not inner_node_id:
        _fail(
            "inner_node_id_metadata",
            operation_id=edit.operation_id,
            target_node_id=target.node_id,
        )

    _validate_chain_evidence(
        document,
        parsed,
        chain,
        operation_id=edit.operation_id,
    )
    terminal = parsed.member_by_chain.get(chain)
    if terminal is None:
        _fail(
            "terminal_missing",
            operation_id=edit.operation_id,
            member_chain=chain,
        )
    assert terminal is not None
    classification = terminal.classification
    if classification.state != "typed" or classification.adapter_key != adapter_key:
        _fail(
            "adapter_reclassification",
            operation_id=edit.operation_id,
            member_chain=chain,
            expected=adapter_key,
            actual=classification.adapter_key,
            classification_state=classification.state,
        )

    expected_digest = target.metadata.get("zip.inner_source_sha256")
    expected_size = target.metadata.get("zip.inner_source_size")
    if expected_digest != terminal.entry.uncompressed_sha256:
        _fail(
            "inner_source_sha256",
            operation_id=edit.operation_id,
            member_chain=chain,
            expected=expected_digest,
            actual=terminal.entry.uncompressed_sha256,
        )
    if expected_size != terminal.entry.uncompressed_size:
        _fail(
            "inner_source_size",
            operation_id=edit.operation_id,
            member_chain=chain,
            expected=expected_size,
            actual=terminal.entry.uncompressed_size,
        )

    capability = capabilities_for_node(target).for_operation(edit.type)
    if capability.state is not CapabilityState.WRITABLE:
        raise UnsupportedEditError(
            "ZIP nested target is read-only for the requested operation.",
            details={
                "reason": "zip.target.read_only",
                "operation_id": edit.operation_id,
                "target_node_id": target.node_id,
                "operation_type": edit.type,
                "member_chain": chain,
                "adapter_key": adapter_key,
            },
        )

    inner_path = target.metadata.get("json.pointer")
    return ZipRoutedEdit(
        operation=edit,
        member_chain=chain,
        adapter_key=adapter_key,
        inner_operation=replace(edit, target_node_id=inner_node_id),
        inner_path=inner_path if isinstance(inner_path, str) else None,
        terminal_sha256=terminal.entry.uncompressed_sha256,
        terminal_size=terminal.entry.uncompressed_size,
    )
