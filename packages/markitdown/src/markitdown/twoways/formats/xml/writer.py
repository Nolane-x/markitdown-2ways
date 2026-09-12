from __future__ import annotations

import codecs
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
from ..._results import (
    FidelityEvidence,
    FidelityReport,
    FidelityStatus,
    WriterResult,
)
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
from .lexical import parse_xml_source
from .model import XmlLexicalNode
from .reader import read_xml_ir


_XML_EVIDENCE_KEYS = (
    "xml.path",
    "xml.kind",
    "xml.char_start",
    "xml.char_end",
    "xml.raw",
    "xml.raw_digest",
    "xml.qname",
    "xml.expanded_name",
    "xml.value_start",
    "xml.value_end",
    "xml.quote",
    "xml.namespace_prefix",
    "xml.namespace_uri",
    "xml.encoding",
    "xml.bom",
    "xml.byte_roundtrip",
    "xml.version",
    "xml.declared_encoding",
    "xml.standalone",
    "xml.declaration_raw",
    "xml.declaration_raw_digest",
    "xml.native_source",
    "xml.identity_markdown",
    CAPABILITY_METADATA_KEY,
)


def _read_source_bytes(source_stream: BinaryIO) -> bytes:
    source = source_stream.read()
    if not isinstance(source, bytes):
        raise TypeError("XML source stream must produce bytes")
    return source


def _source_mismatch(reason: str, *, expected: object, actual: object) -> None:
    raise SourcePackageMismatchError(
        f"XML source does not match the DocumentIR source authority ({reason}).",
        details={"reason": reason, "expected": expected, "actual": actual},
    )


def _validate_source_authority(document: DocumentIR, source: bytes) -> None:
    descriptor = document.source
    if descriptor is None:
        _source_mismatch("missing_source_descriptor", expected="xml", actual=None)
    assert descriptor is not None
    if descriptor.format != "xml":
        _source_mismatch("source_format", expected="xml", actual=descriptor.format)
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
        path = node.metadata.get("xml.path")
        if not isinstance(path, str) or not path:
            raise PatchPreconditionError(
                "XML node is missing its native ownership path.",
                details={"reason": "xml.missing_path", "node_id": node.node_id},
            )
        if path in result:
            raise PatchPreconditionError(
                "XML ownership path is ambiguous in the DocumentIR.",
                details={"reason": "xml.duplicate_path", "path": path},
            )
        result[path] = node
    return result


def _root_node(document: DocumentIR) -> Node:
    if len(document.root_node_ids) != 1:
        raise PatchPreconditionError(
            "XML DocumentIR must contain exactly one document-element root.",
            details={"reason": "xml.root_count"},
        )
    root_id = document.root_node_ids[0]
    root = document.nodes.get(root_id)
    if root is None:
        raise PatchPreconditionError(
            "XML document-element root is missing.",
            details={"reason": "xml.root_missing"},
        )
    return root


def _representation(document: DocumentIR, *, require_writable: bool) -> TextRepresentation:
    root = _root_node(document)
    encoding = root.metadata.get("xml.encoding")
    bom = root.metadata.get("xml.bom")
    byte_roundtrip = root.metadata.get("xml.byte_roundtrip")
    if not isinstance(encoding, str) or not isinstance(bom, str):
        raise PatchPreconditionError(
            "XML source representation metadata is incomplete.",
            details={"reason": "xml.representation_metadata"},
        )
    if not isinstance(byte_roundtrip, bool):
        raise PatchPreconditionError(
            "XML source byte-roundtrip evidence is malformed.",
            details={"reason": "xml.representation_roundtrip_metadata"},
        )
    if require_writable and not byte_roundtrip:
        raise UnsupportedEditError(
            "XML source encoding is not byte-roundtrippable.",
            details={"reason": "xml.encoding.not_roundtrippable"},
        )
    return TextRepresentation(
        encoding=encoding,
        bom=bom,
        newline="mixed",
        byte_roundtrip=byte_roundtrip,
    )


def _fail_native_evidence(
    node: Node,
    path: str,
    reason: str,
    *,
    expected: object,
    actual: object,
) -> None:
    raise PatchPreconditionError(
        "XML native evidence no longer matches the source.",
        details={
            "reason": reason,
            "node_id": node.node_id,
            "path": path,
            "expected": expected,
            "actual": actual,
        },
    )


def _validate_node_evidence(node: Node, expected: Node, path: str) -> None:
    for key in _XML_EVIDENCE_KEYS:
        expected_value = expected.metadata.get(key)
        actual_value = node.metadata.get(key)
        if actual_value != expected_value:
            _fail_native_evidence(
                node,
                path,
                key,
                expected=expected_value,
                actual=actual_value,
            )

    checks = (
        ("native_locator", expected.native_locator, node.native_locator),
        ("provenance", expected.provenance, node.provenance),
        ("parent", expected.parent_id, node.parent_id),
        ("children", expected.children, node.children),
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
) -> tuple[str, dict[str, Node], dict[str, XmlLexicalNode]]:
    descriptor = document.source
    assert descriptor is not None
    try:
        expected_document = read_xml_ir(
            BytesIO(source),
            filename=descriptor.filename,
            mimetype=descriptor.mimetype,
            encoding=representation.encoding,
        )
    except (UnicodeError, ValueError, TypeError) as exc:
        raise PatchPreconditionError(
            "XML source cannot be re-read using the recorded representation.",
            details={"reason": "xml.source_reread"},
        ) from exc

    actual_nodes = _nodes_by_path(document)
    expected_nodes = _nodes_by_path(expected_document)
    if set(actual_nodes) != set(expected_nodes):
        raise PatchPreconditionError(
            "XML ownership topology no longer matches the source.",
            details={
                "reason": "xml.path_set",
                "expected": tuple(sorted(expected_nodes)),
                "actual": tuple(sorted(actual_nodes)),
            },
        )

    if document.root_node_ids != expected_document.root_node_ids:
        raise PatchPreconditionError(
            "XML root ownership no longer matches the source.",
            details={"reason": "xml.root_identity"},
        )
    if document.canvases != expected_document.canvases:
        raise PatchPreconditionError(
            "XML canvas ownership no longer matches the source.",
            details={"reason": "xml.canvas_identity"},
        )

    for path, expected_node in expected_nodes.items():
        _validate_node_evidence(actual_nodes[path], expected_node, path)

    lexical_by_path: dict[str, XmlLexicalNode] = {}
    source_text = ""
    if representation.byte_roundtrip:
        try:
            parsed = parse_xml_source(source, encoding=representation.encoding)
        except (UnicodeError, ValueError, TypeError) as exc:
            raise PatchPreconditionError(
                "XML source fails strict lexical authority reparse.",
                details={"reason": "xml.source_lexical_reparse"},
            ) from exc
        source_text = parsed.text
        lexical_by_path = {item.path: item for item in parsed.lexical.nodes}
        if set(lexical_by_path) != set(expected_nodes):
            raise PatchPreconditionError(
                "XML lexical ownership changed during source reparse.",
                details={"reason": "xml.lexical_path_set"},
            )

    return source_text, actual_nodes, lexical_by_path


def _is_xml_char(character: str) -> bool:
    value = ord(character)
    return (
        value in {0x9, 0xA, 0xD}
        or 0x20 <= value <= 0xD7FF
        or 0xE000 <= value <= 0xFFFD
        or 0x10000 <= value <= 0x10FFFF
    )


def _validate_requested_value(value: object) -> str:
    if not isinstance(value, str):
        raise UnsupportedEditError(
            "XML replacement value must be a string.",
            details={"reason": "xml.value.type", "value_type": type(value).__name__},
        )
    if any(not _is_xml_char(character) for character in value):
        raise UnsupportedEditError(
            "XML replacement contains a character forbidden by XML 1.0.",
            details={"reason": "xml.value.invalid_character"},
        )
    return value


def _validate_preconditions(
    document: DocumentIR,
    node: Node,
    edit: EditOperation,
    lexical: XmlLexicalNode,
) -> None:
    precondition = edit.precondition
    if precondition is not None and precondition.expected_old_value is not None:
        if precondition.expected_old_value != lexical.value:
            raise PatchPreconditionError(
                "XML edit precondition failed.",
                details={
                    "reason": "old_value",
                    "operation_id": edit.operation_id,
                    "target_node_id": edit.target_node_id,
                    "actual": lexical.value,
                },
            )
        generic_precondition = EditPrecondition(
            expected_semantic_digest=precondition.expected_semantic_digest,
            expected_native_locator_digest=precondition.expected_native_locator_digest,
            expected_old_value=None,
        )
        edit = replace(edit, precondition=generic_precondition)
    validate_edit_preconditions(document, node, edit, format_label="xml")


def _preflight_edit(
    document: DocumentIR,
    edit: EditOperation,
    path_nodes: Mapping[str, Node],
    lexical_by_path: Mapping[str, XmlLexicalNode],
) -> tuple[XmlLexicalNode, str]:
    if edit.target_node_id is None or edit.target_node_id not in document.nodes:
        raise PatchPreconditionError(
            "XML edit target does not exist in the DocumentIR.",
            details={
                "reason": "target_mismatch",
                "operation_id": edit.operation_id,
                "target_node_id": edit.target_node_id,
            },
        )
    node = document.nodes[edit.target_node_id]
    path = node.metadata.get("xml.path")
    if not isinstance(path, str) or path_nodes.get(path) is not node:
        raise PatchPreconditionError(
            "XML edit target ownership is invalid.",
            details={"reason": "xml.target_path", "operation_id": edit.operation_id},
        )
    lexical = lexical_by_path.get(path)
    if lexical is None:
        raise PatchPreconditionError(
            "XML edit target is missing from strict lexical ownership.",
            details={"reason": "xml.target_lexical", "path": path},
        )

    expected_type = {
        "text": "replace_xml_text",
        "attribute": "replace_xml_attribute",
    }.get(lexical.kind)
    if expected_type is None or edit.type != expected_type:
        raise UnsupportedEditError(
            "XML edit operation does not match a writable native owner.",
            details={
                "reason": "xml.edit_type_or_kind",
                "operation_id": edit.operation_id,
                "kind": lexical.kind,
                "edit_type": edit.type,
            },
        )

    capability = capabilities_for_node(node).for_operation(expected_type)
    if capability.state is not CapabilityState.WRITABLE:
        raise UnsupportedEditError(
            "XML target is read-only for the requested edit.",
            details={
                "reason": capability.reason_code or "xml.target.read_only",
                "path": path,
            },
        )
    if set(edit.payload) != {"value"}:
        raise UnsupportedEditError(
            "XML edits require exactly one 'value' payload field.",
            details={"reason": "xml.value.payload_shape", "path": path},
        )

    requested = _validate_requested_value(edit.payload["value"])
    _validate_preconditions(document, node, edit, lexical)
    if requested == lexical.value:
        raise UnsupportedEditError(
            "XML edit is a semantic no-op.",
            details={"reason": "xml.value.semantic_noop", "path": path},
        )
    return lexical, requested


def _render_text_value(value: str) -> str:
    parts: list[str] = []
    for character in value:
        if character == "&":
            parts.append("&amp;")
        elif character == "<":
            parts.append("&lt;")
        elif character == ">":
            parts.append("&gt;")
        elif character == "\r":
            parts.append("&#13;")
        else:
            parts.append(character)
    token = "".join(parts)
    _validate_rendered_fragment("text", token, value, quote=None)
    return token


def _render_attribute_value(value: str, quote: str | None) -> str:
    if quote not in {"'", '"'}:
        raise PatchPreconditionError(
            "XML attribute quote evidence is invalid.",
            details={"reason": "xml.attribute.quote"},
        )
    parts: list[str] = []
    for character in value:
        if character == "&":
            parts.append("&amp;")
        elif character == "<":
            parts.append("&lt;")
        elif character == ">":
            parts.append("&gt;")
        elif character == quote:
            parts.append("&quot;" if quote == '"' else "&apos;")
        elif character == "\t":
            parts.append("&#9;")
        elif character == "\n":
            parts.append("&#10;")
        elif character == "\r":
            parts.append("&#13;")
        else:
            parts.append(character)
    token = "".join(parts)
    _validate_rendered_fragment("attribute", token, value, quote=quote)
    return token


def _validate_rendered_fragment(
    kind: str,
    token: str,
    requested: str,
    *,
    quote: str | None,
) -> None:
    if kind == "text":
        wrapper = f"<r>{token}</r>"
    elif kind == "attribute" and quote in {"'", '"'}:
        wrapper = f"<r a={quote}{token}{quote}/>"
    else:
        raise RoundTripVerificationError(
            "XML renderer received an unsupported fragment kind.",
            details={"reason": "xml.render.fragment_kind", "kind": kind},
        )
    try:
        parsed = parse_xml_source(wrapper.encode("utf-8"))
    except (UnicodeError, ValueError, TypeError) as exc:
        raise RoundTripVerificationError(
            "Rendered XML fragment failed strict parser validation.",
            details={"reason": "xml.render.fragment_parse", "kind": kind},
        ) from exc

    if kind == "text":
        values = [
            item.value
            for item in parsed.lexical.nodes
            if item.kind == "text" and item.parent_path == parsed.lexical.root_path
        ]
        actual = "".join(str(value) for value in values)
    else:
        attributes = [
            item
            for item in parsed.lexical.nodes
            if item.kind == "attribute" and item.qname == "a"
        ]
        actual = attributes[0].value if len(attributes) == 1 else None
    if actual != requested:
        raise RoundTripVerificationError(
            "Rendered XML fragment changed the requested semantic value.",
            details={
                "reason": "xml.render.fragment_semantic",
                "kind": kind,
                "expected": requested,
                "actual": actual,
            },
        )


def _replacement_span(lexical: XmlLexicalNode) -> tuple[int, int]:
    if lexical.kind == "text":
        return lexical.start, lexical.end
    if lexical.kind == "attribute":
        if lexical.value_start is None or lexical.value_end is None:
            raise PatchPreconditionError(
                "XML attribute is missing exact value-span evidence.",
                details={"reason": "xml.attribute.value_span", "path": lexical.path},
            )
        return lexical.value_start, lexical.value_end
    raise UnsupportedEditError(
        "XML replacement span is unavailable for this owner kind.",
        details={"reason": "xml.value.owner_kind", "kind": lexical.kind},
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
        if start < cursor or end < start:
            raise UnsupportedEditError(
                "XML edit spans overlap or are invalid.",
                details={"reason": "xml.value.overlapping_targets", "path": path},
            )
        prefix = source_text[cursor:start]
        parts.append(prefix)
        untouched.append((cursor, start, candidate_cursor, candidate_cursor + len(prefix)))
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
            "Incremental XML encoding disagrees with strict whole-text encoding.",
            details={
                "reason": "xml.incremental_encoding_mismatch",
                "encoding": encoding,
            },
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
            "XML encoded payload exceeds its byte stream.",
            details={"reason": "xml.invalid_encoded_payload_boundary"},
        )
    if (
        original_bom_length != candidate_bom_length
        or source_bytes[:original_bom_length]
        != candidate_bytes[:candidate_bom_length]
    ):
        raise RoundTripVerificationError(
            "XML BOM or encoded payload boundary changed unexpectedly.",
            details={"reason": "xml.encoding_boundary_mismatch"},
        )

    original_payload = source_bytes[original_bom_length:]
    candidate_payload = candidate_bytes[candidate_bom_length:]
    if original_payload != original_expected:
        raise RoundTripVerificationError(
            "XML source bytes disagree with the recorded strict encoding.",
            details={"reason": "xml.source_encoded_payload_mismatch"},
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
                "XML bytes outside authorized target spans changed.",
                details={
                    "reason": "xml.untouched_bytes_changed",
                    "source_span": (old_start, old_end),
                    "candidate_span": (new_start, new_end),
                },
            )

    if candidate_payload != candidate_expected:
        raise RoundTripVerificationError(
            "XML candidate bytes disagree with strict candidate encoding.",
            details={"reason": "xml.candidate_encoded_payload_mismatch"},
        )


def _result(bytes_written: int, *, zero_edit: bool) -> WriterResult:
    evidence = [
        FidelityEvidence(
            check_code="xml.source_authority",
            status=FidelityStatus.PASSED,
            description="Source SHA-256 and byte size matched the DocumentIR authority.",
        ),
        FidelityEvidence(
            check_code="xml.native_evidence",
            status=FidelityStatus.PASSED,
            description="XML lexical ownership and native evidence matched the source.",
        ),
    ]
    if zero_edit:
        evidence.append(
            FidelityEvidence(
                check_code="xml.zero_edit_identity",
                status=FidelityStatus.PASSED,
                description="Zero-edit output reused the exact source bytes.",
            )
        )
    else:
        evidence.extend(
            (
                FidelityEvidence(
                    check_code="xml.lexical_span_patch",
                    status=FidelityStatus.PASSED,
                    description="Requested XML values were replaced only at exact lexical source spans.",
                ),
                FidelityEvidence(
                    check_code="xml.untouched_byte_segments",
                    status=FidelityStatus.PASSED,
                    description="Every encoded byte segment outside authorized value spans was preserved exactly.",
                ),
            )
        )
    return WriterResult(
        format="xml",
        mode="patch",
        bytes_written=bytes_written,
        fidelity=FidelityReport(
            claimed_tier="exact-preserve" if zero_edit else "high",
            evidence=tuple(evidence),
        ),
    )


def patch_xml(
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
            "XML DocumentIR failed structural validation.",
            details={"reason": "xml.document_ir_invalid"},
        ) from exc

    source = _read_source_bytes(source_stream)
    _validate_source_authority(document, source)
    edits = tuple(edits)
    representation = _representation(document, require_writable=bool(edits))
    source_text, path_nodes, lexical_by_path = _validate_source_model(
        document,
        source,
        representation,
    )

    if not edits:
        output.write(source)
        return _result(len(source), zero_edit=True)

    seen_paths: set[str] = set()
    replacements: list[tuple[int, int, str, str]] = []
    for edit in edits:
        lexical, requested = _preflight_edit(
            document,
            edit,
            path_nodes,
            lexical_by_path,
        )
        if lexical.path in seen_paths:
            raise UnsupportedEditError(
                "XML edit set contains a duplicate target.",
                details={"reason": "xml.value.duplicate_target", "path": lexical.path},
            )
        seen_paths.add(lexical.path)

        if lexical.kind == "text":
            token = _render_text_value(requested)
        else:
            token = _render_attribute_value(requested, lexical.quote)
        start, end = _replacement_span(lexical)
        replacements.append((start, end, token, lexical.path))

    candidate_text, untouched = _build_candidate(source_text, replacements)
    try:
        candidate = encode_text_source(candidate_text, representation)
    except UnicodeError as exc:
        raise UnsupportedEditError(
            "XML replacement cannot be represented in the source encoding.",
            details={"reason": "xml.encoding.replacement_unencodable"},
        ) from exc
    except ValueError as exc:
        raise RoundTripVerificationError(
            "XML source representation could not be encoded safely.",
            details={"reason": "xml.encoding.candidate"},
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
