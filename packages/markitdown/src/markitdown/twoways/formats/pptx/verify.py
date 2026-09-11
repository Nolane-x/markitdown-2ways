from __future__ import annotations

from io import BytesIO
from typing import Iterable
from zipfile import ZipFile

from ..._errors import RoundTripVerificationError
from ..._results import FidelityEvidence, FidelityReport, FidelityStatus
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.semantics import node_semantic_digest, node_semantic_text
from .locators import resolve_shape_element
from ...ooxml import OOXMLPackageLimits, parse_xml_part
from ...ooxml.package import inspect_package_preservation


def _fail(check: str, message: str, *, expected=None, actual=None) -> None:
    raise RoundTripVerificationError(
        message,
        details={
            "check": check,
            "expected": expected,
            "actual": actual,
        },
    )


def _edited_nodes_and_ancestors(
    document: DocumentIR,
    edited_ids: set[str],
) -> set[str]:
    excluded = set(edited_ids)
    for node_id in tuple(edited_ids):
        current = document.nodes.get(node_id)
        while current is not None and current.parent_id is not None:
            excluded.add(current.parent_id)
            current = document.nodes.get(current.parent_id)
    return excluded


def _canonical_subtree(element) -> bytes:
    from lxml import etree

    return etree.tostring(element, method="c14n", with_comments=True)


def _verify_unrelated_native_subtrees(
    document: DocumentIR,
    source_bytes: bytes,
    output_bytes: bytes,
    *,
    touched_parts: tuple[str, ...],
    edited_ids: set[str],
) -> None:
    touched_uris = {f"/{name.lstrip('/')}" for name in touched_parts}
    if not touched_uris:
        return
    excluded = _edited_nodes_and_ancestors(document, edited_ids)
    with ZipFile(BytesIO(source_bytes), "r") as before_zip, ZipFile(
        BytesIO(output_bytes), "r"
    ) as after_zip:
        roots: dict[str, tuple[object, object]] = {}
        for part_uri in sorted(touched_uris):
            archive_name = part_uri.lstrip("/")
            roots[part_uri] = (
                parse_xml_part(before_zip.read(archive_name)),
                parse_xml_part(after_zip.read(archive_name)),
            )

    changed: list[str] = []
    for node_id, node in document.nodes.items():
        locator = node.native_locator
        if (
            node_id in excluded
            or locator is None
            or locator.part_uri not in touched_uris
        ):
            continue
        before_root, after_root = roots[locator.part_uri]
        before_shape = resolve_shape_element(
            before_root,
            locator,
            part_uri=locator.part_uri,
            strict=True,
        )
        after_shape = resolve_shape_element(
            after_root,
            locator,
            part_uri=locator.part_uri,
            strict=True,
        )
        if _canonical_subtree(before_shape) != _canonical_subtree(after_shape):
            changed.append(node_id)

    if changed:
        _fail(
            "native.unrelated_subtrees",
            "Unrelated PPTX native shape subtrees changed during patch.",
            expected=[],
            actual=sorted(changed),
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
    preservation = inspect_package_preservation(
        source_bytes,
        output_bytes,
        touched_parts=touched_parts,
        limits=limits,
    )
    if not preservation.inventory_matches:
        _fail(
            "package.inventory",
            "PPTX package inventory changed during patch.",
            expected=preservation.before_names,
            actual=preservation.after_names,
        )
    if preservation.changed_untouched:
        _fail(
            "package.untouched_members",
            "Untouched PPTX package members changed during patch.",
            expected=[],
            actual=list(preservation.changed_untouched),
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
        if (
            edit.target_node_id is None
            or edit.target_node_id not in output_document.nodes
        ):
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

    _verify_unrelated_native_subtrees(
        original_document,
        source_bytes,
        output_bytes,
        touched_parts=touched_parts,
        edited_ids=edited_ids,
    )

    changed_unrelated: list[str] = []
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
            check_code="native.unrelated_subtrees",
            status=FidelityStatus.PASSED,
            description="Unedited native shape subtrees in touched parts remain canonically identical.",
        ),
        FidelityEvidence(
            check_code="semantic.unrelated_nodes",
            status=FidelityStatus.PASSED,
            description="Unedited semantic nodes retain identical semantic digests.",
        ),
    )
    return FidelityReport(claimed_tier="high", evidence=evidence)
