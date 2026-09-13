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
from ..xml.writer import patch_xml
from .limits import EpubPackageLimits
from .lowering import EpubXmlTextReplacement, lower_epub_member_edits
from .model import ParsedEpubSource
from .package import build_epub_candidate, read_epub_member
from .parser import parse_epub_source
from .reader import read_epub_ir
from .verification import OwnerKey, verify_epub_candidate


_ALLOWED_EDIT_TYPES = frozenset(
    {"replace_epub_metadata_text", "replace_epub_xhtml_text"}
)
_OWNER_OPERATION = {
    "metadata-text": "replace_epub_metadata_text",
    "xhtml-text": "replace_epub_xhtml_text",
}


def _read_source_bytes(source_stream: BinaryIO) -> bytes:
    source = source_stream.read()
    if not isinstance(source, bytes):
        raise TypeError("EPUB source stream must produce bytes")
    return source


def _source_mismatch(reason: str, *, expected: object, actual: object) -> None:
    raise SourcePackageMismatchError(
        f"EPUB source does not match the DocumentIR source authority ({reason}).",
        details={"reason": reason, "expected": expected, "actual": actual},
    )


def _validate_source_authority(document: DocumentIR, source: bytes) -> None:
    descriptor = document.source
    if descriptor is None:
        _source_mismatch("missing_source_descriptor", expected="epub", actual=None)
    assert descriptor is not None
    if descriptor.format != "epub":
        _source_mismatch("source_format", expected="epub", actual=descriptor.format)
    digest = sha256(source).hexdigest()
    if digest != descriptor.sha256:
        _source_mismatch("source_sha256", expected=descriptor.sha256, actual=digest)
    if len(source) != descriptor.size_bytes:
        _source_mismatch(
            "source_size",
            expected=descriptor.size_bytes,
            actual=len(source),
        )


def _validate_fresh_native_evidence(
    document: DocumentIR,
    source: bytes,
    *,
    limits: EpubPackageLimits | None,
) -> DocumentIR:
    descriptor = document.source
    assert descriptor is not None
    try:
        fresh = read_epub_ir(
            BytesIO(source),
            filename=descriptor.filename,
            mimetype=descriptor.mimetype,
            limits=limits,
        )
    except (TypeError, ValueError) as exc:
        raise PatchPreconditionError(
            "EPUB source can no longer be re-read under recorded authority.",
            details={"reason": "epub.native_reread"},
        ) from exc

    expected = canonical_json_digest(fresh)
    actual = canonical_json_digest(document)
    if actual != expected:
        raise PatchPreconditionError(
            "EPUB native evidence no longer matches the exact source.",
            details={
                "reason": "epub.native_evidence_mismatch",
                "expected": expected,
                "actual": actual,
            },
        )
    return fresh


def _owner_node(document: DocumentIR, edit: EditOperation) -> Node:
    if edit.target_node_id is None or edit.target_node_id not in document.nodes:
        raise PatchPreconditionError(
            "EPUB edit target does not exist in the DocumentIR.",
            details={
                "reason": "target_mismatch",
                "operation_id": edit.operation_id,
                "target_node_id": edit.target_node_id,
            },
        )
    node = document.nodes[edit.target_node_id]
    owner_kind = node.metadata.get("epub.owner_kind")
    if (
        node.kind != "text"
        or not isinstance(node.payload, TextPayload)
        or owner_kind not in _OWNER_OPERATION
    ):
        raise UnsupportedEditError(
            "EPUB edit target must be an advertised native text owner.",
            details={"reason": "epub.target_not_text_owner"},
        )
    return node


def _preflight_edits(
    document: DocumentIR,
    edits: Sequence[EditOperation],
) -> tuple[
    dict[OwnerKey, str],
    dict[str, tuple[EpubXmlTextReplacement, ...]],
]:
    requested: dict[OwnerKey, str] = {}
    grouped: dict[str, list[EpubXmlTextReplacement]] = {}

    for edit in edits:
        if edit.type not in _ALLOWED_EDIT_TYPES:
            raise UnsupportedEditError(
                "H7 EPUB supports text-owner replacement edits only.",
                details={
                    "reason": "epub.edit_type",
                    "operation_id": edit.operation_id,
                    "edit_type": edit.type,
                },
            )
        node = _owner_node(document, edit)
        owner_kind = node.metadata["epub.owner_kind"]
        expected_operation = _OWNER_OPERATION[owner_kind]
        if edit.type != expected_operation:
            raise UnsupportedEditError(
                "EPUB edit type does not match the native owner kind.",
                details={
                    "reason": "epub.owner_operation_mismatch",
                    "operation_id": edit.operation_id,
                    "expected": expected_operation,
                    "actual": edit.type,
                },
            )

        validate_edit_preconditions(document, node, edit, format_label="epub")
        capability = capabilities_for_node(node).for_operation(expected_operation)
        if capability.state is not CapabilityState.WRITABLE:
            raise UnsupportedEditError(
                "EPUB text owner is read-only.",
                details={
                    "reason": capability.reason_code or "epub.target.read_only",
                    "node_id": node.node_id,
                },
            )
        if set(edit.payload) != {"value"}:
            raise UnsupportedEditError(
                "EPUB text edits require exactly one 'value' payload field.",
                details={"reason": "epub.text.payload_shape"},
            )
        value = edit.payload["value"]
        if not isinstance(value, str):
            raise UnsupportedEditError(
                "EPUB text replacement value must be a string.",
                details={"reason": "epub.text.value_type"},
            )
        if value == node.payload.text:
            raise UnsupportedEditError(
                "EPUB text edit is a semantic no-op.",
                details={
                    "reason": "epub.text.semantic_noop",
                    "node_id": node.node_id,
                },
            )

        member_path = node.metadata.get("epub.member_path")
        member_sha256 = node.metadata.get("epub.member_sha256")
        xml_path = node.metadata.get("epub.xml_path")
        if not all(
            isinstance(item, str) and item
            for item in (member_path, member_sha256, xml_path)
        ):
            raise PatchPreconditionError(
                "EPUB native text-owner evidence is incomplete.",
                details={"reason": "epub.owner.native_evidence"},
            )
        assert isinstance(member_path, str)
        assert isinstance(member_sha256, str)
        assert isinstance(xml_path, str)
        key = (member_path, xml_path)
        if key in requested:
            raise UnsupportedEditError(
                "EPUB edit set contains a duplicate native text owner.",
                details={
                    "reason": "epub.text.duplicate_target",
                    "member_path": member_path,
                    "xml_path": xml_path,
                },
            )

        requested[key] = value
        grouped.setdefault(member_path, []).append(
            EpubXmlTextReplacement(
                operation_id=edit.operation_id,
                xml_path=xml_path,
                member_sha256=member_sha256,
                value=value,
            )
        )

    return requested, {key: tuple(value) for key, value in grouped.items()}


def _zero_edit_result(bytes_written: int) -> WriterResult:
    return WriterResult(
        format="epub",
        mode="patch",
        bytes_written=bytes_written,
        fidelity=FidelityReport(
            claimed_tier="exact-preserve",
            evidence=(
                FidelityEvidence(
                    check_code="epub.source_authority",
                    status=FidelityStatus.PASSED,
                    description="Source SHA-256 and byte size matched EPUB authority.",
                ),
                FidelityEvidence(
                    check_code="epub.package_authority",
                    status=FidelityStatus.PASSED,
                    description="The authoritative EPUB package re-read successfully.",
                ),
                FidelityEvidence(
                    check_code="epub.zero_edit_identity",
                    status=FidelityStatus.PASSED,
                    description="Zero-edit output reused the exact EPUB bytes.",
                ),
            ),
        ),
    )


def _mutation_result(bytes_written: int) -> WriterResult:
    evidence = (
        ("epub.source_authority", "Source SHA-256 and size matched EPUB authority."),
        (
            "epub.package_authority",
            "The original OCF/package graph was authoritative.",
        ),
        (
            "epub.native_evidence",
            "Fresh EPUB IR matched the recorded native evidence.",
        ),
        (
            "epub.xml_member_lowering",
            "Authorized owners lowered only to fresh H4 XML text targets.",
        ),
        (
            "epub.member_target_only",
            "H4 verified target-only XML mutation inside touched members.",
        ),
        (
            "epub.untouched_member_content",
            "Untouched EPUB member content remained byte-identical.",
        ),
        (
            "epub.ocf_invariants",
            "The candidate preserved required OCF container invariants.",
        ),
        (
            "epub.package_graph_reread",
            "The candidate preserved manifest and spine semantics.",
        ),
        (
            "epub.candidate_reread",
            "The complete candidate passed strict H7 verification.",
        ),
    )
    return WriterResult(
        format="epub",
        mode="patch",
        bytes_written=bytes_written,
        fidelity=FidelityReport(
            claimed_tier="high",
            evidence=tuple(
                FidelityEvidence(
                    check_code=code,
                    status=FidelityStatus.PASSED,
                    description=description,
                )
                for code, description in evidence
            ),
        ),
    )


def _build_member_replacements(
    source: bytes,
    grouped: Mapping[str, tuple[EpubXmlTextReplacement, ...]],
) -> dict[str, bytes]:
    replacements: dict[str, bytes] = {}
    for member_path, requests in grouped.items():
        member_bytes = read_epub_member(source, member_path)
        shadow, lowered = lower_epub_member_edits(
            member_bytes,
            member_path,
            requests,
        )
        if not lowered:
            raise UnsupportedEditError(
                "EPUB mutation produced no authorized XML text changes.",
                details={"reason": "epub.lowering.empty", "member": member_path},
            )
        internal = BytesIO()
        patch_xml(
            shadow,
            BytesIO(member_bytes),
            internal,
            edits=lowered,
        )
        replacements[member_path] = internal.getvalue()
    return replacements


def patch_epub(
    document: DocumentIR,
    source_stream: BinaryIO,
    output: BinaryIO,
    *,
    edits: Sequence[EditOperation] = (),
    limits: EpubPackageLimits | None = None,
) -> WriterResult:
    validate_document(document)
    source = _read_source_bytes(source_stream)
    _validate_source_authority(document, source)

    edits = tuple(edits)
    if not edits:
        parse_epub_source(source, limits=limits)
        output.write(source)
        return _zero_edit_result(len(source))

    _validate_fresh_native_evidence(document, source, limits=limits)
    requested, grouped = _preflight_edits(document, edits)
    original: ParsedEpubSource = parse_epub_source(source, limits=limits)
    replacements = _build_member_replacements(source, grouped)
    candidate = build_epub_candidate(
        original.package,
        source,
        replacements=replacements,
        limits=limits,
    )
    verify_epub_candidate(
        original,
        candidate,
        requested=requested,
        touched_members=frozenset(replacements),
        limits=limits,
    )
    output.write(candidate)
    return _mutation_result(len(candidate))
