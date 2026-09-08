from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest

from markitdown.twoways import NativeLocator, UnsupportedEditError
from markitdown.twoways.ooxml import parse_xml_part

from ._pptx_fixtures import make_pptx_bytes


def _slide_root(source: bytes):
    with ZipFile(BytesIO(source)) as archive:
        return parse_xml_part(archive.read("ppt/slides/slide1.xml"))


def _shape(root, object_id: str):
    from markitdown.twoways.formats.pptx.locators import resolve_shape_element

    locator = NativeLocator(
        backend="pptx-ooxml",
        part_uri="/ppt/slides/slide1.xml",
        object_id=object_id,
    )
    return resolve_shape_element(root, locator, part_uri=locator.part_uri)


def _run_property_bytes(shape):
    from lxml import etree

    values = []
    for run in shape.xpath('.//*[local-name()="r"]'):
        rpr = next((child for child in run if child.tag.endswith("}rPr")), None)
        values.append(None if rpr is None else etree.tostring(rpr))
    return values


def _run_texts(shape):
    return [node.text or "" for node in shape.xpath('.//*[local-name()="r"]/*[local-name()="t"]')]


def test_replace_text_preserves_run_elements_and_run_properties():
    from markitdown.twoways.formats.pptx.text import patch_text_shape

    root = _slide_root(make_pptx_bytes())
    shape = _shape(root, "3")
    before_rpr = _run_property_bytes(shape)
    before_run_count = len(shape.xpath('.//*[local-name()="r"]'))

    patch_text_shape(shape, old_text="Revenue 38%", new_text="Revenue 42%")

    assert len(shape.xpath('.//*[local-name()="r"]')) == before_run_count
    assert _run_property_bytes(shape) == before_rpr
    assert "".join(_run_texts(shape)) == "Revenue 42%"
    assert _run_texts(shape)[0] == "Revenue "
    assert _run_texts(shape)[1] == "42%"


def test_replace_text_insertion_uses_nearest_existing_style_context():
    from markitdown.twoways.formats.pptx.text import patch_text_shape

    root = _slide_root(make_pptx_bytes())
    shape = _shape(root, "3")
    patch_text_shape(shape, old_text="Revenue 38%", new_text="Revenue FY 38%")

    assert "".join(_run_texts(shape)) == "Revenue FY 38%"
    assert _run_texts(shape) == ["Revenue FY ", "38%"]


def test_paragraph_count_change_is_rejected_without_mutation():
    from lxml import etree

    from markitdown.twoways.formats.pptx.text import patch_text_shape

    root = _slide_root(make_pptx_bytes())
    shape = _shape(root, "3")
    before = etree.tostring(shape)

    with pytest.raises(UnsupportedEditError) as exc:
        patch_text_shape(shape, old_text="Revenue 38%", new_text="Revenue\n42%")
    assert exc.value.details["reason"] == "paragraph_count_change"
    assert etree.tostring(shape) == before


def test_line_break_structure_is_rejected_without_flattening():
    from lxml import etree

    from markitdown.twoways.formats.pptx.text import patch_text_shape

    root = _slide_root(make_pptx_bytes())
    shape = _shape(root, "3")
    paragraph = shape.xpath('.//*[local-name()="p"]')[0]
    paragraph.insert(1, etree.Element("{http://schemas.openxmlformats.org/drawingml/2006/main}br"))

    with pytest.raises(UnsupportedEditError) as exc:
        patch_text_shape(shape, old_text="Revenue 38%", new_text="Revenue 42%")
    assert exc.value.details["reason"] == "unsupported_text_structure"


def test_alt_text_patch_changes_only_picture_cnvpr_description():
    from lxml import etree

    from markitdown.twoways.formats.pptx.patch import patch_picture_alt_text

    root = _slide_root(make_pptx_bytes())
    picture = _shape(root, "4")
    c_nv_pr = picture.xpath('.//*[local-name()="cNvPr"]')[0]
    before_children = [etree.tostring(child) for child in c_nv_pr]

    patch_picture_alt_text(picture, new_alt_text="Updated icon")

    assert c_nv_pr.get("descr") == "Updated icon"
    assert [etree.tostring(child) for child in c_nv_pr] == before_children
