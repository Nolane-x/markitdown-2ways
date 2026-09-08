from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import posixpath
from typing import Iterable
from zipfile import ZipFile

from ..._errors import RoundTripVerificationError
from ..._results import FidelityEvidence, FidelityReport, FidelityStatus
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.semantics import node_semantic_digest, node_semantic_text
from ...ooxml import OOXMLPackageLimits, parse_xml_part, snapshot_package
from .locators import (
    resolve_paragraph_element,
    resolve_picture_docpr,
    resolve_table_element,
)

_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def _fail(check: str, message: str, *, expected=None, actual=None) -> None:
    raise RoundTripVerificationError(
        message,
        details={"check": check, "expected": expected, "actual": actual},
    )


def _canonical_subtree(element) -> bytes:
    from lxml import etree

    return etree.tostring(element, method="c14n", with_comments=True)


def _picture_container(docpr):
    current = docpr
    while current is not None:
        if current.tag.rsplit("}", 1)[-1] in {"inline", "anchor"}:
            return current
        current = current.getparent()
    return docpr


def _resolve_node_subtree(root, node, *, part_uri: str):
    locator = node.native_locator
    if locator is None:
        return None
    if node.kind == "text":
        return resolve_paragraph_element(root, locator, part_uri=part_uri)
    if node.kind == "image":
        return _picture_container(
            resolve_picture_docpr(root, locator, part_uri=part_uri)
        )
    if node.kind == "table":
        return resolve_table_element(root, locator, part_uri=part_uri)
    return None


def _normalized_target_structure(element, *, kind: str, edit_type: str) -> bytes:
    clone = deepcopy(element)
    if edit_type == "replace_text":
        for text_node in clone.xpath('.//*[local-name()="t"]'):
            text_node.text = ""
            text_node.attrib.pop(_XML_SPACE, None)
    elif edit_type == "set_alt_text":
        docprs = clone.xpath('.//*[local-name()="docPr"]')
        if not docprs and clone.tag.rsplit("}", 1)[-1] == "docPr":
            docprs = [clone]
        for docpr in docprs:
            docpr.set("descr", "")
    return _canonical_subtree(clone)


def _roots_for_touched_parts(
    source_bytes: bytes,
    output_bytes: bytes,
    touched_parts: tuple[str, ...],
):
    roots = {}
    with ZipFile(BytesIO(source_bytes), "r") as before_zip, ZipFile(
        BytesIO(output_bytes), "r"
    ) as after_zip:
        for archive_name in touched_parts:
            part_uri = f"/{archive_name.lstrip('/')}"
            roots[part_uri] = (
                parse_xml_part(before_zip.read(archive_name)),
                parse_xml_part(after_zip.read(archive_name)),
            )
    return roots


def _verify_native_subtrees(
    document: DocumentIR,
    source_bytes: bytes,
    output_bytes: bytes,
    *,
    edits: tuple[EditOperation, ...],
    touched_parts: tuple[str, ...],
) -> None:
    roots = _roots_for_touched_parts(source_bytes, output_bytes, touched_parts)
    edited = {edit.target_node_id: edit for edit in edits if edit.target_node_id}
    changed_unrelated: list[str] = []
    target_structure_changed: list[str] = []

    for node_id, node in document.nodes.items():
        locator = node.native_locator
        if locator is None or locator.part_uri not in roots:
            continue
        before_root, after_root = roots[locator.part_uri]
        before_subtree = _resolve_node_subtree(before_root, node, part_uri=locator.part_uri)
        after_subtree = _resolve_node_subtree(after_root, node, part_uri=locator.part_uri)
        if before_subtree is None or after_subtree is None:
            continue
        edit = edited.get(node_id)
        if edit is None:
            if _canonical_subtree(before_subtree) != _canonical_subtree(after_subtree):
                changed_unrelated.append(node_id)
            continue
        before_structure = _normalized_target_structure(
            before_subtree,
            kind=node.kind,
            edit_type=edit.type,
        )
        after_structure = _normalized_target_structure(
            after_subtree,
            kind=node.kind,
            edit_type=edit.type,
        )
        if before_structure != after_structure:
            target_structure_changed.append(node_id)

    if changed_unrelated:
        _fail(
            "docx.native.unrelated_subtrees",
            "Unrelated DOCX native subtrees changed during patch.",
            expected=[],
            actual=sorted(changed_unrelated),
        )
    if target_structure_changed:
        _fail(
            "docx.native.target_structure",
            "DOCX target native wrapper structure changed beyond the permitted value mutation.",
            expected=[],
            actual=sorted(target_structure_changed),
        )


def _rels_member_for_part(part_uri: str) -> str:
    member = part_uri.lstrip("/")
    directory, filename = posixpath.split(member)
    return posixpath.join(directory, "_rels", f"{filename}.rels")


def _verify_relationships_and_media(
    source_bytes: bytes,
    output_bytes: bytes,
    *,
    touched_parts: tuple[str, ...],
) -> None:
    with ZipFile(BytesIO(source_bytes), "r") as before_zip, ZipFile(
        BytesIO(output_bytes), "r"
    ) as after_zip:
        before_names = set(before_zip.namelist())
        after_names = set(after_zip.namelist())
        for touched in touched_parts:
            rels_name = _rels_member_for_part(f"/{touched.lstrip('/')}")
            before = before_zip.read(rels_name) if rels_name in before_names else None
            after = after_zip.read(rels_name) if rels_name in after_names else None
            if before != after:
                _fail(
                    "docx.hyperlinks.relationships",
                    "DOCX relationships changed during text/value patch.",
                    expected="unchanged",
                    actual=rels_name,
                )
        media_names = sorted(name for name in before_names if name.startswith("word/media/"))
        if media_names != sorted(name for name in after_names if name.startswith("word/media/")):
            _fail(
                "docx.media.unchanged",
                "DOCX media inventory changed during patch.",
            )
        changed_media = [
            name for name in media_names if before_zip.read(name) != after_zip.read(name)
        ]
        if changed_media:
            _fail(
                "docx.media.unchanged",
                "DOCX media bytes changed during text/alt-text patch.",
                expected=[],
                actual=changed_media,
            )


def _reopen_evidence(output_bytes: bytes) -> FidelityEvidence:
    try:
        from docx import Document
    except (ImportError, ModuleNotFoundError):
        return FidelityEvidence(
            check_code="docx.reopen",
            status=FidelityStatus.NOT_APPLICABLE,
            description="python-docx is not installed; reopen oracle was not applicable.",
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
    before = snapshot_package(source_bytes, limits=limits)
    after = snapshot_package(output_bytes, limits=limits)
    before_names = tuple(entry.name for entry in before.entries)
    after_names = tuple(entry.name for entry in after.entries)
    if before_names != after_names:
        _fail(
            "docx.package.inventory",
            "DOCX package inventory changed during patch.",
            expected=before_names,
            actual=after_names,
        )

    touched = set(touched_parts)
    after_by_name = after.entry_by_name
    changed_untouched = [
        entry.name
        for entry in before.entries
        if entry.name not in touched
        and after_by_name[entry.name].uncompressed_sha256 != entry.uncompressed_sha256
    ]
    if changed_untouched:
        _fail(
            "docx.package.untouched_members",
            "Untouched DOCX package members changed during patch.",
            expected=[],
            actual=changed_untouched,
        )

    reopen_evidence = _reopen_evidence(output_bytes)

    from .reader import read_docx_ir

    output_document = read_docx_ir(BytesIO(output_bytes))
    edit_list = tuple(edits)
    edited_ids = {edit.target_node_id for edit in edit_list if edit.target_node_id}
    for edit in edit_list:
        if edit.target_node_id is None or edit.target_node_id not in output_document.nodes:
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
        if output_node is None or node_semantic_digest(output_node) != node_semantic_digest(node):
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
                description="Untouched DOCX package members preserve identical uncompressed bytes.",
            ),
            reopen_evidence,
            FidelityEvidence(
                check_code="docx.semantic.readback",
                status=FidelityStatus.PASSED,
                description="Requested DOCX edits read back with expected semantic values.",
                affected_node_ids=tuple(sorted(edited_ids)),
            ),
            FidelityEvidence(
                check_code="docx.native.unrelated_subtrees",
                status=FidelityStatus.PASSED,
                description="Unedited native DOCX subtrees in touched parts remain canonically identical.",
            ),
            FidelityEvidence(
                check_code="docx.native.target_structure",
                status=FidelityStatus.PASSED,
                description="Edited DOCX native wrappers preserve their structure outside permitted values.",
                affected_node_ids=tuple(sorted(edited_ids)),
            ),
            FidelityEvidence(
                check_code="docx.hyperlinks.relationships",
                status=FidelityStatus.PASSED,
                description="DOCX relationship parts remain unchanged during text/value patching.",
            ),
            FidelityEvidence(
                check_code="docx.media.unchanged",
                status=FidelityStatus.PASSED,
                description="DOCX media inventory and bytes remain unchanged.",
            ),
            FidelityEvidence(
                check_code="docx.semantic.unrelated_nodes",
                status=FidelityStatus.PASSED,
                description="Unedited DOCX semantic nodes retain identical semantic digests.",
            ),
        ),
    )
