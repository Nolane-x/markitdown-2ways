from __future__ import annotations

from io import BytesIO
from typing import Iterable

from ..._errors import RoundTripVerificationError
from ..._results import FidelityEvidence, FidelityReport, FidelityStatus
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.semantics import node_semantic_digest, node_semantic_text
from ...ooxml import OOXMLPackageLimits
from ...ooxml.package import inspect_package_preservation
from ._verify_native import (
    _fail,
    _verify_native_subtrees,
    _verify_relationships_and_media,
)


def _reopen_evidence(output_bytes: bytes) -> FidelityEvidence:
    try:
        from docx import Document
    except (ImportError, ModuleNotFoundError):
        return FidelityEvidence(
            check_code="docx.reopen",
            status=FidelityStatus.NOT_APPLICABLE,
            description=(
                "python-docx is not installed; reopen oracle was not applicable."
            ),
            required=False,
        )
    try:
        Document(BytesIO(output_bytes))
    except Exception as exc:
        raise RoundTripVerificationError(
            "Patched DOCX cannot be reopened by python-docx.",
            details={"check": "docx.reopen", "error": repr(exc)},
        ) from exc
    return FidelityEvidence(
        check_code="docx.reopen",
        status=FidelityStatus.PASSED,
        description="Patched DOCX reopens successfully with python-docx.",
    )


def verify_docx_output(
    original_document: DocumentIR,
    source_bytes: bytes,
    output_bytes: bytes,
    *,
    edits: Iterable[EditOperation],
    touched_parts: tuple[str, ...],
    limits: OOXMLPackageLimits,
) -> FidelityReport:
    preservation = inspect_package_preservation(
        source_bytes,
        output_bytes,
        touched_parts=touched_parts,
        limits=limits,
    )
    if not preservation.inventory_matches:
        _fail(
            "docx.package.inventory",
            "DOCX package inventory changed during patch.",
            expected=preservation.before_names,
            actual=preservation.after_names,
        )
    if preservation.changed_untouched:
        _fail(
            "docx.package.untouched_members",
            "Untouched DOCX package members changed during patch.",
            expected=[],
            actual=list(preservation.changed_untouched),
        )

    reopen_evidence = _reopen_evidence(output_bytes)

    from .reader import read_docx_ir

    output_document = read_docx_ir(BytesIO(output_bytes))
    edit_list = tuple(edits)
    edited_ids = {edit.target_node_id for edit in edit_list if edit.target_node_id}
    for edit in edit_list:
        if (
            edit.target_node_id is None
            or edit.target_node_id not in output_document.nodes
        ):
            _fail(
                "docx.semantic.target_identity",
                "Edited DOCX node identity did not survive round trip.",
                expected=edit.target_node_id,
                actual=None,
            )
        output_node = output_document.nodes[edit.target_node_id]
        expected_value = (
            edit.payload.get("text")
            if edit.type == "replace_text"
            else edit.payload.get("alt_text")
        )
        actual_value = node_semantic_text(output_node)
        if actual_value != expected_value:
            _fail(
                "docx.semantic.readback",
                "Patched DOCX semantic value did not read back correctly.",
                expected=expected_value,
                actual=actual_value,
            )

    _verify_native_subtrees(
        original_document,
        source_bytes,
        output_bytes,
        edits=edit_list,
        touched_parts=touched_parts,
    )
    _verify_relationships_and_media(
        source_bytes,
        output_bytes,
        touched_parts=touched_parts,
    )

    changed_unrelated = []
    for node_id, node in original_document.nodes.items():
        if node_id in edited_ids:
            continue
        output_node = output_document.nodes.get(node_id)
        if (
            output_node is None
            or node_semantic_digest(output_node) != node_semantic_digest(node)
        ):
            changed_unrelated.append(node_id)
    if changed_unrelated:
        _fail(
            "docx.semantic.unrelated_nodes",
            "Unrelated DOCX semantic nodes changed during patch.",
            expected=[],
            actual=changed_unrelated,
        )

    return FidelityReport(
        claimed_tier="high",
        evidence=(
            FidelityEvidence(
                check_code="docx.package.inventory",
                status=FidelityStatus.PASSED,
                description="DOCX package member inventory is unchanged.",
            ),
            FidelityEvidence(
                check_code="docx.package.untouched_members",
                status=FidelityStatus.PASSED,
                description=(
                    "Untouched DOCX package members preserve identical "
                    "uncompressed bytes."
                ),
            ),
            reopen_evidence,
            FidelityEvidence(
                check_code="docx.semantic.readback",
                status=FidelityStatus.PASSED,
                description=(
                    "Requested DOCX edits read back with expected semantic values."
                ),
                affected_node_ids=tuple(sorted(edited_ids)),
            ),
            FidelityEvidence(
                check_code="docx.native.unrelated_subtrees",
                status=FidelityStatus.PASSED,
                description=(
                    "Unedited native DOCX subtrees in touched parts remain "
                    "canonically identical."
                ),
            ),
            FidelityEvidence(
                check_code="docx.native.target_structure",
                status=FidelityStatus.PASSED,
                description=(
                    "Edited DOCX native wrappers preserve their structure "
                    "outside permitted values."
                ),
                affected_node_ids=tuple(sorted(edited_ids)),
            ),
            FidelityEvidence(
                check_code="docx.hyperlinks.relationships",
                status=FidelityStatus.PASSED,
                description=(
                    "DOCX relationship parts remain unchanged during "
                    "text/value patching."
                ),
            ),
            FidelityEvidence(
                check_code="docx.media.unchanged",
                status=FidelityStatus.PASSED,
                description="DOCX media inventory and bytes remain unchanged.",
            ),
            FidelityEvidence(
                check_code="docx.semantic.unrelated_nodes",
                status=FidelityStatus.PASSED,
                description=(
                    "Unedited DOCX semantic nodes retain identical semantic digests."
                ),
            ),
        ),
    )
