from __future__ import annotations

from collections.abc import Mapping, Sequence
import codecs
from decimal import Decimal
from hashlib import sha256
import json
import math
from typing import BinaryIO

from ..._errors import (
    PatchPreconditionError,
    RoundTripVerificationError,
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
from ...ir.nodes import Node
from ...ir.semantics import validate_edit_preconditions
from ...ir.serialization import validate_document
from ..text.codec import decode_text_source, encode_text_source
from ..text.model import TextRepresentation
from .lexical import scan_json_text
from .model import JsonLexicalDocument, JsonLexicalNode


def _read_source_bytes(source_stream: BinaryIO) -> bytes:
    source = source_stream.read()
    if not isinstance(source, bytes):
        raise TypeError("JSON source stream must produce bytes")
    return source


def _source_mismatch(reason: str, *, expected: object, actual: object) -> None:
    raise SourcePackageMismatchError(
        f"JSON source does not match the DocumentIR source authority ({reason}).",
        details={"reason": reason, "expected": expected, "actual": actual},
    )


def _validate_source_authority(document: DocumentIR, source: bytes) -> None:
    descriptor = document.source
    if descriptor is None:
        _source_mismatch("missing_source_descriptor", expected="json", actual=None)
    assert descriptor is not None
    if descriptor.format != "json":
        _source_mismatch("source_format", expected="json", actual=descriptor.format)
    digest = sha256(source).hexdigest()
    if digest != descriptor.sha256:
        _source_mismatch("source_sha256", expected=descriptor.sha256, actual=digest)
    if len(source) != descriptor.size_bytes:
        _source_mismatch(
            "source_size",
            expected=descriptor.size_bytes,
            actual=len(source),
        )


def _nodes_by_pointer(document: DocumentIR) -> dict[str, Node]:
    result: dict[str, Node] = {}
    for node in document.nodes.values():
        pointer = node.metadata.get("json.pointer")
        if not isinstance(pointer, str):
            raise PatchPreconditionError(
                "JSON node is missing its native pointer evidence.",
                details={"reason": "missing_pointer", "node_id": node.node_id},
            )
        if pointer in result:
            raise PatchPreconditionError(
                "JSON pointer ownership is ambiguous in the DocumentIR.",
                details={"reason": "duplicate_pointer", "pointer": pointer},
            )
        result[pointer] = node
    return result


def _representation(document: DocumentIR) -> TextRepresentation:
    nodes = _nodes_by_pointer(document)
    root = nodes.get("")
    if root is None:
        raise PatchPreconditionError(
            "JSON root node is missing from the DocumentIR.",
            details={"reason": "missing_root"},
        )
    encoding = root.metadata.get("json.encoding")
    bom = root.metadata.get("json.bom")
    byte_roundtrip = root.metadata.get("json.byte_roundtrip")
    if not isinstance(encoding, str) or not isinstance(bom, str):
        raise PatchPreconditionError(
            "JSON source representation metadata is incomplete.",
            details={"reason": "representation_metadata"},
        )
    if not isinstance(byte_roundtrip, bool) or not byte_roundtrip:
        raise UnsupportedEditError(
            "JSON source encoding is not byte-roundtrippable.",
            details={"reason": "json.encoding.not_roundtrippable"},
        )
    return TextRepresentation(
        encoding=encoding,
        bom=bom,
        newline="mixed",
        byte_roundtrip=True,
    )


def _fail_native_evidence(
    node: Node,
    pointer: str,
    reason: str,
    *,
    expected: object,
    actual: object,
) -> None:
    raise PatchPreconditionError(
        "JSON native evidence no longer matches the source.",
        details={
            "reason": reason,
            "node_id": node.node_id,
            "pointer": pointer,
            "expected": expected,
            "actual": actual,
        },
    )


def _validate_node_evidence(
    node: Node,
    lexical: JsonLexicalNode,
    pointer_nodes: Mapping[str, Node],
) -> None:
    pointer = lexical.pointer
    expected_metadata = {
        "json.pointer": pointer,
        "json.kind": lexical.kind,
        "json.char_start": lexical.start,
        "json.char_end": lexical.end,
        "json.raw": lexical.raw,
        "json.raw_digest": lexical.raw_digest,
    }
    for key, expected in expected_metadata.items():
        actual = node.metadata.get(key)
        if actual != expected:
            _fail_native_evidence(
                node,
                pointer,
                key,
                expected=expected,
                actual=actual,
            )

    locator = node.native_locator
    expected_locator = ("json", "/", "value", pointer)
    actual_locator = None
    if locator is not None:
        actual_locator = (
            locator.backend,
            locator.part_uri,
            locator.object_id,
            locator.path,
        )
    if actual_locator != expected_locator:
        _fail_native_evidence(
            node,
            pointer,
            "native_locator",
            expected=expected_locator,
            actual=actual_locator,
        )

    expected_span = (lexical.start, lexical.end)
    actual_span = node.provenance[0].char_span if len(node.provenance) == 1 else None
    if actual_span != expected_span:
        _fail_native_evidence(
            node,
            pointer,
            "source_span",
            expected=expected_span,
            actual=actual_span,
        )

    expected_parent = (
        None
        if lexical.parent_pointer is None
        else pointer_nodes[lexical.parent_pointer].node_id
    )
    if node.parent_id != expected_parent:
        _fail_native_evidence(
            node,
            pointer,
            "parent",
            expected=expected_parent,
            actual=node.parent_id,
        )
    expected_children = tuple(pointer_nodes[item].node_id for item in lexical.children)
    if node.children != expected_children:
        _fail_native_evidence(
            node,
            pointer,
            "children",
            expected=expected_children,
            actual=node.children,
        )
    if node.kind != "unknown_native" or node.semantic_role != f"json-{lexical.kind}":
        _fail_native_evidence(
            node,
            pointer,
            "semantic_kind",
            expected=("unknown_native", f"json-{lexical.kind}"),
            actual=(node.kind, node.semantic_role),
        )


def _validate_source_model(
    document: DocumentIR,
    source: bytes,
    representation: TextRepresentation,
) -> tuple[str, JsonLexicalDocument, dict[str, Node]]:
    try:
        source_text, actual_representation = decode_text_source(
            source,
            encoding=representation.encoding,
        )
    except (UnicodeError, ValueError) as exc:
        raise PatchPreconditionError(
            "JSON source cannot be decoded using the recorded representation.",
            details={"reason": "source_decode"},
        ) from exc

    if (
        actual_representation.encoding != representation.encoding
        or actual_representation.bom != representation.bom
        or not actual_representation.byte_roundtrip
    ):
        raise PatchPreconditionError(
            "JSON source representation no longer matches the DocumentIR.",
            details={
                "reason": "representation_drift",
                "expected_encoding": representation.encoding,
                "actual_encoding": actual_representation.encoding,
                "expected_bom": representation.bom,
                "actual_bom": actual_representation.bom,
            },
        )
    try:
        if encode_text_source(source_text, representation) != source:
            raise PatchPreconditionError(
                "JSON source fails exact decode/encode authority proof.",
                details={"reason": "source_roundtrip"},
            )
    except UnicodeError as exc:
        raise PatchPreconditionError(
            "JSON source fails exact decode/encode authority proof.",
            details={"reason": "source_roundtrip"},
        ) from exc

    lexical = scan_json_text(source_text)
    pointer_nodes = _nodes_by_pointer(document)
    lexical_by_pointer = {item.pointer: item for item in lexical.nodes}
    if set(pointer_nodes) != set(lexical_by_pointer):
        raise PatchPreconditionError(
            "JSON pointer topology no longer matches the source.",
            details={
                "reason": "pointer_set",
                "expected": tuple(sorted(pointer_nodes)),
                "actual": tuple(sorted(lexical_by_pointer)),
            },
        )
    for pointer, source_node in lexical_by_pointer.items():
        _validate_node_evidence(pointer_nodes[pointer], source_node, pointer_nodes)
    return source_text, lexical, pointer_nodes


def _render_scalar(value: object) -> tuple[str, str, object]:
    if value is None:
        return "null", "null", None
    if type(value) is bool:
        return ("true" if value else "false"), "boolean", value
    if type(value) is str:
        return json.dumps(value, ensure_ascii=False), "string", value
    if type(value) is int:
        return str(value), "number", Decimal(value)
    if type(value) is float:
        if not math.isfinite(value):
            raise UnsupportedEditError(
                "JSON replacement numbers must be finite.",
                details={"reason": "json.scalar.non_finite"},
            )
        token = json.dumps(value, ensure_ascii=False, allow_nan=False)
        return token, "number", Decimal(token)
    raise UnsupportedEditError(
        "JSON H3 supports scalar replacement values only.",
        details={
            "reason": "json.scalar.structural_value_unsupported",
            "value_type": type(value).__name__,
        },
    )


def _source_semantic(node: JsonLexicalNode) -> tuple[str, object]:
    if node.kind == "number":
        assert node.number_value is not None
        return "number", node.number_value
    if node.kind == "null":
        return "null", None
    return node.kind, node.value


def _preflight_edit(
    document: DocumentIR,
    edit: EditOperation,
    pointer_nodes: Mapping[str, Node],
    lexical_by_pointer: Mapping[str, JsonLexicalNode],
) -> tuple[JsonLexicalNode, str]:
    if edit.type != "replace_json_scalar":
        raise UnsupportedEditError(
            "JSON H3 supports replace_json_scalar edits only.",
            details={"reason": "json.edit_type", "operation_id": edit.operation_id},
        )
    if edit.target_node_id is None or edit.target_node_id not in document.nodes:
        raise PatchPreconditionError(
            "JSON edit target does not exist in the DocumentIR.",
            details={
                "reason": "target_mismatch",
                "operation_id": edit.operation_id,
                "target_node_id": edit.target_node_id,
            },
        )
    node = document.nodes[edit.target_node_id]
    pointer = node.metadata.get("json.pointer")
    if not isinstance(pointer, str) or pointer_nodes.get(pointer) is not node:
        raise PatchPreconditionError(
            "JSON edit target ownership is invalid.",
            details={"reason": "target_pointer", "operation_id": edit.operation_id},
        )
    validate_edit_preconditions(document, node, edit, format_label="json")

    capability = capabilities_for_node(node).for_operation("replace_json_scalar")
    if capability.state is not CapabilityState.WRITABLE:
        raise UnsupportedEditError(
            "JSON target is read-only for scalar replacement.",
            details={
                "reason": capability.reason_code or "json.target.read_only",
                "pointer": pointer,
            },
        )

    if set(edit.payload) != {"value"}:
        raise UnsupportedEditError(
            "JSON scalar edits require exactly one 'value' payload field.",
            details={"reason": "json.scalar.payload_shape", "pointer": pointer},
        )
    token, requested_kind, requested_semantic = _render_scalar(edit.payload["value"])
    lexical_node = lexical_by_pointer[pointer]
    if lexical_node.kind in {"object", "array"}:
        raise UnsupportedEditError(
            "JSON object and array structural replacement is not supported in H3.",
            details={"reason": "json.container.structural_edit_unsupported"},
        )
    source_kind, source_semantic = _source_semantic(lexical_node)
    if source_kind == requested_kind and source_semantic == requested_semantic:
        raise UnsupportedEditError(
            "JSON scalar edit is a semantic no-op.",
            details={"reason": "json.scalar.semantic_noop", "pointer": pointer},
        )
    return lexical_node, token


def _build_candidate(
    source_text: str,
    replacements: Sequence[tuple[JsonLexicalNode, str]],
) -> tuple[str, tuple[tuple[int, int, int, int], ...]]:
    ordered = sorted(replacements, key=lambda item: item[0].start)
    parts: list[str] = []
    untouched: list[tuple[int, int, int, int]] = []
    cursor = 0
    candidate_cursor = 0
    for lexical, token in ordered:
        if lexical.start < cursor:
            raise UnsupportedEditError(
                "JSON scalar edit spans overlap.",
                details={"reason": "json.scalar.overlapping_targets"},
            )
        prefix = source_text[cursor : lexical.start]
        parts.append(prefix)
        untouched.append(
            (cursor, lexical.start, candidate_cursor, candidate_cursor + len(prefix))
        )
        candidate_cursor += len(prefix)
        parts.append(token)
        candidate_cursor += len(token)
        cursor = lexical.end

    suffix = source_text[cursor:]
    parts.append(suffix)
    untouched.append(
        (cursor, len(source_text), candidate_cursor, candidate_cursor + len(suffix))
    )
    return "".join(parts), tuple(untouched)


def _encoded_payload_and_boundaries(
    text: str, encoding: str
) -> tuple[bytes, tuple[int, ...]]:
    encoder_type = codecs.getincrementalencoder(encoding)
    encoder = encoder_type(errors="strict")
    payload = bytearray()
    boundaries = [0]
    for character in text:
        payload.extend(encoder.encode(character, final=False))
        boundaries.append(len(payload))
    payload.extend(encoder.encode("", final=True))
    boundaries[-1] = len(payload)
    encoded = bytes(payload)
    expected = text.encode(encoding, errors="strict")
    if encoded != expected:
        raise RoundTripVerificationError(
            "Incremental JSON encoding disagrees with strict whole-text encoding.",
            details={"reason": "json.incremental_encoding_mismatch", "encoding": encoding},
        )
    return encoded, tuple(boundaries)


def _verify_untouched_bytes(
    source_bytes: bytes,
    candidate_bytes: bytes,
    source_text: str,
    candidate_text: str,
    representation: TextRepresentation,
    untouched: tuple[tuple[int, int, int, int], ...],
) -> None:
    original_expected, original_bounds = _encoded_payload_and_boundaries(
        source_text, representation.encoding
    )
    candidate_expected, candidate_bounds = _encoded_payload_and_boundaries(
        candidate_text, representation.encoding
    )
    original_bom_length = len(source_bytes) - len(original_expected)
    candidate_bom_length = len(candidate_bytes) - len(candidate_expected)
    if original_bom_length < 0 or candidate_bom_length < 0:
        raise RoundTripVerificationError(
            "JSON encoded payload exceeds its byte stream.",
            details={"reason": "json.invalid_encoded_payload_boundary"},
        )
    if (
        original_bom_length != candidate_bom_length
        or source_bytes[:original_bom_length]
        != candidate_bytes[:candidate_bom_length]
    ):
        raise RoundTripVerificationError(
            "JSON BOM or encoded payload boundary changed unexpectedly.",
            details={"reason": "json.encoding_boundary_mismatch"},
        )

    original_payload = source_bytes[original_bom_length:]
    candidate_payload = candidate_bytes[candidate_bom_length:]
    if original_payload != original_expected:
        raise RoundTripVerificationError(
            "JSON source bytes disagree with the recorded strict encoding.",
            details={"reason": "json.source_encoded_payload_mismatch"},
        )

    for old_start, old_end, new_start, new_end in untouched:
        old_bytes = original_payload[
            original_bounds[old_start] : original_bounds[old_end]
        ]
        new_bytes = candidate_payload[
            candidate_bounds[new_start] : candidate_bounds[new_end]
        ]
        if old_bytes != new_bytes:
            raise RoundTripVerificationError(
                "JSON bytes outside authorized target spans changed.",
                details={
                    "reason": "json.untouched_bytes_changed",
                    "source_span": (old_start, old_end),
                    "candidate_span": (new_start, new_end),
                },
            )

    if candidate_payload != candidate_expected:
        raise RoundTripVerificationError(
            "JSON candidate bytes disagree with strict candidate encoding.",
            details={"reason": "json.candidate_encoded_payload_mismatch"},
        )


def _result(bytes_written: int, *, zero_edit: bool) -> WriterResult:
    checks = [
        FidelityEvidence(
            check_code="json.source_authority",
            status=FidelityStatus.PASSED,
            description="Source SHA-256 and byte size matched the DocumentIR authority.",
        )
    ]
    if zero_edit:
        checks.append(
            FidelityEvidence(
                check_code="json.zero_edit_identity",
                status=FidelityStatus.PASSED,
                description="Zero-edit output reused the exact source bytes.",
            )
        )
    else:
        checks.extend(
            (
                FidelityEvidence(
                    check_code="json.native_evidence",
                    status=FidelityStatus.PASSED,
                    description="JSON pointer, hierarchy, span, and raw evidence matched the source.",
                ),
                FidelityEvidence(
                    check_code="json.lexical_span_patch",
                    status=FidelityStatus.PASSED,
                    description="Requested scalars were replaced by exact lexical source spans.",
                ),
                FidelityEvidence(
                    check_code="json.untouched_byte_segments",
                    status=FidelityStatus.PASSED,
                    description="All encoded byte segments outside target scalars stayed exact.",
                ),
            )
        )
    return WriterResult(
        format="json",
        mode="patch",
        bytes_written=bytes_written,
        fidelity=FidelityReport(
            claimed_tier="exact-preserve" if zero_edit else "high",
            evidence=tuple(checks),
        ),
    )


def patch_json(
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
        return _result(len(source), zero_edit=True)

    representation = _representation(document)
    source_text, lexical, pointer_nodes = _validate_source_model(
        document,
        source,
        representation,
    )
    lexical_by_pointer = {item.pointer: item for item in lexical.nodes}

    replacements: list[tuple[JsonLexicalNode, str]] = []
    target_pointers: set[str] = set()
    for edit in edits:
        lexical_node, token = _preflight_edit(
            document,
            edit,
            pointer_nodes,
            lexical_by_pointer,
        )
        if lexical_node.pointer in target_pointers:
            raise UnsupportedEditError(
                "JSON edit set contains a duplicate target.",
                details={
                    "reason": "json.scalar.duplicate_target",
                    "pointer": lexical_node.pointer,
                },
            )
        target_pointers.add(lexical_node.pointer)
        replacements.append((lexical_node, token))

    candidate_text, untouched = _build_candidate(source_text, replacements)
    try:
        candidate = encode_text_source(candidate_text, representation)
    except UnicodeError as exc:
        raise UnsupportedEditError(
            "JSON replacement cannot be represented in the source encoding.",
            details={"reason": "json.encoding.replacement_unencodable"},
        ) from exc
    except ValueError as exc:
        raise RoundTripVerificationError(
            "JSON source representation could not be encoded safely.",
            details={"reason": "json.encoding.candidate"},
        ) from exc

    _verify_untouched_bytes(
        source,
        candidate,
        source_text,
        candidate_text,
        representation,
        untouched,
    )
    output.write(candidate)
    return _result(len(candidate), zero_edit=False)
