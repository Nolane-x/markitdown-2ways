from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest

from markitdown.twoways import PatchPreconditionError, UnsupportedEditError
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.semantics import native_locator_digest, node_semantic_digest
from markitdown.twoways.ooxml import parse_xml_part

from ._pptx_fixtures import make_pptx_bytes


_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _slide_root(source: bytes):
    with ZipFile(BytesIO(source), "r") as archive:
        return parse_xml_part(archive.read("ppt/slides/slide1.xml"))


def _shape(root, object_id: str = "3"):
    from markitdown.twoways import NativeLocator
    from markitdown.twoways.formats.pptx.locators import resolve_shape_element

    locator = NativeLocator(
        backend="pptx-ooxml",
        part_uri="/ppt/slides/slide1.xml",
        object_id=object_id,
    )
    return resolve_shape_element(root, locator, part_uri=locator.part_uri)


def _runs(shape):
    return shape.xpath('.//*[local-name()="p"]/*[local-name()="r"]')


def _direct_style(node, run_index: int) -> dict[str, object]:
    runs = tuple(run for paragraph in node.payload.paragraphs for run in paragraph.runs)
    style = runs[run_index].style
    direct = {} if style is None else dict(style.direct)
    color = direct.get("color")
    if isinstance(color, str):
        direct["color"] = color.upper()
    size = direct.get("font_size_pt")
    if type(size) in {int, float}:
        direct["font_size_pt"] = float(size)
    underline = direct.get("underline")
    if underline is True:
        direct["underline"] = "single"
    elif underline is False:
        direct["underline"] = "none"
    return direct


def _patch(shape, *, run_index: int, old_style, new_style):
    try:
        from markitdown.twoways.formats.pptx.style import patch_text_run_style
    except ModuleNotFoundError:
        pytest.fail("PPTX style patcher is not implemented yet")
    patch_text_run_style(
        shape,
        run_index=run_index,
        old_style=old_style,
        new_style=new_style,
    )


def test_patch_pptx_run_style_changes_only_target_rpr():
    from lxml import etree

    root = _slide_root(make_pptx_bytes())
    shape = _shape(root)
    first, second = _runs(shape)
    first_text_before = first.xpath('./*[local-name()="t"]/text()')
    second_before = etree.tostring(second)

    _patch(
        shape,
        run_index=0,
        old_style={
            "bold": True,
            "font_size_pt": 24.0,
            "font_family": "Aptos",
            "color": "#0A141E",
        },
        new_style={
            "bold": False,
            "italic": True,
            "underline": "double",
            "font_size_pt": 26.5,
            "font_family": "Aptos Display",
            "color": "#336699",
        },
    )

    first_after, second_after = _runs(shape)
    assert first_after.xpath('./*[local-name()="t"]/text()') == first_text_before
    assert etree.tostring(second_after) == second_before
    rpr = first_after.xpath('./*[local-name()="rPr"]')[0]
    assert rpr.get("b") == "0"
    assert rpr.get("i") == "1"
    assert rpr.get("u") == "dbl"
    assert rpr.get("sz") == "2650"
    assert rpr.xpath('./*[local-name()="latin"]')[0].get("typeface") == "Aptos Display"
    assert (
        rpr.xpath('./*[local-name()="solidFill"]/*[local-name()="srgbClr"]')[0].get(
            "val"
        )
        == "336699"
    )


def test_patch_pptx_run_style_rejects_stale_native_style():
    root = _slide_root(make_pptx_bytes())
    with pytest.raises(PatchPreconditionError) as exc:
        _patch(
            _shape(root),
            run_index=0,
            old_style={"bold": False},
            new_style={"bold": True},
        )
    assert exc.value.details["reason"] == "run_style_mismatch"


def test_patch_pptx_run_style_rejects_field_layout():
    from lxml import etree

    root = _slide_root(make_pptx_bytes())
    shape = _shape(root)
    paragraph = shape.xpath('.//*[local-name()="p"]')[0]
    paragraph.insert(0, etree.Element(f"{{{_A_NS}}}fld"))
    with pytest.raises(UnsupportedEditError) as exc:
        _patch(
            shape,
            run_index=0,
            old_style={},
            new_style={"bold": True},
        )
    assert exc.value.details["reason"] == "pptx.text.ambiguous_run_layout"


def test_patch_pptx_run_style_rejects_theme_color_replacement():
    from lxml import etree

    root = _slide_root(make_pptx_bytes())
    shape = _shape(root)
    first = _runs(shape)[0]
    rpr = first.xpath('./*[local-name()="rPr"]')[0]
    solid = rpr.xpath('./*[local-name()="solidFill"]')[0]
    for child in tuple(solid):
        solid.remove(child)
    solid.append(etree.Element(f"{{{_A_NS}}}schemeClr", val="accent1"))

    with pytest.raises(UnsupportedEditError) as exc:
        _patch(
            shape,
            run_index=0,
            old_style={"bold": True, "font_size_pt": 24.0, "font_family": "Aptos"},
            new_style={
                "bold": True,
                "font_size_pt": 24.0,
                "font_family": "Aptos",
                "color": "#112233",
            },
        )
    assert (
        exc.value.details["reason"] == "pptx.style.theme_color_requires_explicit_edit"
    )


def test_pptx_writer_roundtrips_direct_run_style_without_changing_text():
    from markitdown.twoways.formats.pptx import patch_pptx, read_pptx_ir

    source = make_pptx_bytes()
    document = read_pptx_ir(BytesIO(source))
    node = next(
        node
        for node in document.nodes.values()
        if node.kind == "text" and node.payload.text == "Revenue 38%"
    )
    assert _direct_style(node, 0) == {
        "bold": True,
        "font_size_pt": 24.0,
        "font_family": "Aptos",
        "color": "#0A141E",
    }

    edit = EditOperation(
        operation_id="pptx-style-run-0",
        type="set_text_style",
        target_node_id=node.node_id,
        precondition=EditPrecondition(
            expected_semantic_digest=node_semantic_digest(node),
            expected_native_locator_digest=native_locator_digest(node),
            expected_old_value=node.payload.text,
        ),
        payload={
            "run_index": 0,
            "old_style": _direct_style(node, 0),
            "style": {
                "bold": False,
                "italic": True,
                "underline": "double",
                "font_size_pt": 26.5,
                "font_family": "Aptos Display",
                "color": "#336699",
            },
        },
    )
    output = BytesIO()
    result = patch_pptx(document, BytesIO(source), output, edits=(edit,))

    reread = read_pptx_ir(BytesIO(output.getvalue()))
    updated = reread.nodes[node.node_id]
    assert updated.payload.text == node.payload.text
    assert _direct_style(updated, 0) == {
        "bold": False,
        "italic": True,
        "underline": "double",
        "font_size_pt": 26.5,
        "font_family": "Aptos Display",
        "color": "#336699",
    }
    assert _direct_style(updated, 1) == {"italic": True, "font_size_pt": 24.0}
    assert result.metadata["touched_parts"] == ("ppt/slides/slide1.xml",)
    assert result.fidelity.claimed_tier == "high"
