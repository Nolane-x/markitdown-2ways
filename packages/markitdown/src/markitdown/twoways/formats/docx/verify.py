from __future__ import annotations

from io import BytesIO
from typing import Iterable

from ..._errors import RoundTripVerificationError
from ..._results import FidelityEvidence, FidelityReport, FidelityStatus
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.nodes import TablePayload, TextPayload
from ...ir.semantics import node_semantic_digest, node_semantic_text
from ...ir.style_edits import validate_text_style_update
from ...ir.table_edits import table_semantic_text_after_updates
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


def _expected_edit_value(original_document: DocumentIR, edit: EditOperation) -> object:
    if edit.type == "replace_text":
        return edit.payload.get("text")
    if edit.type == "set_alt_text":
        return edit.payload.get("alt_text")
    if edit.type == "set_text_style" and edit.target_node_id is not None:
        source_node = original_document.nodes.get(edit.target_node_id)
        return None if source_node is None else node_semantic_text(source_node)
    if edit.type == "update_table_cells" and edit.target_node_id is not None:
        source_node = original_document.nodes.get(edit.target_node_id)
        if source_node is not None and isinstance(source_node.payload, TablePayload):
            return table_semantic_text_after_updates(
                source_node.payload,
                edit.payload.get("cells"),
                format_label="DOCX",
            )
    return None


def _direct_style(payload: TextPayload, run_index: int) -> dict[str, object]:
    runs = tuple(run for paragraph in payload.paragraphs for run in paragraph.runs)
    if run_index < 0 or run_index >= len(runs):
        return {}
    style = runs[run_index].style
    direct = {} if style is None else dict(style.direct)
    color = direct.get("color")
    if isinstance(color, str):
        direct["color"] = color.upper()
    size = direct.get("font_size_pt")
    if type(size) in {int, float}:
        direct["font_size_pt"] = float(size)
    return direct


def _verify_style_readback(
    original_document: DocumentIR,
    output_document: DocumentIR,
    edit: EditOperation,
) -> None:
    if edit.target_node_id is None:
        return
    source_node = original_document.nodes.get(edit.target_node_id)
    output_node = output_document.nodes.get(edit.target_node_id)
    if (
        source_node is None
        or output_node is None
        or not isinstance(source_node.payload, TextPayload)
        or not isinstance(output_node.payload, TextPayload)
    ):
        _fail(
            "docx.style.target_identity",
            "DOCX style target did not survive as a text node.",
            expected=edit.target_node_id,
            actual=None,
        )
    run_index, _, expected_style = validate_text_style_update(
        source_node.payload,
        edit.payload,
    )
    actual_style = _direct_style(output_node.payload, run_index)
    if actual_style != expected_style:
        _fail(
            "docx.style.readback",
            "Patched DOCX direct run style did not read back correctly.",
            expected=expected_style,
            actual=actual_style,
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
    style_edited_ids: set[str] = set()
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
        expected_value = _expected_edit_value(original_document, edit)
        actual_value = node_semantic_text(output_node)
        if actual_value != expected_value:
            _fail(
                "docx.semantic.readback",
                "Patched DOCX semantic value did not read back correctly.",
                expected=expected_value,
                actual=actual_value,
            )
        if edit.type == "set_text_style":
            _verify_style_readback(original_document, output_document, edit)
            style_edited_ids.add(edit.target_node_id)

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
        if output_node is None or node_semantic_digest(
            output_node
        ) != node_semantic_digest(node):
            changed_unrelated.append(node_id)
    if changed_unrelated:
        _fail(
            "docx.semantic.unrelated_nodes",
            "Unrelated DOCX semantic nodes changed during patch.",
            expected=[],
            actual=changed_unrelated,
        )

    evidence = [
        FidelityEvidence(
            check_code="docx.package.inventory",
            status=FidelityStatus.PASSED,
            description="DOCX package member inventory is unchanged.",
        ),
        FidelityEvidence(
            check_code="docx.package.untouched_members",
            status=FidelityStatus.PASSED,
            description=(
                "Untouched DOCX package members preserve identical uncompressed bytes."
            ),
        ),
        reopen_evidence,
        FidelityEvidence(
            check_code="docx.semantic.readback",
            status=FidelityStatus.PASSED,
            description="Requested DOCX edits read back with expected semantic values.",
            affected_node_ids=tuple(sorted(edited_ids)),
        ),
    ]
    if style_edited_ids:
        evidence.append(
            FidelityEvidence(
                check_code="docx.style.readback",
                status=FidelityStatus.PASSED,
                description="Requested DOCX direct run styles read back exactly.",
                affected_node_ids=tuple(sorted(style_edited_ids)),
            )
        )
    evidence.extend(
        [
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
        ]
    )

    return FidelityReport(claimed_tier="high", evidence=tuple(evidence))
