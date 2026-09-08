from __future__ import annotations

from io import BytesIO
from typing import Iterable

from ..._errors import RoundTripVerificationError
from ..._results import FidelityEvidence, FidelityReport, FidelityStatus
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.semantics import node_semantic_digest, node_semantic_text
from ...ooxml import OOXMLPackageLimits, snapshot_package


def _fail(check: str, message: str, *, expected=None, actual=None) -> None:
    raise RoundTripVerificationError(
        message,
        details={
            "check": check,
            "expected": expected,
            "actual": actual,
        },
    )


def verify_pptx_output(
    original_document: DocumentIR,
    source_bytes: bytes,
    output_bytes: bytes,
    *,
    edits: Iterable[EditOperation],
    touched_parts: tuple[str, ...],
    limits: OOXMLPackageLimits,
) -> FidelityReport:
    before = snapshot_package(source_bytes, limits=limits)
    after = snapshot_package(output_bytes, limits=limits)
    before_names = tuple(entry.name for entry in before.entries)
    after_names = tuple(entry.name for entry in after.entries)
    if before_names != after_names:
        _fail("package.inventory", "PPTX package inventory changed during patch.", expected=before_names, actual=after_names)

    touched = set(touched_parts)
    after_by_name = after.entry_by_name
    changed_untouched: list[str] = []
    for entry in before.entries:
        if entry.name in touched:
            continue
        if after_by_name[entry.name].uncompressed_sha256 != entry.uncompressed_sha256:
            changed_untouched.append(entry.name)
    if changed_untouched:
        _fail(
            "package.untouched_members",
            "Untouched PPTX package members changed during patch.",
            expected=[],
            actual=changed_untouched,
        )

    try:
        from pptx import Presentation

        Presentation(BytesIO(output_bytes))
    except Exception as exc:
        raise RoundTripVerificationError(
            "Patched PPTX cannot be reopened by python-pptx.",
            details={"check": "pptx.reopen", "error": repr(exc)},
        ) from exc

    from .reader import read_pptx_ir

    output_document = read_pptx_ir(BytesIO(output_bytes))
    edit_list = tuple(edits)
    edited_ids = {edit.target_node_id for edit in edit_list if edit.target_node_id}

    for edit in edit_list:
        if edit.target_node_id is None or edit.target_node_id not in output_document.nodes:
            _fail(
                "semantic.target_identity",
                "Edited PPTX node identity did not survive round trip.",
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
                "semantic.readback",
                "Patched PPTX semantic value did not read back correctly.",
                expected=expected_value,
                actual=actual_value,
            )

    changed_unrelated: list[str] = []
    for node_id, node in original_document.nodes.items():
        if node_id in edited_ids:
            continue
        output_node = output_document.nodes.get(node_id)
        if output_node is None or node_semantic_digest(output_node) != node_semantic_digest(node):
            changed_unrelated.append(node_id)
    if changed_unrelated:
        _fail(
            "semantic.unrelated_nodes",
            "Unrelated PPTX semantic nodes changed during patch.",
            expected=[],
            actual=changed_unrelated,
        )

    evidence = (
        FidelityEvidence(
            check_code="package.inventory",
            status=FidelityStatus.PASSED,
            description="PPTX package member inventory is unchanged.",
        ),
        FidelityEvidence(
            check_code="package.untouched_members",
            status=FidelityStatus.PASSED,
            description="Untouched package members preserve identical uncompressed bytes.",
        ),
        FidelityEvidence(
            check_code="pptx.reopen",
            status=FidelityStatus.PASSED,
            description="Patched PPTX reopens successfully with python-pptx.",
        ),
        FidelityEvidence(
            check_code="semantic.readback",
            status=FidelityStatus.PASSED,
            description="Requested edits read back with the expected semantic values.",
            affected_node_ids=tuple(sorted(edited_ids)),
        ),
        FidelityEvidence(
            check_code="semantic.unrelated_nodes",
            status=FidelityStatus.PASSED,
            description="Unedited semantic nodes retain identical semantic digests.",
        ),
    )
    return FidelityReport(claimed_tier="high", evidence=evidence)
