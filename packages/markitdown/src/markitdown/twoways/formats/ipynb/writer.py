from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
from io import BytesIO
from typing import BinaryIO

from ..._errors import (
    PatchPreconditionError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from ..._results import (
    FidelityEvidence,
    FidelityReport,
    FidelityStatus,
    WriterResult,
)
from ...capabilities import CapabilityState, capabilities_for_node
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.nodes import Node, TextPayload
from ...ir.semantics import validate_edit_preconditions
from ...ir.serialization import canonical_json_digest, validate_document
from ..json.writer import patch_json
from .lowering import lower_ipynb_cell_sources
from .model import ParsedIpynbSource
from .parser import parse_ipynb_source
from .reader import read_ipynb_ir
from .verification import verify_ipynb_candidate


def _read_source_bytes(source_stream: BinaryIO) -> bytes:
    source = source_stream.read()
    if not isinstance(source, bytes):
        raise TypeError("IPYNB source stream must produce bytes")
    return source


def _source_mismatch(reason: str, *, expected: object, actual: object) -> None:
    raise SourcePackageMismatchError(
        f"IPYNB source does not match the DocumentIR source authority ({reason}).",
        details={"reason": reason, "expected": expected, "actual": actual},
    )


def _validate_source_authority(document: DocumentIR, source: bytes) -> None:
    descriptor = document.source
    if descriptor is None:
        _source_mismatch("missing_source_descriptor", expected="ipynb", actual=None)
    assert descriptor is not None
    if descriptor.format != "ipynb":
        _source_mismatch("source_format", expected="ipynb", actual=descriptor.format)
    digest = sha256(source).hexdigest()
    if digest != descriptor.sha256:
        _source_mismatch("source_sha256", expected=descriptor.sha256, actual=digest)
    if len(source) != descriptor.size_bytes:
        _source_mismatch(
            "source_size",
            expected=descriptor.size_bytes,
            actual=len(source),
        )


def _root_node(document: DocumentIR) -> Node:
    if len(document.root_node_ids) != 1:
        raise PatchPreconditionError(
            "IPYNB DocumentIR must expose exactly one notebook root.",
            details={"reason": "ipynb.root_count"},
        )
    root_id = document.root_node_ids[0]
    root = document.nodes.get(root_id)
    if root is None:
        raise PatchPreconditionError(
            "IPYNB notebook root is missing.",
            details={"reason": "ipynb.root_missing"},
        )
    return root


def _recorded_encoding(document: DocumentIR) -> str:
    encoding = _root_node(document).metadata.get("ipynb.encoding")
    if not isinstance(encoding, str) or not encoding:
        raise PatchPreconditionError(
            "IPYNB source encoding evidence is missing.",
            details={"reason": "ipynb.encoding_evidence"},
        )
    return encoding


def _validate_fresh_native_evidence(
    document: DocumentIR,
    source: bytes,
    *,
    encoding: str,
) -> DocumentIR:
    descriptor = document.source
    assert descriptor is not None
    try:
        fresh = read_ipynb_ir(
            BytesIO(source),
            filename=descriptor.filename,
            mimetype=descriptor.mimetype,
            encoding=encoding,
        )
    except (TypeError, ValueError) as exc:
        raise PatchPreconditionError(
            "IPYNB source can no longer be re-read under recorded authority.",
            details={"reason": "ipynb.native_reread"},
        ) from exc

    expected = canonical_json_digest(fresh)
    actual = canonical_json_digest(document)
    if actual != expected:
        raise PatchPreconditionError(
            "IPYNB native evidence no longer matches the exact source.",
            details={
                "reason": "ipynb.native_evidence_mismatch",
                "expected": expected,
                "actual": actual,
            },
        )
    return fresh


def _source_node(document: DocumentIR, edit: EditOperation) -> Node:
    if edit.target_node_id is None or edit.target_node_id not in document.nodes:
        raise PatchPreconditionError(
            "IPYNB edit target does not exist in the DocumentIR.",
            details={
                "reason": "target_mismatch",
                "operation_id": edit.operation_id,
                "target_node_id": edit.target_node_id,
            },
        )
    node = document.nodes[edit.target_node_id]
    pointer = node.metadata.get("ipynb.source_pointer")
    if (
        node.kind != "text"
        or not isinstance(node.payload, TextPayload)
        or not isinstance(pointer, str)
    ):
        raise UnsupportedEditError(
            "IPYNB edit target must be a native cell-source text node.",
            details={"reason": "ipynb.target_not_cell_source"},
        )
    return node


def _preflight_edits(
    document: DocumentIR,
    edits: Sequence[EditOperation],
) -> dict[int, str]:
    requested: dict[int, str] = {}
    for edit in edits:
        if edit.type != "replace_ipynb_cell_source":
            raise UnsupportedEditError(
                "H6 IPYNB supports replace_ipynb_cell_source edits only.",
                details={
                    "reason": "ipynb.edit_type",
                    "operation_id": edit.operation_id,
                },
            )
        node = _source_node(document, edit)
        validate_edit_preconditions(document, node, edit, format_label="ipynb")

        capability = capabilities_for_node(node).for_operation(
            "replace_ipynb_cell_source"
        )
        if capability.state is not CapabilityState.WRITABLE:
            raise UnsupportedEditError(
                "IPYNB source target is read-only.",
                details={
                    "reason": capability.reason_code or "ipynb.target.read_only",
                    "node_id": node.node_id,
                },
            )
        if set(edit.payload) != {"value"}:
            raise UnsupportedEditError(
                "IPYNB source edits require exactly one 'value' payload field.",
                details={"reason": "ipynb.source.payload_shape"},
            )
        value = edit.payload["value"]
        if not isinstance(value, str):
            raise UnsupportedEditError(
                "IPYNB source replacement value must be a string.",
                details={"reason": "ipynb.source.value_type"},
            )
        index = node.metadata.get("ipynb.cell_index")
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise PatchPreconditionError(
                "IPYNB cell index evidence is invalid.",
                details={"reason": "ipynb.cell_index"},
            )
        if index in requested:
            raise UnsupportedEditError(
                "IPYNB edit set contains a duplicate cell-source target.",
                details={
                    "reason": "ipynb.source.duplicate_target",
                    "cell_index": index,
                },
            )
        if value == node.payload.text:
            raise UnsupportedEditError(
                "IPYNB cell-source edit is a semantic no-op.",
                details={
                    "reason": "ipynb.source.semantic_noop",
                    "cell_index": index,
                },
            )
        requested[index] = value
    return requested


def _zero_edit_result(bytes_written: int) -> WriterResult:
    return WriterResult(
        format="ipynb",
        mode="patch",
        bytes_written=bytes_written,
        fidelity=FidelityReport(
            claimed_tier="exact-preserve",
            evidence=(
                FidelityEvidence(
                    check_code="ipynb.source_authority",
                    status=FidelityStatus.PASSED,
                    description="Source SHA-256 and byte size matched the IPYNB authority.",
                ),
                FidelityEvidence(
                    check_code="ipynb.zero_edit_identity",
                    status=FidelityStatus.PASSED,
                    description="Zero-edit output reused the exact notebook bytes.",
                ),
            ),
        ),
    )


def _mutation_result(bytes_written: int) -> WriterResult:
    return WriterResult(
        format="ipynb",
        mode="patch",
        bytes_written=bytes_written,
        fidelity=FidelityReport(
            claimed_tier="high",
            evidence=(
                FidelityEvidence(
                    check_code="ipynb.source_authority",
                    status=FidelityStatus.PASSED,
                    description="Source SHA-256 and byte size matched the IPYNB authority.",
                ),
                FidelityEvidence(
                    check_code="ipynb.native_evidence",
                    status=FidelityStatus.PASSED,
                    description="Fresh notebook IR matched recorded native evidence before mutation.",
                ),
                FidelityEvidence(
                    check_code="ipynb.json_scalar_lowering",
                    status=FidelityStatus.PASSED,
                    description="Cell-source edits lowered only to existing H3 JSON scalar targets.",
                ),
                FidelityEvidence(
                    check_code="ipynb.untouched_bytes",
                    status=FidelityStatus.PASSED,
                    description="H3 proved all bytes outside authorized JSON scalar spans stayed exact.",
                ),
                FidelityEvidence(
                    check_code="ipynb.candidate_reread",
                    status=FidelityStatus.PASSED,
                    description="Candidate notebook passed H6 semantic and preservation verification.",
                ),
            ),
        ),
    )


def _prepare_ipynb_mutation(
    document: DocumentIR,
    source: bytes,
    edits: Sequence[EditOperation],
) -> tuple[
    ParsedIpynbSource,
    Mapping[int, str],
    DocumentIR,
    tuple[EditOperation, ...],
]:
    encoding = _recorded_encoding(document)
    _validate_fresh_native_evidence(document, source, encoding=encoding)
    requested = _preflight_edits(document, edits)
    parsed = parse_ipynb_source(source, encoding=encoding)
    shadow, lowered = lower_ipynb_cell_sources(source, parsed, requested)
    if not lowered:
        raise UnsupportedEditError(
            "IPYNB mutation produced no authorized JSON scalar changes.",
            details={"reason": "ipynb.lowering.empty"},
        )
    return parsed, requested, shadow, lowered


def patch_ipynb(
    document: DocumentIR,
    source_stream: BinaryIO,
    output: BinaryIO,
    *,
    edits: Sequence[EditOperation] = (),
) -> WriterResult:
    validate_document(document)
    source = _read_source_bytes(source_stream)
    _validate_source_authority(document, source)

    edits = tuple(edits)
    if not edits:
        output.write(source)
        return _zero_edit_result(len(source))

    original, requested, shadow, lowered = _prepare_ipynb_mutation(
        document,
        source,
        edits,
    )
    internal = BytesIO()
    patch_json(
        shadow,
        BytesIO(source),
        internal,
        edits=lowered,
    )
    candidate = internal.getvalue()
    verify_ipynb_candidate(
        original,
        candidate,
        encoding=original.representation.encoding,
        requested=requested,
    )
    output.write(candidate)
    return _mutation_result(len(candidate))
