from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from markitdown.twoways import CapabilityState, capabilities_for_node

from ._docx_fixtures import build_docx_fixture
from ._pptx_fixtures import make_grouped_pptx_bytes, make_pptx_bytes


def _decision(node, operation: str):
    return capabilities_for_node(node).for_operation(operation)


def _duplicate_first_pptx_latin_font(source: bytes) -> bytes:
    from lxml import etree

    input_stream = BytesIO(source)
    output_stream = BytesIO()
    with ZipFile(input_stream, "r") as before, ZipFile(
        output_stream, "w", compression=ZIP_DEFLATED
    ) as after:
        for info in before.infolist():
            content = before.read(info.filename)
            if info.filename == "ppt/slides/slide1.xml":
                root = etree.fromstring(content)
                latin = root.xpath(
                    '(.//*[local-name()="rPr"]/*[local-name()="latin"])[1]'
                )[0]
                latin.getparent().append(etree.fromstring(etree.tostring(latin)))
                content = etree.tostring(
                    root,
                    xml_declaration=True,
                    encoding="UTF-8",
                    standalone=True,
                )
            after.writestr(info, content)
    return output_stream.getvalue()


def test_docx_reader_declares_kernel_capabilities_for_supported_nodes():
    from markitdown.twoways.formats.docx import read_docx_ir

    document = read_docx_ir(BytesIO(build_docx_fixture()))
    text = document.nodes[document.canvases[0].root_node_ids[0]]
    table = next(node for node in document.nodes.values() if node.kind == "table")
    image = next(node for node in document.nodes.values() if node.kind == "image")

    assert _decision(text, "replace_text").state is CapabilityState.WRITABLE
    style = _decision(text, "set_text_style")
    assert style.state is CapabilityState.WRITABLE
    assert style.constraints["direct_run_style"] is True
    assert style.constraints["run_indexed"] is True
    assert _decision(table, "update_table_cells").state is CapabilityState.WRITABLE
    assert _decision(image, "set_alt_text").state is CapabilityState.WRITABLE


def test_pptx_reader_declares_style_and_geometry_capabilities_conservatively():
    from markitdown.twoways.formats.pptx import read_pptx_ir

    document = read_pptx_ir(BytesIO(make_pptx_bytes()))
    text = next(
        node
        for node in document.nodes.values()
        if node.kind == "text" and node.payload.text == "Revenue 38%"
    )

    assert _decision(text, "replace_text").state is CapabilityState.WRITABLE
    style = _decision(text, "set_text_style")
    assert style.state is CapabilityState.WRITABLE
    assert style.constraints["direct_run_style"] is True
    geometry = _decision(text, "move_resize")
    assert geometry.state is CapabilityState.WRITABLE
    assert geometry.constraints == {
        "group_coordinate_space": False,
        "rotation": False,
        "unit": "emu",
    }


def test_pptx_group_children_do_not_advertise_move_resize():
    from markitdown.twoways.formats.pptx import read_pptx_ir

    document = read_pptx_ir(BytesIO(make_grouped_pptx_bytes()))
    child = next(node for node in document.nodes.values() if node.parent_id is not None)
    decision = _decision(child, "move_resize")

    assert decision.state is CapabilityState.READ_ONLY
    assert decision.reason_code == "pptx.geometry.group_coordinate_space"


def test_pptx_reader_tolerates_ambiguous_direct_style_but_marks_style_read_only():
    from markitdown.twoways.formats.pptx import read_pptx_ir

    source = _duplicate_first_pptx_latin_font(make_pptx_bytes())
    document = read_pptx_ir(BytesIO(source))
    text = next(
        node
        for node in document.nodes.values()
        if node.kind == "text" and node.payload.text == "Revenue 38%"
    )
    decision = _decision(text, "set_text_style")

    assert decision.state is CapabilityState.READ_ONLY
    assert decision.reason_code == "pptx.style.ambiguous_direct_style"
    assert _decision(text, "replace_text").state is CapabilityState.WRITABLE
