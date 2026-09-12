from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest

from markitdown.twoways import PatchPreconditionError, UnsupportedEditError
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.semantics import native_locator_digest, node_semantic_digest
from markitdown.twoways.ooxml import parse_xml_part

from ._docx_fixtures import build_docx_fixture


_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _document_root(source: bytes):
    with ZipFile(BytesIO(source), "r") as archive:
        return parse_xml_part(archive.read("word/document.xml"))


def _paragraph(root, index: int = 0):
    paragraphs = root.xpath('./*[local-name()="body"]/*[local-name()="p"]')
    return paragraphs[index]


def _runs(paragraph):
    return [
        child
        for child in paragraph
        if isinstance(child.tag, str) and child.tag.endswith("}r")
    ]


def _style_direct(node, run_index: int) -> dict[str, object]:
    runs = tuple(run for paragraph in node.payload.paragraphs for run in paragraph.runs)
    style = runs[run_index].style
    return {} if style is None else dict(style.direct)


def _patch_primitive(paragraph, *, run_index: int, old_style, new_style):
    try:
        from markitdown.twoways.formats.docx._style_patch import patch_docx_run_style
    except ModuleNotFoundError:
        pytest.fail("DOCX style patcher is not implemented yet")
    patch_docx_run_style(
        paragraph,
        run_index=run_index,
        old_style=old_style,
        new_style=new_style,
    )


def test_patch_docx_run_style_changes_only_target_run_properties():
    from lxml import etree

    root = _document_root(build_docx_fixture())
    paragraph = _paragraph(root)
    first, second = _runs(paragraph)
    first_text_before = tuple(
        child.text for child in first if child.tag == f"{{{_W_NS}}}t"
    )
    second_before = etree.tostring(second)

    _patch_primitive(
        paragraph,
        run_index=0,
        old_style={"bold": True},
        new_style={
            "bold": False,
            "italic": True,
            "underline": "double",
            "font_size_pt": 14.0,
            "font_family": "Aptos",
            "color": "#AABBCC",
        },
    )

    first_after, second_after = _runs(paragraph)
    assert (
        tuple(child.text for child in first_after if child.tag == f"{{{_W_NS}}}t")
        == first_text_before
    )
    assert etree.tostring(second_after) == second_before

    rpr = next(child for child in first_after if child.tag == f"{{{_W_NS}}}rPr")
    children = {child.tag.rsplit("}", 1)[-1]: child for child in rpr}
    assert children["b"].get(f"{{{_W_NS}}}val") == "0"
    assert children["i"].get(f"{{{_W_NS}}}val") is None
    assert children["u"].get(f"{{{_W_NS}}}val") == "double"
    assert children["sz"].get(f"{{{_W_NS}}}val") == "28"
    assert children["rFonts"].get(f"{{{_W_NS}}}ascii") == "Aptos"
    assert children["rFonts"].get(f"{{{_W_NS}}}hAnsi") == "Aptos"
    assert children["color"].get(f"{{{_W_NS}}}val") == "AABBCC"


def test_patch_docx_run_style_rejects_stale_native_style():
    root = _document_root(build_docx_fixture())
    with pytest.raises(PatchPreconditionError) as exc:
        _patch_primitive(
            _paragraph(root),
            run_index=0,
            old_style={"bold": False},
            new_style={"bold": True},
        )
    assert exc.value.details["reason"] == "run_style_mismatch"


def test_patch_docx_run_style_rejects_duplicate_property_container():
    from lxml import etree

    root = _document_root(build_docx_fixture())
    paragraph = _paragraph(root)
    first = _runs(paragraph)[0]
    first.insert(0, etree.Element(f"{{{_W_NS}}}rPr"))
    with pytest.raises(UnsupportedEditError) as exc:
        _patch_primitive(
            paragraph,
            run_index=0,
            old_style={"bold": True},
            new_style={"bold": False},
        )
    assert exc.value.details["reason"] == "unsupported_text_structure"


def test_patch_docx_run_style_rejects_unrepresentable_half_point_size():
    root = _document_root(build_docx_fixture())
    with pytest.raises(UnsupportedEditError) as exc:
        _patch_primitive(
            _paragraph(root),
            run_index=0,
            old_style={"bold": True},
            new_style={"bold": True, "font_size_pt": 12.25},
        )
    assert exc.value.details["reason"] == "docx.style.unrepresentable_font_size"


def test_docx_writer_roundtrips_direct_run_style_without_changing_text():
    from markitdown.twoways.formats.docx import patch_docx, read_docx_ir

    source = build_docx_fixture()
    document = read_docx_ir(BytesIO(source))
    node = document.nodes[document.canvases[0].root_node_ids[0]]
    assert _style_direct(node, 0) == {"bold": True}

    edit = EditOperation(
        operation_id="docx-style-run-0",
        type="set_text_style",
        target_node_id=node.node_id,
        precondition=EditPrecondition(
            expected_semantic_digest=node_semantic_digest(node),
            expected_native_locator_digest=native_locator_digest(node),
            expected_old_value=node.payload.text,
        ),
        payload={
            "run_index": 0,
            "old_style": {"bold": True},
            "style": {
                "bold": False,
                "italic": True,
                "underline": "single",
                "font_size_pt": 14.0,
                "font_family": "Aptos",
                "color": "#336699",
            },
        },
    )
    output = BytesIO()
    result = patch_docx(document, BytesIO(source), output, edits=(edit,))

    reread = read_docx_ir(BytesIO(output.getvalue()))
    updated = reread.nodes[node.node_id]
    assert updated.payload.text == node.payload.text
    assert _style_direct(updated, 0) == {
        "bold": False,
        "italic": True,
        "underline": "single",
        "font_size_pt": 14.0,
        "font_family": "Aptos",
        "color": "#336699",
    }
    assert _style_direct(updated, 1) == {"italic": True}
    assert result.metadata["touched_parts"] == ("word/document.xml",)
    assert result.fidelity.claimed_tier == "high"


def test_docx_writer_style_edit_fails_before_writing_on_stale_old_style():
    from markitdown.twoways.formats.docx import patch_docx, read_docx_ir

    source = build_docx_fixture()
    document = read_docx_ir(BytesIO(source))
    node = document.nodes[document.canvases[0].root_node_ids[0]]
    edit = EditOperation(
        operation_id="docx-style-stale",
        type="set_text_style",
        target_node_id=node.node_id,
        payload={
            "run_index": 0,
            "old_style": {"bold": False},
            "style": {"bold": True},
        },
    )
    output = BytesIO()
    with pytest.raises(PatchPreconditionError):
        patch_docx(document, BytesIO(source), output, edits=(edit,))
    assert output.getvalue() == b""
