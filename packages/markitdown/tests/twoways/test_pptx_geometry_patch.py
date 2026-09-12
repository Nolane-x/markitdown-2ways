from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest

from markitdown.twoways import PatchPreconditionError, UnsupportedEditError
from markitdown.twoways.ir.edits import EditOperation
from markitdown.twoways.ir.geometry import Geometry
from markitdown.twoways.ir.semantics import node_semantic_text
from markitdown.twoways.ooxml import parse_xml_part

from ._pptx_fixtures import make_grouped_pptx_bytes, make_pptx_bytes


def _shape(source: bytes, object_id: str = "3"):
    from markitdown.twoways import NativeLocator
    from markitdown.twoways.formats.pptx.locators import resolve_shape_element

    with ZipFile(BytesIO(source), "r") as archive:
        root = parse_xml_part(archive.read("ppt/slides/slide1.xml"))
    locator = NativeLocator(
        backend="pptx-ooxml",
        part_uri="/ppt/slides/slide1.xml",
        object_id=object_id,
    )
    return resolve_shape_element(root, locator, part_uri=locator.part_uri)


def _native_geometry(shape) -> tuple[int, int, int, int]:
    xfrm = shape.xpath('.//*[local-name()="xfrm"]')
    assert len(xfrm) == 1
    off = xfrm[0].xpath('./*[local-name()="off"]')
    ext = xfrm[0].xpath('./*[local-name()="ext"]')
    assert len(off) == len(ext) == 1
    return (
        int(off[0].get("x")),
        int(off[0].get("y")),
        int(ext[0].get("cx")),
        int(ext[0].get("cy")),
    )


def _patch(shape, current: Geometry, target: Geometry) -> None:
    try:
        from markitdown.twoways.formats.pptx.geometry import patch_shape_geometry
    except ModuleNotFoundError:
        pytest.fail("PPTX geometry patcher is not implemented yet")
    patch_shape_geometry(shape, current=current, target=target)


def _move_edit(node) -> EditOperation:
    assert node.geometry is not None
    return EditOperation(
        operation_id="pptx-move-resize-revenue",
        type="move_resize",
        target_node_id=node.node_id,
        payload={
            "x": node.geometry.x + 914400,
            "y": node.geometry.y + 457200,
            "width": node.geometry.width + 914400,
            "height": node.geometry.height + 457200,
        },
    )


def test_patch_shape_geometry_changes_only_native_coordinates():
    from lxml import etree

    shape = _shape(make_pptx_bytes())
    x, y, width, height = _native_geometry(shape)
    current = Geometry(x=x, y=y, width=width, height=height, unit="emu")
    target = Geometry(
        x=x + 914400,
        y=y + 457200,
        width=width + 914400,
        height=height + 457200,
        unit="emu",
    )
    text_before = tuple(shape.xpath('.//*[local-name()="t"]/text()'))
    xfrm = shape.xpath('.//*[local-name()="xfrm"]')[0]
    attrs_before = dict(xfrm.attrib)
    before = etree.tostring(shape)

    _patch(shape, current, target)

    assert _native_geometry(shape) == tuple(
        int(value) for value in (target.x, target.y, target.width, target.height)
    )
    assert tuple(shape.xpath('.//*[local-name()="t"]/text()')) == text_before
    assert dict(xfrm.attrib) == attrs_before
    assert etree.tostring(shape) != before


def test_patch_shape_geometry_rejects_stale_and_fractional_emu():
    shape = _shape(make_pptx_bytes())
    x, y, width, height = _native_geometry(shape)
    current = Geometry(x=x, y=y, width=width, height=height, unit="emu")
    with pytest.raises(PatchPreconditionError) as stale:
        _patch(
            shape,
            Geometry(x=x + 1, y=y, width=width, height=height, unit="emu"),
            Geometry(x=x + 2, y=y, width=width, height=height, unit="emu"),
        )
    assert stale.value.details["reason"] == "native_geometry_mismatch"

    with pytest.raises(UnsupportedEditError) as fractional:
        _patch(
            shape,
            current,
            Geometry(x=x + 0.5, y=y, width=width, height=height, unit="emu"),
        )
    assert fractional.value.details["reason"] == "pptx.geometry.unrepresentable_emu"


def test_pptx_writer_roundtrips_move_resize_without_semantic_change():
    from markitdown.twoways.formats.pptx import patch_pptx, read_pptx_ir

    source = make_pptx_bytes()
    document = read_pptx_ir(BytesIO(source))
    node = next(
        item
        for item in document.nodes.values()
        if item.kind == "text" and item.payload.text == "Revenue 38%"
    )
    edit = _move_edit(node)
    output = BytesIO()
    result = patch_pptx(document, BytesIO(source), output, edits=(edit,))
    reread = read_pptx_ir(BytesIO(output.getvalue()))
    updated = reread.nodes[node.node_id]

    assert node_semantic_text(updated) == node_semantic_text(node)
    assert updated.geometry is not None
    assert (
        updated.geometry.x,
        updated.geometry.y,
        updated.geometry.width,
        updated.geometry.height,
    ) == (
        edit.payload["x"],
        edit.payload["y"],
        edit.payload["width"],
        edit.payload["height"],
    )
    assert result.metadata["touched_parts"] == ("ppt/slides/slide1.xml",)
    assert result.fidelity.claimed_tier == "high"


def test_pptx_writer_rejects_group_child_geometry_edits():
    from markitdown.twoways.formats.pptx import patch_pptx, read_pptx_ir

    source = make_grouped_pptx_bytes()
    document = read_pptx_ir(BytesIO(source))
    child = next(node for node in document.nodes.values() if node.parent_id is not None)
    assert child.geometry is not None
    edit = EditOperation(
        operation_id="pptx-group-child-move",
        type="move_resize",
        target_node_id=child.node_id,
        payload={"x": child.geometry.x + 914400},
    )
    output = BytesIO()
    with pytest.raises(UnsupportedEditError) as exc:
        patch_pptx(document, BytesIO(source), output, edits=(edit,))
    assert exc.value.details["reason"] == "pptx.geometry.group_coordinate_space"
    assert output.getvalue() == b""


def test_pptx_geometry_verifier_rejects_extra_native_target_mutation(monkeypatch):
    from markitdown.twoways import RoundTripVerificationError
    from markitdown.twoways.formats.pptx import patch_pptx, read_pptx_ir
    from markitdown.twoways.formats.pptx import writer as writer_module

    source = make_pptx_bytes()
    document = read_pptx_ir(BytesIO(source))
    node = next(
        item
        for item in document.nodes.values()
        if item.kind == "text" and item.payload.text == "Revenue 38%"
    )
    edit = _move_edit(node)
    original = writer_module.patch_shape_geometry

    def tampering_patch(shape_element, **kwargs):
        original(shape_element, **kwargs)
        xfrm = shape_element.xpath('.//*[local-name()="xfrm"]')[0]
        xfrm.set("flipH", "1")

    monkeypatch.setattr(writer_module, "patch_shape_geometry", tampering_patch)
    output = BytesIO()
    with pytest.raises(RoundTripVerificationError) as exc:
        patch_pptx(document, BytesIO(source), output, edits=(edit,))
    assert exc.value.details["check"] == "native.target_structure"
    assert output.getvalue() == b""
