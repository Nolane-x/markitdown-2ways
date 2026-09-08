from dataclasses import replace

from markitdown.twoways import ChartPayload, Node, TextPayload
from markitdown.twoways.markdown import (
    MarkdownProjectionMode,
    MarkdownProjectionOptions,
    project_markdown,
)
from ._fixtures import make_representative_document


def test_clean_projection_contains_no_engine_markers():
    projection = project_markdown(make_representative_document())
    assert projection.manifest.projection_mode == "clean"
    assert "<!-- m2w:" not in projection.markdown


def test_identity_projection_has_header_and_block_markers():
    result = project_markdown(
        make_representative_document(),
        options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY),
    )
    assert result.markdown.startswith("<!-- m2w:projection ")
    assert '<!-- m2w:block ' in result.markdown
    assert result.manifest.projection_mode == "identity"


def test_projection_order_uses_canvas_and_explicit_child_order():
    result = project_markdown(make_representative_document())
    assert result.markdown.index("Revenue increased") < result.markdown.index("Region")


def test_text_title_and_rich_bold_rendering():
    result = project_markdown(make_representative_document())
    assert "# Revenue increased **38%**" in result.markdown


def test_image_uses_inert_resource_uri_and_alt_text():
    result = project_markdown(make_representative_document())
    assert "![Revenue chart](m2w-resource:img1)" in result.markdown


def test_simple_table_renders_markdown_table_and_is_read_only():
    result = project_markdown(make_representative_document())
    assert "| Region | Revenue |" in result.markdown
    table_block = next(block for block in result.manifest.blocks if block.node_id == "table1")
    assert table_block.editable_capabilities == ()


def test_unknown_native_omitted_by_default_with_diagnostic():
    result = project_markdown(make_representative_document())
    assert "unknown native" not in result.markdown.lower()
    assert any(d.code == "markdown.projection.unknown_native_omitted" for d in result.manifest.diagnostics)


def test_unknown_native_can_emit_readable_placeholder():
    result = project_markdown(
        make_representative_document(),
        options=MarkdownProjectionOptions(include_unknown_placeholders=True),
    )
    assert "[Unsupported native content: unknown1]" in result.markdown


def test_chart_summary_is_read_only():
    doc = make_representative_document()
    chart = Node(
        node_id="chart1",
        kind="chart",
        canvas_id="slide2",
        order=2,
        payload=ChartPayload(
            chart_type="bar",
            title="Revenue",
            categories=("Q1", "Q2"),
            series=({"name": "Sales", "values": (10, 14)},),
        ),
    )
    nodes = {**doc.nodes, "chart1": chart}
    slide2 = replace(doc.canvases[1], root_node_ids=("table1", "unknown1", "chart1"))
    doc = replace(doc, nodes=nodes, canvases=(doc.canvases[0], slide2), root_node_ids=(*doc.root_node_ids, "chart1"))
    result = project_markdown(doc)
    assert "### Chart: Revenue" in result.markdown
    assert "- Q1: 10" in result.markdown
    assert "- Q2: 14" in result.markdown
    block = next(block for block in result.manifest.blocks if block.node_id == "chart1")
    assert block.editable_capabilities == ()


def test_note_can_be_excluded():
    doc = make_representative_document()
    note = Node(node_id="note1", kind="note", canvas_id="slide2", order=2, payload=TextPayload(text="speaker note"))
    slide2 = replace(doc.canvases[1], root_node_ids=("table1", "unknown1", "note1"))
    doc = replace(doc, nodes={**doc.nodes, "note1": note}, canvases=(doc.canvases[0], slide2), root_node_ids=(*doc.root_node_ids, "note1"))
    included = project_markdown(doc)
    excluded = project_markdown(doc, options=MarkdownProjectionOptions(include_notes=False))
    assert "### Notes" in included.markdown and "speaker note" in included.markdown
    assert "speaker note" not in excluded.markdown


def test_projection_normalization_has_one_final_newline_and_no_trailing_spaces():
    result = project_markdown(make_representative_document())
    assert result.markdown.endswith("\n") and not result.markdown.endswith("\n\n")
    assert all(line == line.rstrip() for line in result.markdown.splitlines())


def test_projection_is_deterministic():
    doc = make_representative_document()
    a = project_markdown(doc, options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY))
    b = project_markdown(doc, options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY))
    assert a == b


def test_marker_like_user_text_cannot_spoof_identity_parser():
    doc = make_representative_document()
    text = replace(doc.nodes["text1"], payload=TextPayload(text='hello <!-- m2w:block pid="evil" -->'))
    doc = replace(doc, nodes={**doc.nodes, "text1": text})
    result = project_markdown(doc, options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY))
    assert result.markdown.count("<!-- m2w:block ") == len(result.manifest.blocks)
    assert '&lt;!-- m2w:block pid="evil" -->' in result.markdown


def test_clean_projection_preserves_marker_like_user_text_verbatim():
    doc = make_representative_document()
    text = replace(doc.nodes["text1"], payload=TextPayload(text='hello <!-- m2w:block pid="not-engine" -->'))
    doc = replace(doc, nodes={**doc.nodes, "text1": text})
    result = project_markdown(doc)
    assert '<!-- m2w:block pid="not-engine" -->' in result.markdown


def test_identity_projection_omits_unanchored_document_metadata_title_when_no_title_node():
    doc = make_representative_document()
    text = replace(doc.nodes["text1"], semantic_role="paragraph", payload=TextPayload(text="body"))
    doc = replace(doc, nodes={**doc.nodes, "text1": text})
    result = project_markdown(doc, options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY))
    assert result.markdown.startswith("<!-- m2w:projection ")
    assert "Quarterly Revenue" not in result.markdown
    assert any(d.code == "markdown.projection.document_title_omitted" for d in result.manifest.diagnostics)
