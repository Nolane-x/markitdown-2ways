from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest

from markitdown.twoways._errors import AmbiguousNativeLocatorError
from markitdown.twoways.ooxml import parse_xml_part

from ._docx_fixtures import build_docx_fixture


def _document_root(data: bytes):
    with ZipFile(BytesIO(data)) as archive:
        return parse_xml_part(archive.read("word/document.xml"))


def test_relationships_parse_external_hyperlink_and_image_target():
    from markitdown.twoways.formats.docx.relationships import relationships_for_part

    relationships = relationships_for_part(build_docx_fixture(), "/word/document.xml")
    external = [item for item in relationships.values() if item.external]
    assert any(item.target == "https://openai.com/" for item in external)
    images = [
        item for item in relationships.values() if "image" in item.relationship_type
    ]
    assert len(images) == 1
    assert images[0].resolved_target.startswith("/word/media/")


def test_resolve_relationship_target_rejects_escape():
    from markitdown.twoways.formats.docx.relationships import (
        resolve_relationship_target,
    )

    assert (
        resolve_relationship_target("/word/document.xml", "media/image1.png")
        == "/word/media/image1.png"
    )
    with pytest.raises(ValueError):
        resolve_relationship_target("/word/document.xml", "../../outside.bin")


def test_paragraph_locator_resolves_exact_part_and_node_id_is_text_independent():
    from markitdown.twoways.formats.docx.locators import (
        paragraph_locator,
        resolve_paragraph_element,
        stable_docx_node_id,
    )

    data = build_docx_fixture()
    root = _document_root(data)
    locator = paragraph_locator(
        "/word/document.xml",
        paragraph_index=0,
        path=(
            "/*[local-name()='document']/*[local-name()='body']"
            "/*[local-name()='p'][1]"
        ),
    )
    node_id = stable_docx_node_id(locator, "text")
    resolved = resolve_paragraph_element(root, locator, part_uri="/word/document.xml")
    assert resolved.xpath('string(.//*[local-name()="t"][1])') == "Revenue "
    assert node_id == stable_docx_node_id(locator, "text")
    with pytest.raises(AmbiguousNativeLocatorError):
        resolve_paragraph_element(root, locator, part_uri="/word/header1.xml")


def test_picture_locator_requires_unique_docpr():
    from markitdown.twoways.formats.docx.locators import (
        picture_locator,
        resolve_picture_docpr,
    )

    root = _document_root(build_docx_fixture())
    doc_pr = root.xpath('.//*[local-name()="docPr"]')[0]
    locator = picture_locator(
        "/word/document.xml",
        docpr_id=doc_pr.get("id"),
        relationship_id=None,
        path="//*[local-name()='docPr' and @id='1']",
    )
    assert (
        resolve_picture_docpr(root, locator, part_uri="/word/document.xml").get("descr")
        == "Green status pixel"
    )

    duplicate = parse_xml_part(
        b'<w:document xmlns:w="http://schemas.openxmlformats.org/'
        b'wordprocessingml/2006/main" '
        b'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/'
        b'wordprocessingDrawing">'
        b'<w:body><wp:docPr id="1"/><wp:docPr id="1"/></w:body></w:document>'
    )
    with pytest.raises(AmbiguousNativeLocatorError):
        resolve_picture_docpr(duplicate, locator, part_uri="/word/document.xml")


def test_docx_edit_preconditions_are_fail_closed():
    from io import BytesIO

    from markitdown.twoways._errors import PatchPreconditionError
    from markitdown.twoways.formats.docx import read_docx_ir
    from markitdown.twoways.formats.docx.patch import validate_edit_preconditions
    from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
    from markitdown.twoways.ir.semantics import (
        native_locator_digest,
        node_semantic_digest,
    )

    document = read_docx_ir(BytesIO(build_docx_fixture()))
    node = document.nodes[document.canvases[0].root_node_ids[0]]
    good = EditOperation(
        operation_id="docx-precondition-good",
        type="replace_text",
        target_node_id=node.node_id,
        precondition=EditPrecondition(
            expected_semantic_digest=node_semantic_digest(node),
            expected_native_locator_digest=native_locator_digest(node),
            expected_old_value="Revenue 38%",
        ),
        payload={"text": "Revenue 42%"},
    )
    validate_edit_preconditions(document, node, good)

    stale = EditOperation(
        operation_id="docx-precondition-stale",
        type="replace_text",
        target_node_id=node.node_id,
        precondition=EditPrecondition(expected_semantic_digest="0" * 64),
        payload={"text": "Revenue 42%"},
    )
    with pytest.raises(PatchPreconditionError) as exc:
        validate_edit_preconditions(document, node, stale)
    assert exc.value.details["reason"] == "semantic_digest"


def test_picture_alt_patch_changes_only_descr_attribute():
    from lxml import etree

    from markitdown.twoways.formats.docx.patch import patch_picture_alt_text

    root = _document_root(build_docx_fixture())
    docpr = root.xpath('.//*[local-name()="docPr"]')[0]
    before_id = docpr.get("id")
    before_name = docpr.get("name")
    children_before = [etree.tostring(child) for child in docpr]
    patch_picture_alt_text(docpr, new_alt_text="Updated status pixel")
    assert docpr.get("descr") == "Updated status pixel"
    assert docpr.get("id") == before_id
    assert docpr.get("name") == before_name
    assert [etree.tostring(child) for child in docpr] == children_before


def test_paragraph_resolver_does_not_execute_arbitrary_locator_xpath():
    from markitdown.twoways.formats.docx.locators import resolve_paragraph_element
    from markitdown.twoways.ir.provenance import NativeLocator

    root = _document_root(build_docx_fixture())
    locator = NativeLocator(
        backend="docx-ooxml",
        part_uri="/word/document.xml",
        object_id="paragraph:0",
        path="//*",
        attributes={"paragraph_index": 0},
    )
    with pytest.raises(AmbiguousNativeLocatorError) as exc:
        resolve_paragraph_element(root, locator, part_uri="/word/document.xml")
    assert exc.value.details["reason"] == "path_mismatch"


def test_picture_locator_rejects_foreign_docpr_namespace():
    from markitdown.twoways.formats.docx.locators import (
        picture_locator,
        resolve_picture_docpr,
    )

    root = parse_xml_part(
        b'<w:document xmlns:w="http://schemas.openxmlformats.org/'
        b'wordprocessingml/2006/main" xmlns:foreign="urn:foreign">'
        b'<w:body><foreign:docPr id="9" descr="spoof"/></w:body></w:document>'
    )
    locator = picture_locator(
        "/word/document.xml",
        docpr_id="9",
        relationship_id=None,
        path="//*[local-name()='docPr' and @id='9']",
    )
    with pytest.raises(AmbiguousNativeLocatorError) as exc:
        resolve_picture_docpr(root, locator, part_uri="/word/document.xml")
    assert exc.value.details["reason"] == "not_found"


def test_picture_locator_treats_docpr_id_as_data_not_xpath_source():
    from markitdown.twoways.formats.docx.locators import (
        picture_locator,
        resolve_picture_docpr,
    )

    root = parse_xml_part(
        b'<w:document xmlns:w="http://schemas.openxmlformats.org/'
        b'wordprocessingml/2006/main" '
        b'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/'
        b'wordprocessingDrawing">'
        b'<w:body><wp:docPr id="a&quot;b" descr="quoted"/></w:body></w:document>'
    )
    locator = picture_locator(
        "/word/document.xml",
        docpr_id='a"b',
        relationship_id=None,
        path="unused-by-picture-resolver",
    )
    resolved = resolve_picture_docpr(root, locator, part_uri="/word/document.xml")
    assert resolved.get("descr") == "quoted"
