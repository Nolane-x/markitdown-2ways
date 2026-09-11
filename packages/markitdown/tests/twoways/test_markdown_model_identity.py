import pytest

from markitdown.twoways import MarkdownIdentityError
from markitdown.twoways.markdown import (
    MarkdownProjectionMode,
    MarkdownProjectionOptions,
    ProjectionBlock,
    ProjectionManifest,
)


def test_projection_options_default_to_clean_mode():
    options = MarkdownProjectionOptions()
    assert options.mode is MarkdownProjectionMode.CLEAN
    assert options.resource_uri_scheme == "m2w-resource"


def test_projection_manifest_is_tuple_backed_and_versioned():
    block = ProjectionBlock(
        projection_id="p1",
        node_id="n1",
        canvas_id="c1",
        node_kind="text",
        semantic_role=None,
        ordinal=0,
        source_semantic_digest="a" * 64,
        native_locator_digest=None,
        editable_capabilities=("replace_text",),
        rendered_digest="b" * 64,
    )
    manifest = ProjectionManifest(
        format_version="1",
        document_id="doc1",
        document_schema_version="0.1.0",
        source_document_digest="c" * 64,
        projection_mode="identity",
        blocks=[block],
    )
    assert manifest.blocks == (block,)


def test_markdown_identity_error_keeps_structured_details():
    exc = MarkdownIdentityError("bad marker", details={"line": 4})
    assert exc.code == "markdown.identity"
    assert exc.details == {"line": 4}


from markitdown.twoways.markdown import (
    projection_manifest_bytes,
    projection_manifest_digest,
)
from markitdown.twoways.markdown.identity import (
    encode_block_marker,
    encode_projection_header,
    escape_marker_like_text,
    parse_marker_line,
    unescape_marker_like_text,
)


def test_identity_marker_encoder_is_canonical_and_one_line():
    marker = encode_block_marker(
        projection_id="p1", node_id="n1", kind="text", source_digest="a" * 64
    )
    assert (
        marker
        == '<!-- m2w:block pid="p1" node="n1" kind="text" src="sha256:'
        + "a" * 64
        + '" -->'
    )
    assert "\n" not in marker


def test_projection_header_encoder_is_canonical():
    marker = encode_projection_header(
        version="1", document_id="doc1", source_digest="b" * 64
    )
    assert (
        marker
        == '<!-- m2w:projection v="1" doc="doc1" base="sha256:' + "b" * 64 + '" -->'
    )


def test_duplicate_marker_keys_fail_closed():
    line = (
        '<!-- m2w:block pid="p1" pid="p2" node="n1" kind="text" src="sha256:'
        + "a" * 64
        + '" -->'
    )
    with pytest.raises(MarkdownIdentityError):
        parse_marker_line(line)


def test_unrelated_html_comment_is_not_engine_marker():
    assert parse_marker_line("<!-- ordinary comment -->") is None


def test_malformed_engine_comment_fails_closed():
    with pytest.raises(MarkdownIdentityError):
        parse_marker_line("<!-- m2w:block nope -->")


def test_unknown_marker_key_fails_strict_mode():
    line = (
        '<!-- m2w:block pid="p1" node="n1" kind="text" src="sha256:'
        + "a" * 64
        + '" extra="x" -->'
    )
    with pytest.raises(MarkdownIdentityError):
        parse_marker_line(line)


def test_marker_like_user_text_is_escaped_and_reversible():
    source = 'hello <!-- m2w:block pid="evil" --> world'
    escaped = escape_marker_like_text(source)
    assert "<!-- m2w:block" not in escaped
    assert unescape_marker_like_text(escaped) == source


def test_marker_values_reject_physical_newlines():
    with pytest.raises(MarkdownIdentityError):
        encode_block_marker(
            projection_id="bad\nid", node_id="n1", kind="text", source_digest="a" * 64
        )


def test_manifest_serialization_is_deterministic():
    block = ProjectionBlock(
        projection_id="p1",
        node_id="n1",
        canvas_id="c1",
        node_kind="text",
        semantic_role=None,
        ordinal=0,
        source_semantic_digest="a" * 64,
        native_locator_digest=None,
        editable_capabilities=("replace_text",),
        rendered_digest="b" * 64,
    )
    manifest = ProjectionManifest(
        format_version="1",
        document_id="doc1",
        document_schema_version="0.1.0",
        source_document_digest="c" * 64,
        projection_mode="identity",
        blocks=(block,),
    )
    assert projection_manifest_bytes(manifest) == projection_manifest_bytes(manifest)
    assert len(projection_manifest_digest(manifest)) == 64


def test_unrelated_comment_that_mentions_m2w_text_is_not_engine_marker():
    assert parse_marker_line("<!-- ordinary note mentioning m2w:block -->") is None


def test_marker_like_user_text_with_extra_spaces_is_escaped_and_reversible():
    source = 'hello <!--   m2w:block pid="evil" --> world'
    escaped = escape_marker_like_text(source)
    assert "<!--   m2w:block" not in escaped
    assert unescape_marker_like_text(escaped) == source


def test_projection_block_rejects_invalid_digest_shape():
    with pytest.raises(ValueError, match="source_semantic_digest"):
        ProjectionBlock(
            projection_id="p1",
            node_id="n1",
            canvas_id=None,
            node_kind="text",
            semantic_role=None,
            ordinal=0,
            source_semantic_digest="not-a-digest",
            native_locator_digest=None,
            editable_capabilities=(),
            rendered_digest="b" * 64,
        )
