import markitdown.twoways as tw


def test_phase_b_public_api_is_exported():
    expected = {
        "MarkdownProjectionMode",
        "MarkdownProjectionOptions",
        "MarkdownProjection",
        "ProjectionManifest",
        "MarkdownImportResult",
        "project_markdown",
        "import_identity_markdown",
        "read_markdown_ir",
        "projection_manifest_bytes",
        "projection_manifest_digest",
        "MarkdownProjectionError",
        "MarkdownImportError",
        "MarkdownIdentityError",
        "MarkdownSemanticParseError",
    }
    assert expected <= set(tw.__all__)
    for name in expected:
        assert hasattr(tw, name)


def test_internal_identity_parser_is_not_root_exported():
    assert "parse_marker_line" not in tw.__all__
    assert not hasattr(tw, "parse_marker_line")
