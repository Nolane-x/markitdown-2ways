from markitdown.twoways import (
    ImagePayload,
    TablePayload,
    TextPayload,
    validate_document,
)
from markitdown.twoways.markdown import read_markdown_ir


def test_semantic_reader_builds_flow_document():
    doc = read_markdown_ir("# Title\n\nHello **world**.\n", document_id="md-doc")
    validate_document(doc)
    assert doc.document_id == "md-doc"
    assert len(doc.canvases) == 1
    assert doc.canvases[0].kind == "flow"
    assert doc.source.format == "markdown"


def test_semantic_reader_is_deterministic_with_explicit_document_id():
    source = "# Title\n\nHello.\n"
    a = read_markdown_ir(source, document_id="same")
    b = read_markdown_ir(source, document_id="same")
    assert tuple(a.nodes) == tuple(b.nodes)
    assert a == b


def test_headings_and_rich_text_become_text_nodes_and_runs():
    doc = read_markdown_ir(
        "# Title\n\n## Section\n\nHello **world** and *friends*.\n", document_id="rich"
    )
    nodes = list(doc.nodes.values())
    assert nodes[0].semantic_role == "title"
    assert nodes[1].semantic_role == "heading2"
    paragraph = nodes[2].payload.paragraphs[0]
    assert any(
        run.text == "world" and run.style and run.style.direct.get("bold")
        for run in paragraph.runs
    )
    assert any(
        run.text == "friends" and run.style and run.style.direct.get("italic")
        for run in paragraph.runs
    )


def test_lists_preserve_list_level_and_ordered_metadata():
    doc = read_markdown_ir("- first\n  - nested\n1. ordered\n", document_id="lists")
    nodes = list(doc.nodes.values())
    assert nodes[0].semantic_role == "list_item"
    assert nodes[0].payload.paragraphs[0].list_level == 0
    assert nodes[1].payload.paragraphs[0].list_level == 1
    assert nodes[2].metadata["ordered"] is True


def test_fenced_code_becomes_code_text_node():
    doc = read_markdown_ir("```python\nprint('x')\n```\n", document_id="code")
    node = next(iter(doc.nodes.values()))
    assert node.kind == "text"
    assert node.semantic_role == "code"
    assert node.payload.text == "print('x')"
    assert node.metadata["language"] == "python"


def test_image_link_is_inert_resource_reference_without_io():
    doc = read_markdown_ir("![Remote](https://example.com/a.png)\n", document_id="img")
    node = next(iter(doc.nodes.values()))
    assert isinstance(node.payload, ImagePayload)
    resource = doc.resources[node.payload.resource_id]
    assert resource.metadata["source_uri"] == "https://example.com/a.png"
    assert resource.storage_ref is None


def test_simple_markdown_table_becomes_table_payload():
    source = "| A | B |\n| --- | --- |\n| 1 | 2 |\n"
    doc = read_markdown_ir(source, document_id="table")
    node = next(iter(doc.nodes.values()))
    assert isinstance(node.payload, TablePayload)
    assert node.payload.rows == 2
    assert node.payload.columns == 2
    assert [cell.text for cell in node.payload.cells] == ["A", "B", "1", "2"]


def test_marker_like_text_is_ordinary_semantic_content():
    source = '<!-- m2w:block pid="fake" -->\n'
    doc = read_markdown_ir(source, document_id="marker-text")
    node = next(iter(doc.nodes.values()))
    assert isinstance(node.payload, TextPayload)
    assert "m2w:block" in node.payload.text


def test_source_filename_is_recorded():
    doc = read_markdown_ir("Hello\n", document_id="named", source_name="notes.md")
    assert doc.source.filename == "notes.md"


def test_missing_document_id_is_marked_non_reproducible():
    doc = read_markdown_ir("Hello\n")
    assert any(
        d.code == "markdown.semantic.non_reproducible_id" for d in doc.diagnostics
    )
