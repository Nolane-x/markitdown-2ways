from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from io import BytesIO
from typing import Any, BinaryIO

from ..._errors import (
    PatchPreconditionError,
    RoundTripVerificationError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from ..._results import FidelityEvidence, FidelityReport, FidelityStatus, WriterResult
from ...capabilities import CapabilityState, capabilities_for_node
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.nodes import Node, TextPayload
from ...ir.semantics import validate_edit_preconditions
from ...ir.serialization import validate_document
from ...writers.base import DocumentWriter, TargetInfo
from .codec import decode_text_source, encode_text_source, normalize_newlines
from .model import TextRepresentation
from .reader import read_text_ir


def _read_source_bytes(source: BinaryIO) -> bytes:
    data = source.read()
    if isinstance(data, str):
        raise TypeError("text source stream must return bytes")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("text source stream returned a non-bytes value")
    return bytes(data)


def _validate_source_authority(document: DocumentIR, source_bytes: bytes) -> str:
    source = document.source
    actual_digest = sha256(source_bytes).hexdigest()
    if source is None or source.format not in {"text", "markdown"} or not source.sha256:
        raise SourcePackageMismatchError(
            "DocumentIR does not contain authoritative text source metadata.",
            details={"reason": "missing_source_authority", "actual": actual_digest},
        )
    if source.sha256 != actual_digest:
        raise SourcePackageMismatchError(
            "Provided text source does not match the DocumentIR source authority.",
            details={
                "reason": "source_digest_mismatch",
                "expected": source.sha256,
                "actual": actual_digest,
            },
        )
    if source.size_bytes is not None and source.size_bytes != len(source_bytes):
        raise SourcePackageMismatchError(
            "Provided text source size does not match the DocumentIR source authority.",
            details={
                "reason": "source_size_mismatch",
                "expected": source.size_bytes,
                "actual": len(source_bytes),
            },
        )
    return source.format


def _representation_for_node(node: Node) -> TextRepresentation:
    try:
        encoding = node.metadata["text.encoding"]
        bom = node.metadata["text.bom"]
        newline = node.metadata["text.newline"]
        byte_roundtrip = node.metadata["text.byte_roundtrip"]
    except KeyError as exc:
        raise PatchPreconditionError(
            "Text edit target is missing source representation metadata.",
            details={"reason": "missing_representation_metadata", "field": str(exc)},
        ) from exc
    if (
        not isinstance(encoding, str)
        or not isinstance(bom, str)
        or not isinstance(newline, str)
    ):
        raise PatchPreconditionError(
            "Text edit target contains invalid source representation metadata.",
            details={"reason": "invalid_representation_metadata"},
        )
    if not isinstance(byte_roundtrip, bool):
        raise PatchPreconditionError(
            "Text edit target contains invalid byte-roundtrip metadata.",
            details={"reason": "invalid_representation_metadata"},
        )
    try:
        return TextRepresentation(
            encoding=encoding,
            bom=bom,
            newline=newline,
            byte_roundtrip=byte_roundtrip,
        )
    except ValueError as exc:
        raise PatchPreconditionError(
            "Text edit target contains unsupported source representation metadata.",
            details={"reason": "invalid_representation_metadata"},
        ) from exc


def _validate_native_binding(node: Node, source_format: str) -> None:
    locator = node.native_locator
    if (
        locator is None
        or locator.backend != "text"
        or locator.part_uri != "/"
        or locator.object_id != "document-body"
        or node.metadata.get("text.format") != source_format
    ):
        raise PatchPreconditionError(
            "Text edit target is not bound to the authoritative source body.",
            details={
                "reason": "missing_or_unauthorized_text_locator",
                "target_node_id": node.node_id,
            },
        )


def _validate_representation_against_source(
    node: Node,
    source_bytes: bytes,
    representation: TextRepresentation,
) -> None:
    assert isinstance(node.payload, TextPayload)
    actual_text, actual = decode_text_source(
        source_bytes,
        encoding=representation.encoding,
    )
    expected = (
        representation.encoding,
        representation.bom,
        representation.newline,
        representation.byte_roundtrip,
    )
    observed = (
        actual.encoding,
        actual.bom,
        actual.newline,
        actual.byte_roundtrip,
    )
    if actual_text != node.payload.text or observed != expected:
        raise PatchPreconditionError(
            "Text source representation no longer matches the authoritative IR.",
            details={
                "reason": "source_representation_mismatch",
                "expected": expected,
                "actual": observed,
            },
        )


def _prepare_replace(
    document: DocumentIR,
    source_bytes: bytes,
    source_format: str,
    edits: tuple[EditOperation, ...],
) -> tuple[Node, TextRepresentation, str] | None:
    if not edits:
        return None
    if len(edits) != 1:
        target_ids = [
            edit.target_node_id for edit in edits if edit.type == "replace_text"
        ]
        if len(target_ids) != len(set(target_ids)):
            raise UnsupportedEditError(
                "Text patch contains duplicate replace_text targets.",
                details={"reason": "duplicate_replace_target"},
            )
        raise UnsupportedEditError(
            "H1 text patching supports one authoritative replace_text edit.",
            details={"reason": "multiple_text_edits", "count": len(edits)},
        )

    edit = edits[0]
    if edit.type != "replace_text":
        raise UnsupportedEditError(
            "Text patch writer supports only replace_text in H1.",
            details={"reason": "unsupported_edit_type", "edit_type": edit.type},
        )
    if edit.target_node_id is None or edit.target_node_id not in document.nodes:
        raise PatchPreconditionError(
            "Text edit target node does not exist in the source IR.",
            details={
                "reason": "missing_target",
                "target_node_id": edit.target_node_id,
            },
        )
    node = document.nodes[edit.target_node_id]
    if not isinstance(node.payload, TextPayload) or node.kind != "text":
        raise UnsupportedEditError(
            "replace_text requires the authoritative text node.",
            details={"reason": "wrong_node_kind", "target_node_id": node.node_id},
        )
    _validate_native_binding(node, source_format)

    decision = capabilities_for_node(node).for_operation("replace_text")
    if decision.state is not CapabilityState.WRITABLE:
        raise UnsupportedEditError(
            "Text replace_text capability is read-only for this source.",
            details={
                "reason": decision.reason_code or "capability.read_only",
                "target_node_id": node.node_id,
            },
        )
    validate_edit_preconditions(document, node, edit, format_label="text")

    if set(edit.payload) != {"text"} or not isinstance(edit.payload.get("text"), str):
        raise UnsupportedEditError(
            "replace_text payload must contain exactly one string field named text.",
            details={"reason": "invalid_replace_text_payload"},
        )

    representation = _representation_for_node(node)
    _validate_representation_against_source(node, source_bytes, representation)
    requested = edit.payload["text"]
    try:
        normalized = normalize_newlines(requested, representation.newline)
    except ValueError as exc:
        raise UnsupportedEditError(
            "Replacement cannot preserve the source newline convention.",
            details={"reason": "newline_convention_not_preservable"},
        ) from exc
    return node, representation, normalized


def _verify_candidate(
    document: DocumentIR,
    candidate: bytes,
    *,
    source_format: str,
    representation: TextRepresentation,
    expected_text: str,
) -> None:
    assert document.source is not None
    reread = read_text_ir(
        BytesIO(candidate),
        filename=document.source.filename,
        mimetype=document.source.mimetype,
        encoding=representation.encoding,
    )
    node = reread.nodes[reread.canvases[0].root_node_ids[0]]
    if not isinstance(node.payload, TextPayload):
        raise RoundTripVerificationError(
            "Re-read text output did not produce a text payload.",
            details={"reason": "missing_text_payload"},
        )
    expected_newline = representation.newline
    if not any(separator in expected_text for separator in ("\r", "\n")):
        expected_newline = "none"
    observed = (
        reread.source.format if reread.source is not None else None,
        node.metadata.get("text.encoding"),
        node.metadata.get("text.bom"),
        node.metadata.get("text.newline"),
        node.metadata.get("text.byte_roundtrip"),
    )
    expected = (
        source_format,
        representation.encoding,
        representation.bom,
        expected_newline,
        True,
    )
    if node.payload.text != expected_text or observed != expected:
        raise RoundTripVerificationError(
            "Text output failed semantic or source-representation verification.",
            details={
                "reason": "text_roundtrip_mismatch",
                "expected_representation": expected,
                "actual_representation": observed,
            },
        )


def patch_text(
    document: DocumentIR,
    source_stream: BinaryIO,
    output: BinaryIO,
    *,
    edits: Sequence[EditOperation] = (),
) -> WriterResult:
    validate_document(document)
    source_bytes = _read_source_bytes(source_stream)
    source_format = _validate_source_authority(document, source_bytes)
    edit_list = tuple(edits)

    prepared = _prepare_replace(document, source_bytes, source_format, edit_list)
    if prepared is None:
        output_bytes = source_bytes
        fidelity = FidelityReport(
            claimed_tier="exact-preserve",
            evidence=(
                FidelityEvidence(
                    check_code="text.byte_identity",
                    status=FidelityStatus.PASSED,
                    description="No-op text patch preserves source bytes exactly.",
                    expected=sha256(source_bytes).hexdigest(),
                    actual=sha256(output_bytes).hexdigest(),
                ),
            ),
        )
    else:
        node, representation, normalized = prepared
        assert isinstance(node.payload, TextPayload)
        if normalized == node.payload.text:
            output_bytes = source_bytes
        else:
            output_bytes = encode_text_source(normalized, representation)
        _verify_candidate(
            document,
            output_bytes,
            source_format=source_format,
            representation=representation,
            expected_text=normalized,
        )
        fidelity = FidelityReport(
            claimed_tier="high",
            evidence=(
                FidelityEvidence(
                    check_code="text.semantic_readback",
                    status=FidelityStatus.PASSED,
                    description="Edited text was re-read with the requested semantics.",
                    expected=normalized,
                    actual=normalized,
                    affected_node_ids=(node.node_id,),
                ),
                FidelityEvidence(
                    check_code="text.source_representation",
                    status=FidelityStatus.PASSED,
                    description="Encoding, BOM and newline policy remained within the H1 contract.",
                    expected={
                        "encoding": representation.encoding,
                        "bom": representation.bom,
                        "newline": representation.newline,
                    },
                    actual={
                        "encoding": representation.encoding,
                        "bom": representation.bom,
                        "newline": representation.newline,
                    },
                    affected_node_ids=(node.node_id,),
                ),
            ),
        )

    written = output.write(output_bytes)
    return WriterResult(
        format=source_format,
        mode="patch",
        bytes_written=len(output_bytes) if written is None else written,
        fidelity=fidelity,
        metadata={"touched_nodes": () if prepared is None else (prepared[0].node_id,)},
    )


class TextPatchWriter(DocumentWriter):
    def accepts(self, document: DocumentIR, target: TargetInfo, **kwargs: Any) -> bool:
        source_format = document.source.format if document.source is not None else None
        if source_format not in {"text", "markdown"}:
            return False
        extension = (target.extension or "").lower()
        if target.format.lower() == source_format:
            return True
        if source_format == "text":
            return extension in {".txt", ".text"}
        return extension in {".md", ".markdown"}

    def write(
        self,
        document: DocumentIR,
        output: BinaryIO,
        target: TargetInfo,
        **kwargs: Any,
    ) -> WriterResult:
        source_stream = kwargs.pop("source_stream", None)
        edits = kwargs.pop("edits", None)
        if source_stream is None or edits is None:
            raise TypeError("TextPatchWriter.write requires source_stream= and edits=")
        if kwargs:
            raise TypeError(f"unexpected text writer options: {sorted(kwargs)}")
        return patch_text(
            document,
            source_stream,
            output,
            edits=tuple(edits),
        )
