from __future__ import annotations

from io import BytesIO

from markitdown.twoways.formats.html.lexical import parse_html_source
from markitdown.twoways.formats.html.reader import read_html_ir
from markitdown.twoways.formats.html.render import (
    render_html_attribute,
    render_html_text,
)
from markitdown.twoways.formats.html.writer import patch_html
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.semantics import native_locator_digest, node_semantic_digest


def _node(document, path):
    return next(
        node
        for node in document.nodes.values()
        if node.metadata.get("html.path") == path
    )


def _edit(document, path, value, *, operation_id):
    node = _node(document, path)
    edit_type = (
        "replace_html_attribute"
        if node.metadata.get("html.kind") == "attribute"
        else "replace_html_text"
    )
    return EditOperation(
        operation_id=operation_id,
        type=edit_type,
        target_node_id=node.node_id,
        precondition=EditPrecondition(
            expected_semantic_digest=node_semantic_digest(node),
            expected_native_locator_digest=native_locator_digest(node),
            expected_old_value=node.payload.get("value"),
        ),
        payload={"value": value},
    )


def _lexical_value(source: str, path: str) -> str:
    parsed = parse_html_source(source.encode("utf-8"))
    node = next(item for item in parsed.lexical.nodes if item.path == path)
    assert isinstance(node.value, str)
    return node.value


def test_text_renderer_preserves_requested_semantics() -> None:
    requested = "A&B<C>D\rE\nΩ"

    token = render_html_text(requested)

    assert token == "A&amp;B&lt;C&gt;D&#13;E\nΩ"
    wrapper = f"<html><body><p>{token}</p></body></html>"
    assert _lexical_value(wrapper, "/html[1]/body[1]/p[1]/#text[1]") == requested


def test_double_quoted_attribute_renderer_preserves_requested_semantics() -> None:
    requested = '"&<>\t\n\rΩ'

    token = render_html_attribute(requested, '"')

    assert token == "&quot;&amp;&lt;&gt;&#9;&#10;&#13;Ω"
    wrapper = f'<html><body><p data-x="{token}">x</p></body></html>'
    assert _lexical_value(wrapper, "/html[1]/body[1]/p[1]/@data-x") == requested


def test_single_quoted_attribute_renderer_preserves_requested_semantics() -> None:
    requested = "'&<>\t\n\rΩ"

    token = render_html_attribute(requested, "'")

    assert token == "&#39;&amp;&lt;&gt;&#9;&#10;&#13;Ω"
    wrapper = f"<html><body><p data-x='{token}'>x</p></body></html>"
    assert _lexical_value(wrapper, "/html[1]/body[1]/p[1]/@data-x") == requested


def test_patch_html_renders_text_and_preserves_source_outside_target() -> None:
    source = b"<html><body><p>old &amp; text</p><div>stay</div></body></html>"
    document = read_html_ir(BytesIO(source), filename="page.html")
    output = BytesIO()

    result = patch_html(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(
                document,
                "/html[1]/body[1]/p[1]/#text[1]",
                "A&B<C>D\rE\nΩ",
                operation_id="text",
            ),
        ),
    )

    assert output.getvalue() == (
        "<html><body><p>A&amp;B&lt;C&gt;D&#13;E\nΩ</p>" "<div>stay</div></body></html>"
    ).encode("utf-8")
    assert result.fidelity.claimed_tier == "high"


def test_multi_target_patch_preserves_quotes_and_handles_offset_changes() -> None:
    source = (
        b'<html><body><p class="x">much longer</p>'
        b"<div data-k='v'>stay</div></body></html>"
    )
    document = read_html_ir(BytesIO(source), filename="page.html")
    output = BytesIO()

    patch_html(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(
                document,
                "/html[1]/body[1]/p[1]/#text[1]",
                "z",
                operation_id="text",
            ),
            _edit(
                document,
                "/html[1]/body[1]/p[1]/@class",
                'a "much" longer & value',
                operation_id="class",
            ),
            _edit(
                document,
                "/html[1]/body[1]/div[1]/@data-k",
                "changed's",
                operation_id="data-k",
            ),
        ),
    )

    assert output.getvalue() == (
        b'<html><body><p class="a &quot;much&quot; longer &amp; value">z</p>'
        b"<div data-k='changed&#39;s'>stay</div></body></html>"
    )
