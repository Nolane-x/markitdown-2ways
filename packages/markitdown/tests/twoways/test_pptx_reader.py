from __future__ import annotations

from hashlib import sha256
from io import BytesIO

from markitdown.twoways import ImagePayload, TextPayload, validate_document

from ._pptx_fixtures import PNG_1X1, make_pptx_bytes


def _node_with_text(document, text: str):
    for node in document.nodes.values():
        if isinstance(node.payload, TextPayload) and node.payload.text == text:
            return node
    raise AssertionError(f"text node not found: {text!r}")


def _image_node(document):
    for node in document.nodes.values():
        if isinstance(node.payload, ImagePayload):
            return node
    raise AssertionError("image node not found")


def test_reader_captures_source_slides_geometry_and_valid_ir():
    from markitdown.twoways.formats.pptx import read_pptx_ir

    source = make_pptx_bytes()
    document = read_pptx_ir(BytesIO(source))
    validate_document(document)

    assert document.source is not None
    assert document.source.format == "pptx"
    assert document.source.sha256 == sha256(source).hexdigest()
    assert document.source.size_bytes == len(source)
    assert document.source.preserved_source_ref == f"pptx:sha256:{sha256(source).hexdigest()}"
    assert len(document.canvases) == 2
    assert [canvas.kind for canvas in document.canvases] == ["slide", "slide"]
    assert document.canvases[0].unit == "emu"
    assert document.canvases[0].width and document.canvases[0].width > 0
    assert document.canvases[0].native_locator.part_uri == "/ppt/slides/slide1.xml"


def test_reader_preserves_text_runs_direct_style_and_native_locator():
    from markitdown.twoways.formats.pptx import read_pptx_ir

    document = read_pptx_ir(BytesIO(make_pptx_bytes()))
    node = _node_with_text(document, "Revenue 38%")

    assert node.kind == "text"
    assert node.geometry is not None and node.geometry.unit == "emu"
    assert node.native_locator is not None
    assert node.native_locator.backend == "pptx-ooxml"
    assert node.native_locator.part_uri == "/ppt/slides/slide1.xml"
    assert node.native_locator.object_id is not None
    assert node.metadata["pptx:patch_text_compatible"] is True

    payload = node.payload
    assert isinstance(payload, TextPayload)
    assert len(payload.paragraphs) == 1
    assert [run.text for run in payload.paragraphs[0].runs] == ["Revenue ", "38%"]
    assert payload.paragraphs[0].runs[0].style.direct["bold"] is True
    assert payload.paragraphs[0].runs[0].style.direct["font_size_pt"] == 24.0
    assert payload.paragraphs[0].runs[0].style.direct["font_family"] == "Aptos"
    assert payload.paragraphs[0].runs[1].style.direct["italic"] is True


def test_reader_node_ids_are_deterministic_and_text_independent():
    from markitdown.twoways.formats.pptx import read_pptx_ir

    first = read_pptx_ir(BytesIO(make_pptx_bytes(metric="38%")))
    repeated = read_pptx_ir(BytesIO(make_pptx_bytes(metric="38%")))
    changed = read_pptx_ir(BytesIO(make_pptx_bytes(metric="42%")))

    first_node = _node_with_text(first, "Revenue 38%")
    repeated_node = _node_with_text(repeated, "Revenue 38%")
    changed_node = _node_with_text(changed, "Revenue 42%")

    assert first_node.node_id == repeated_node.node_id == changed_node.node_id
    assert first_node.native_locator == changed_node.native_locator
    assert first.document_id != changed.document_id


def test_reader_extracts_picture_resource_and_alt_text():
    from markitdown.twoways.formats.pptx import read_pptx_ir

    document = read_pptx_ir(BytesIO(make_pptx_bytes()))
    node = _image_node(document)
    payload = node.payload
    assert isinstance(payload, ImagePayload)
    assert payload.alt_text == "Revenue icon"
    assert payload.resource_id in document.resources
    resource = document.resources[payload.resource_id]
    assert resource.sha256 == sha256(PNG_1X1).hexdigest()
    assert resource.content_type == "image/png"
    assert node.native_locator.part_uri == "/ppt/slides/slide1.xml"


def test_reader_marks_slide_titles_semantically():
    from markitdown.twoways.formats.pptx import read_pptx_ir

    document = read_pptx_ir(BytesIO(make_pptx_bytes()))
    title = _node_with_text(document, "Quarterly Revenue")
    assert title.semantic_role == "title"


def test_reader_extracts_speaker_notes_as_patchable_note_nodes():
    from markitdown.twoways.formats.pptx import read_pptx_ir

    document = read_pptx_ir(BytesIO(make_pptx_bytes()))
    notes = [node for node in document.nodes.values() if node.kind == "note"]
    assert len(notes) == 1
    note = notes[0]
    assert isinstance(note.payload, TextPayload)
    assert note.payload.text == "Speaker note 38%"
    assert note.native_locator.part_uri == "/ppt/notesSlides/notesSlide1.xml"
    assert note.metadata["pptx:patch_text_compatible"] is True


def test_reader_extracts_tables_and_charts_as_read_only_semantic_nodes():
    from markitdown.twoways import ChartPayload, TablePayload
    from markitdown.twoways.formats.pptx import read_pptx_ir

    document = read_pptx_ir(BytesIO(make_pptx_bytes()))
    table = next(node for node in document.nodes.values() if isinstance(node.payload, TablePayload))
    chart = next(node for node in document.nodes.values() if isinstance(node.payload, ChartPayload))

    assert table.kind == "table"
    assert table.payload.rows == 2
    assert table.payload.columns == 2
    assert [cell.text for cell in table.payload.cells] == ["Region", "Revenue", "APAC", "42"]
    assert table.metadata["pptx:patch_capabilities"] == ()

    assert chart.kind == "chart"
    assert chart.payload.categories == ("Q1", "Q2")
    assert chart.payload.series[0]["name"] == "Revenue"
    assert chart.payload.series[0]["values"] == (38.0, 42.0)
    assert chart.metadata["pptx:patch_capabilities"] == ()
