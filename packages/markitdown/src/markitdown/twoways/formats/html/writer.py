from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from typing import BinaryIO

from ..._errors import (
    IRValidationError,
    PatchPreconditionError,
    RoundTripVerificationError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from ..._results import FidelityEvidence, FidelityReport, FidelityStatus, WriterResult
from ...capabilities import (
    CAPABILITY_METADATA_KEY,
    CapabilityState,
    capabilities_for_node,
)
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation, EditPrecondition
from ...ir.nodes import Node
from ...ir.semantics import validate_edit_preconditions
from ...ir.serialization import validate_document
from ..text.codec import encode_text_source
from ..text.model import TextRepresentation
from .lexical import parse_html_source
from .preservation import verify_untouched_bytes
from .reader import read_html_ir
from .render import render_html_attribute, render_html_text
from .verification import verify_html_candidate


def _read_source_bytes(source_stream: BinaryIO) -> bytes:
    source = source_stream.read()
    if not isinstance(source, bytes):
        raise TypeError("HTML source stream must produce bytes")
    return source


def _source_mismatch(reason: str, *, expected: object, actual: object) -> None:
    raise SourcePackageMismatchError(
        f"HTML source does not match the DocumentIR source authority ({reason}).",
        details={"reason": reason, "expected": expected, "actual": actual},
    )


def _validate_source_authority(document: DocumentIR, source: bytes) -> None:
    descriptor = document.source
    if descriptor is None:
        _source_mismatch("missing_source_descriptor", expected="html", actual=None)
    assert descriptor is not None
    if descriptor.format != "html":
        _source_mismatch("source_format", expected="html", actual=descriptor.format)
    digest = sha256(source).hexdigest()
    if digest != descriptor.sha256:
        _source_mismatch("source_sha256", expected=descriptor.sha256, actual=digest)
    if len(source) != descriptor.size_bytes:
        _source_mismatch(
            "source_size",
            expected=descriptor.size_bytes,
            actual=len(source),
        )


def _nodes_by_path(document: DocumentIR) -> dict[str, Node]:
    result: dict[str, Node] = {}
    for node in document.nodes.values():
        path = node.metadata.get("html.path")
        if not isinstance(path, str) or not path:
            raise PatchPreconditionError(
                "HTML node is missing its native ownership path.",
                details={"reason": "html.missing_path", "node_id": node.node_id},
            )
        if path in result:
            raise PatchPreconditionError(
                "HTML ownership path is ambiguous in the DocumentIR.",
                details={"reason": "html.duplicate_path", "path": path},
            )
        result[path] = node
    return result


def _root_node(document: DocumentIR) -> Node:
    if len(document.root_node_ids) != 1:
        raise PatchPreconditionError(
            "HTML DocumentIR must contain exactly one document root.",
            details={"reason": "html.root_count"},
        )
    root = document.nodes.get(document.root_node_ids[0])
    if root is None:
        raise PatchPreconditionError(
            "HTML document root is missing.",
            details={"reason": "html.root_missing"},
        )
    if root.metadata.get("html.path") != "/":
        raise PatchPreconditionError(
            "HTML document root ownership path is invalid.",
            details={"reason": "html.root_path"},
        )
    return root


def _representation(
    document: DocumentIR,
    *,
    require_writable: bool,
) -> TextRepresentation:
    root = _root_node(document)
    encoding = root.metadata.get("html.encoding")
    bom = root.metadata.get("html.bom")
    byte_roundtrip = root.metadata.get("html.byte_roundtrip")
    recovery_stable = root.metadata.get("html.recovery_stable")
    if not isinstance(encoding, str) or not isinstance(bom, str):
        raise PatchPreconditionError(
            "HTML source representation metadata is incomplete.",
            details={"reason": "html.representation_metadata"},
        )
    if not isinstance(byte_roundtrip, bool):
        raise PatchPreconditionError(
            "HTML source byte-roundtrip evidence is malformed.",
            details={"reason": "html.representation_roundtrip_metadata"},
        )
    if not isinstance(recovery_stable, bool):
        raise PatchPreconditionError(
            "HTML recovery-stability evidence is malformed.",
            details={"reason": "html.recovery_metadata"},
        )
    if require_writable and not recovery_stable:
        raise UnsupportedEditError(
            "HTML recovery-sensitive source is read-only.",
            details={
                "reason": root.metadata.get("html.recovery_reason")
                or "html.recovery.unproven"
            },
        )
    if require_writable and not byte_roundtrip:
        raise UnsupportedEditError(
            "HTML source encoding is not byte-roundtrippable.",
            details={"reason": "html.encoding.not_roundtrippable"},
        )
    return TextRepresentation(
        encoding=encoding,
        bom=bom,
        newline="mixed",
        byte_roundtrip=byte_roundtrip,
    )


def _native_metadata(node: Node) -> dict[str, object]:
    return {
        key: value
        for key, value in node.metadata.items()
        if key.startswith("html.") or key == CAPABILITY_METADATA_KEY
    }


def _fail_native_evidence(
    node: Node,
    path: str,
    reason: str,
    *,
    expected: object,
    actual: object,
) -> None:
    raise PatchPreconditionError(
        "HTML native evidence no longer matches the source.",
        details={
            "reason": reason,
            "node_id": node.node_id,
            "path": path,
            "expected": expected,
            "actual": actual,
        },
    )


def _validate_node_evidence(node: Node, expected: Node, path: str) -> None:
    expected_metadata = _native_metadata(expected)
    actual_metadata = _native_metadata(node)
    if actual_metadata != expected_metadata:
        _fail_native_evidence(
            node,
            path,
            "html.metadata",
            expected=expected_metadata,
            actual=actual_metadata,
        )
    checks = (
        ("native_locator", expected.native_locator, node.native_locator),
        ("provenance", expected.provenance, node.provenance),
        ("parent", expected.parent_id, node.parent_id),
        ("children", expected.children, node.children),
        ("order", expected.order, node.order),
        ("canvas", expected.canvas_id, node.canvas_id),
        (
            "semantic_kind",
            (expected.kind, expected.semantic_role),
            (node.kind, node.semantic_role),
        ),
        ("payload", expected.payload, node.payload),
    )
    for reason, expected_value, actual_value in checks:
        if actual_value != expected_value:
            _fail_native_evidence(
                node,
                path,
                reason,
                expected=expected_value,
                actual=actual_value,
            )


def _validate_source_model(
    document: DocumentIR,
    source: bytes,
    representation: TextRepresentation,
) -> tuple[str, dict[str, Node], dict[str, Node]]:
    descriptor = document.source
    assert descriptor is not None
    try:
        parsed = parse_html_source(source, encoding=representation.encoding)
        expected_document = read_html_ir(
            BytesIO(source),
            filename=descriptor.filename,
            mimetype=descriptor.mimetype,
            encoding=representation.encoding,
        )
    except (UnicodeError, ValueError, TypeError) as exc:
        raise PatchPreconditionError(
            "HTML source cannot be re-read using the recorded representation.",
            details={"reason": "html.source_reread"},
        ) from exc

    actual_nodes = _nodes_by_path(document)
    expected_nodes = _nodes_by_path(expected_document)
    if set(actual_nodes) != set(expected_nodes):
        raise PatchPreconditionError(
            "HTML ownership topology no longer matches the source.",
            details={
                "reason": "html.path_set",
                "expected": tuple(sorted(expected_nodes)),
                "actual": tuple(sorted(actual_nodes)),
            },
        )
    if document.root_node_ids != expected_document.root_node_ids:
        raise PatchPreconditionError(
            "HTML root ownership no longer matches the source.",
            details={"reason": "html.root_identity"},
        )
    if document.canvases != expected_document.canvases:
        raise PatchPreconditionError(
            "HTML canvas ownership no longer matches the source.",
            details={"reason": "html.canvas_identity"},
        )
    for path, expected_node in expected_nodes.items():
        _validate_node_evidence(actual_nodes[path], expected_node, path)
    return parsed.text, actual_nodes, expected_nodes


def _semantic_value(node: Node) -> object:
    if not isinstance(node.payload, Mapping):
        return None
    return node.payload.get("value")


def _validate_preconditions(
    document: DocumentIR,
    node: Node,
    edit: EditOperation,
    old_value: object,
) -> None:
    precondition = edit.precondition
    if precondition is not None and precondition.expected_old_value is not None:
        if precondition.expected_old_value != old_value:
            raise PatchPreconditionError(
                "HTML edit precondition failed.",
                details={
                    "reason": "old_value",
                    "operation_id": edit.operation_id,
                    "target_node_id": edit.target_node_id,
                    "actual": old_value,
                },
            )
        edit = replace(
            edit,
            precondition=EditPrecondition(
                expected_semantic_digest=precondition.expected_semantic_digest,
                expected_native_locator_digest=precondition.expected_native_locator_digest,
                expected_old_value=None,
            ),
        )
    validate_edit_preconditions(document, node, edit, format_label="html")


def _preflight_edit(
    document: DocumentIR,
    edit: EditOperation,
    path_nodes: Mapping[str, Node],
    expected_nodes: Mapping[str, Node],
) -> tuple[Node, str, str]:
    if edit.target_node_id is None or edit.target_node_id not in document.nodes:
        raise PatchPreconditionError(
            "HTML edit target does not exist in the DocumentIR.",
            details={
                "reason": "target_mismatch",
                "operation_id": edit.operation_id,
                "target_node_id": edit.target_node_id,
            },
        )
    node = document.nodes[edit.target_node_id]
    path = node.metadata.get("html.path")
    if not isinstance(path, str) or path_nodes.get(path) is not node:
        raise PatchPreconditionError(
            "HTML edit target ownership is invalid.",
            details={"reason": "html.target_path", "operation_id": edit.operation_id},
        )
    expected = expected_nodes.get(path)
    if expected is None:
        raise PatchPreconditionError(
            "HTML edit target is missing from fresh source ownership.",
            details={"reason": "html.target_source", "path": path},
        )

    kind = node.metadata.get("html.kind")
    expected_type = {
        "text": "replace_html_text",
        "attribute": "replace_html_attribute",
    }.get(kind)
    if expected_type is None or edit.type != expected_type:
        raise UnsupportedEditError(
            "HTML edit operation does not match a writable native owner.",
            details={
                "reason": "html.edit_type_or_kind",
                "operation_id": edit.operation_id,
                "kind": kind,
                "edit_type": edit.type,
            },
        )
    capability = capabilities_for_node(node).for_operation(expected_type)
    if capability.state is not CapabilityState.WRITABLE:
        raise UnsupportedEditError(
            "HTML target is read-only for the requested edit.",
            details={
                "reason": capability.reason_code or "html.target.read_only",
                "path": path,
            },
        )
    if set(edit.payload) != {"value"}:
        raise UnsupportedEditError(
            "HTML edits require exactly one 'value' payload field.",
            details={"reason": "html.value.payload_shape", "path": path},
        )
    requested = edit.payload["value"]
    if not isinstance(requested, str):
        raise UnsupportedEditError(
            "HTML replacement value must be a string.",
            details={
                "reason": "html.value.type",
                "value_type": type(requested).__name__,
            },
        )

    old_value = _semantic_value(expected)
    _validate_preconditions(document, node, edit, old_value)
    if requested == old_value:
        raise UnsupportedEditError(
            "HTML edit is a semantic no-op.",
            details={"reason": "html.value.semantic_noop", "path": path},
        )
    return expected, path, requested


def _replacement_span(node: Node, path: str) -> tuple[int, int]:
    kind = node.metadata.get("html.kind")
    if kind == "text":
        start = node.metadata.get("html.char_start")
        end = node.metadata.get("html.char_end")
    elif kind == "attribute":
        start = node.metadata.get("html.value_start")
        end = node.metadata.get("html.value_end")
    else:
        raise UnsupportedEditError(
            "HTML target has no writable scalar span.",
            details={"reason": "html.value.span_kind", "path": path},
        )
    if (
        not isinstance(start, int)
        or not isinstance(end, int)
        or start < 0
        or end < start
    ):
        raise PatchPreconditionError(
            "HTML target value span evidence is invalid.",
            details={"reason": "html.value.span", "path": path},
        )
    return start, end


def _render_value(node: Node, path: str, requested: str) -> str:
    kind = node.metadata.get("html.kind")
    try:
        if kind == "text":
            return render_html_text(requested)
        if kind == "attribute":
            quote = node.metadata.get("html.quote")
            if not isinstance(quote, str):
                raise UnsupportedEditError(
                    "HTML writable attribute is missing quote evidence.",
                    details={"reason": "html.attribute.quote", "path": path},
                )
            return render_html_attribute(requested, quote)
    except (TypeError, ValueError) as exc:
        raise UnsupportedEditError(
            "HTML replacement could not be rendered without changing semantics.",
            details={"reason": "html.rendering.semantic", "path": path},
        ) from exc
    raise UnsupportedEditError(
        "HTML target is not a writable scalar owner.",
        details={"reason": "html.rendering.kind", "path": path},
    )


def _build_candidate(
    source_text: str,
    replacements: Sequence[tuple[int, int, str, str]],
) -> tuple[str, tuple[tuple[int, int, int, int], ...]]:
    ordered = sorted(replacements, key=lambda item: (item[0], item[1], item[3]))
    parts: list[str] = []
    untouched: list[tuple[int, int, int, int]] = []
    cursor = 0
    candidate_cursor = 0
    for start, end, token, path in ordered:
        if start < cursor or end < start or end > len(source_text):
            raise UnsupportedEditError(
                "HTML edit spans overlap or are invalid.",
                details={"reason": "html.value.overlapping_targets", "path": path},
            )
        prefix = source_text[cursor:start]
        parts.append(prefix)
        untouched.append(
            (cursor, start, candidate_cursor, candidate_cursor + len(prefix))
        )
        candidate_cursor += len(prefix)
        parts.append(token)
        candidate_cursor += len(token)
        cursor = end

    suffix = source_text[cursor:]
    parts.append(suffix)
    untouched.append(
        (cursor, len(source_text), candidate_cursor, candidate_cursor + len(suffix))
    )
    return "".join(parts), tuple(untouched)


def _result(bytes_written: int, *, zero_edit: bool) -> WriterResult:
    evidence = [
        FidelityEvidence(
            check_code="html.source_authority",
            status=FidelityStatus.PASSED,
            description="Source SHA-256 and byte size matched the DocumentIR authority.",
        ),
        FidelityEvidence(
            check_code="html.native_evidence",
            status=FidelityStatus.PASSED,
            description="HTML lexical ownership and recovery evidence matched the source.",
        ),
    ]
    if zero_edit:
        evidence.append(
            FidelityEvidence(
                check_code="html.zero_edit_identity",
                status=FidelityStatus.PASSED,
                description="Zero-edit output reused the exact source bytes.",
            )
        )
    else:
        evidence.extend(
            (
                FidelityEvidence(
                    check_code="html.lexical_span_patch",
                    status=FidelityStatus.PASSED,
                    description=(
                        "Requested HTML scalar values were replaced only at recorded "
                        "lexical value spans."
                    ),
                ),
                FidelityEvidence(
                    check_code="html.untouched_bytes",
                    status=FidelityStatus.PASSED,
                    description=(
                        "Encoded bytes outside authorized target spans were verified "
                        "unchanged."
                    ),
                ),
                FidelityEvidence(
                    check_code="html.candidate_reread",
                    status=FidelityStatus.PASSED,
                    description=(
                        "Candidate HTML was re-read and verified for ownership, recovery "
                        "structure, requested semantics, and unrequested raw evidence."
                    ),
                ),
            )
        )
    return WriterResult(
        format="html",
        mode="patch",
        bytes_written=bytes_written,
        fidelity=FidelityReport(
            claimed_tier="exact-preserve" if zero_edit else "high",
            evidence=tuple(evidence),
        ),
    )


def patch_html(
    document: DocumentIR,
    source_stream: BinaryIO,
    output: BinaryIO,
    *,
    edits: Sequence[EditOperation] = (),
) -> WriterResult:
    try:
        validate_document(document)
    except IRValidationError as exc:
        raise PatchPreconditionError(
            "HTML DocumentIR failed structural validation.",
            details={"reason": "html.document_ir_invalid"},
        ) from exc

    source = _read_source_bytes(source_stream)
    _validate_source_authority(document, source)
    edits = tuple(edits)
    representation = _representation(document, require_writable=bool(edits))
    source_text, path_nodes, expected_nodes = _validate_source_model(
        document,
        source,
        representation,
    )
    if not edits:
        output.write(source)
        return _result(len(source), zero_edit=True)

    seen_paths: set[str] = set()
    requested_values: dict[str, str] = {}
    replacements: list[tuple[int, int, str, str]] = []
    for edit in edits:
        expected, path, requested = _preflight_edit(
            document,
            edit,
            path_nodes,
            expected_nodes,
        )
        if path in seen_paths:
            raise UnsupportedEditError(
                "HTML edit set contains a duplicate target.",
                details={"reason": "html.value.duplicate_target", "path": path},
            )
        seen_paths.add(path)
        requested_values[path] = requested
        start, end = _replacement_span(expected, path)
        replacements.append(
            (start, end, _render_value(expected, path, requested), path)
        )

    candidate_text, untouched = _build_candidate(source_text, replacements)
    try:
        candidate = encode_text_source(candidate_text, representation)
    except UnicodeError as exc:
        raise UnsupportedEditError(
            "HTML replacement cannot be represented in the source encoding.",
            details={"reason": "html.encoding.replacement_unencodable"},
        ) from exc
    except ValueError as exc:
        raise RoundTripVerificationError(
            "HTML source representation could not be encoded safely.",
            details={"reason": "html.encoding.candidate"},
        ) from exc

    verify_untouched_bytes(
        source,
        candidate,
        source_text,
        candidate_text,
        representation,
        untouched,
    )
    verify_html_candidate(
        document,
        candidate,
        representation,
        requested_values,
    )
    output.write(candidate)
    return _result(len(candidate), zero_edit=False)
