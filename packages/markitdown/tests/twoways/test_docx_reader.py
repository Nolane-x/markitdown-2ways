from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile, ZipInfo

from markitdown.twoways.ir.nodes import ImagePayload, TablePayload, TextPayload

from ._docx_fixtures import build_docx_fixture


def _rewrite_document_text(source: bytes, old: bytes, new: bytes) -> bytes:
    output = BytesIO()
    with ZipFile(BytesIO(source), "r") as original, ZipFile(output, "w") as target:
        for info in original.infolist():
            data = original.read(info)
            if info.filename == "word/document.xml":
                data = data.replace(old, new)
            clone = ZipInfo(info.filename, info.date_time)
            clone.compress_type = info.compress_type
            clone.external_attr = info.external_attr
            clone.internal_attr = info.internal_attr
            clone.extra = info.extra
            clone.comment = info.comment
            target.writestr(clone, data)
    return output.getvalue()


def test_reader_builds_source_authority_body_order_and_metadata():
    from markitdown.twoways.formats.docx import read_docx_ir

    source = build_docx_fixture()
    document = read_docx_ir(BytesIO(source))
    assert document.source.format == "docx"
    assert document.source.sha256
    assert document.source.size_bytes == len(source)
    assert document.metadata.title == "MarkItDown 2Ways DOCX Fixture"
    assert document.metadata.author == "Nolane"
    assert document.canvases[0].canvas_id == "docx-body"

    body_nodes = [document.nodes[node_id] for node_id in document.canvases[0].root_node_ids]
    assert [node.kind for node in body_nodes] == ["text", "text", "table", "image"]
    assert body_nodes[0].payload.text == "Revenue 38%"
    assert body_nodes[1].payload.text == "Visit OpenAI today"


def test_reader_preserves_run_styles_hyperlink_context_and_table_semantics():
    from markitdown.twoways.formats.docx import read_docx_ir

    document = read_docx_ir(BytesIO(build_docx_fixture()))
    body_nodes = [document.nodes[node_id] for node_id in document.canvases[0].root_node_ids]
    first = body_nodes[0]
    assert isinstance(first.payload, TextPayload)
    assert first.payload.paragraphs[0].runs[0].style.direct["bold"] is True
    assert first.payload.paragraphs[0].runs[1].style.direct["italic"] is True

    linked = body_nodes[1]
    contexts = [
        run.native_locator.attributes["hyperlink_relationship_id"]
        for run in linked.payload.paragraphs[0].runs
    ]
    assert contexts[0] is None and contexts[1] and contexts[2] is None

    table = body_nodes[2]
    assert isinstance(table.payload, TablePayload)
    assert (table.payload.rows, table.payload.columns) == (2, 2)
    assert [cell.text for cell in table.payload.cells] == ["Metric", "Value", "Revenue", "38%"]
    assert table.metadata["docx:patch_capabilities"] == ()


def test_reader_builds_header_footer_canvases_and_picture_resource():
    from markitdown.twoways.formats.docx import read_docx_ir

    document = read_docx_ir(BytesIO(build_docx_fixture()))
    assert [canvas.kind for canvas in document.canvases] == ["document", "header", "footer"]
    header = document.nodes[document.canvases[1].root_node_ids[0]]
    footer = document.nodes[document.canvases[2].root_node_ids[0]]
    assert header.payload.text == "Confidential Header"
    assert footer.payload.text == "Page Footer"

    image_nodes = [node for node in document.nodes.values() if node.kind == "image"]
    assert len(image_nodes) == 1
    image = image_nodes[0]
    assert isinstance(image.payload, ImagePayload)
    assert image.payload.alt_text == "Green status pixel"
    assert image.payload.resource_id in document.resources
    resource = document.resources[image.payload.resource_id]
    assert resource.storage_ref.startswith("/word/media/")
    assert resource.sha256


def test_reader_node_ids_survive_text_only_source_change():
    from markitdown.twoways.formats.docx import read_docx_ir

    source = build_docx_fixture()
    changed = _rewrite_document_text(source, b"38%", b"42%")
    before = read_docx_ir(BytesIO(source))
    after = read_docx_ir(BytesIO(changed))

    before_body = [before.nodes[node_id] for node_id in before.canvases[0].root_node_ids]
    after_body = [after.nodes[node_id] for node_id in after.canvases[0].root_node_ids]
    assert before_body[0].node_id == after_body[0].node_id
    before_image = next(node for node in before.nodes.values() if node.kind == "image")
    after_image = next(node for node in after.nodes.values() if node.kind == "image")
    assert before_image.node_id == after_image.node_id
