from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from zipfile import ZipFile

import pytest

from markitdown.twoways import (
    AmbiguousNativeLocatorError,
    EditOperation,
    EditPrecondition,
    NativeLocator,
    PatchPreconditionError,
    TextPayload,
)
from markitdown.twoways.ir.semantics import (
    native_locator_digest,
    node_semantic_digest,
    node_semantic_text,
)
from markitdown.twoways.ooxml import parse_xml_part

from ._pptx_fixtures import make_pptx_bytes


def _text_node(document, text="Revenue 38%"):
    for node in document.nodes.values():
        if isinstance(node.payload, TextPayload) and node.payload.text == text:
            return node
    raise AssertionError("target text node not found")


def _slide_root(source: bytes, name="ppt/slides/slide1.xml"):
    with ZipFile(BytesIO(source)) as archive:
        return parse_xml_part(archive.read(name))


def test_resolver_finds_exact_shape_by_object_id_in_designated_part():
    from markitdown.twoways.formats.pptx import read_pptx_ir
    from markitdown.twoways.formats.pptx.locators import resolve_shape_element

    source = make_pptx_bytes()
    document = read_pptx_ir(BytesIO(source))
    node = _text_node(document)
    shape = resolve_shape_element(
        _slide_root(source),
        node.native_locator,
        part_uri="/ppt/slides/slide1.xml",
    )
    assert shape.tag.endswith("}sp")


def test_resolver_rejects_wrong_part_and_name_only_authority():
    from markitdown.twoways.formats.pptx import read_pptx_ir
    from markitdown.twoways.formats.pptx.locators import resolve_shape_element

    source = make_pptx_bytes()
    node = _text_node(read_pptx_ir(BytesIO(source)))

    with pytest.raises(AmbiguousNativeLocatorError) as exc:
        resolve_shape_element(
            _slide_root(source),
            node.native_locator,
            part_uri="/ppt/slides/slide2.xml",
        )
    assert exc.value.details["reason"] == "part_mismatch"

    name_only = NativeLocator(
        backend="pptx-ooxml",
        part_uri="/ppt/slides/slide1.xml",
        name=node.native_locator.name,
    )
    with pytest.raises(AmbiguousNativeLocatorError) as exc:
        resolve_shape_element(
            _slide_root(source),
            name_only,
            part_uri="/ppt/slides/slide1.xml",
        )
    assert exc.value.details["reason"] == "insufficient_identity"


def test_resolver_requires_creation_and_object_id_to_agree():
    from lxml import etree

    from markitdown.twoways.formats.pptx.locators import resolve_shape_element

    root = _slide_root(make_pptx_bytes())
    c_nv_pr = root.xpath('//*[local-name()="cNvPr" and @id="3"]')[0]
    creation = etree.SubElement(c_nv_pr, "{http://schemas.microsoft.com/office/drawing/2014/main}creationId")
    creation.set("id", "{GOOD}")

    good = NativeLocator(
        backend="pptx-ooxml",
        part_uri="/ppt/slides/slide1.xml",
        object_id="3",
        creation_id="{GOOD}",
    )
    assert resolve_shape_element(root, good, part_uri=good.part_uri).tag.endswith("}sp")

    mismatch = replace(good, object_id="2")
    with pytest.raises(AmbiguousNativeLocatorError) as exc:
        resolve_shape_element(root, mismatch, part_uri=good.part_uri)
    assert exc.value.details["reason"] == "identity_mismatch"


def test_edit_preconditions_match_shared_core_semantics():
    from markitdown.twoways.formats.pptx import read_pptx_ir
    from markitdown.twoways.formats.pptx.patch import validate_edit_preconditions

    document = read_pptx_ir(BytesIO(make_pptx_bytes()))
    node = _text_node(document)
    edit = EditOperation(
        operation_id="edit-1",
        type="replace_text",
        target_node_id=node.node_id,
        precondition=EditPrecondition(
            expected_semantic_digest=node_semantic_digest(node),
            expected_native_locator_digest=native_locator_digest(node),
            expected_old_value=node_semantic_text(node),
        ),
        payload={"text": "Revenue 42%"},
    )
    validate_edit_preconditions(document, node, edit)


def test_stale_semantic_locator_and_old_value_preconditions_fail_closed():
    from markitdown.twoways.formats.pptx import read_pptx_ir
    from markitdown.twoways.formats.pptx.patch import validate_edit_preconditions

    document = read_pptx_ir(BytesIO(make_pptx_bytes()))
    node = _text_node(document)
    cases = [
        EditPrecondition(expected_semantic_digest="0" * 64),
        EditPrecondition(expected_native_locator_digest="1" * 64),
        EditPrecondition(expected_old_value="stale"),
    ]
    for index, precondition in enumerate(cases):
        edit = EditOperation(
            operation_id=f"stale-{index}",
            type="replace_text",
            target_node_id=node.node_id,
            precondition=precondition,
            payload={"text": "Revenue 42%"},
        )
        with pytest.raises(PatchPreconditionError):
            validate_edit_preconditions(document, node, edit)
