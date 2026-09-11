from dataclasses import replace

import pytest

from markitdown.twoways import MarkdownIdentityError, MarkdownImportError
from markitdown.twoways.markdown import (
    MarkdownProjectionMode,
    MarkdownProjectionOptions,
    import_identity_markdown,
    project_markdown,
)
from ._fixtures import make_representative_document


def identity_fixture():
    doc = make_representative_document()
    projection = project_markdown(
        doc, options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY)
    )
    return doc, projection


def test_unchanged_identity_projection_yields_no_edits():
    doc, projection = identity_fixture()
    result = import_identity_markdown(
        projection.markdown,
        original_document=doc,
        manifest=projection.manifest,
    )
    assert result.edits == ()
    assert "text1" in result.unchanged_node_ids


def test_text_change_generates_replace_text_with_preconditions():
    doc, projection = identity_fixture()
    edited = projection.markdown.replace("Revenue increased", "Revenue grew")
    result = import_identity_markdown(
        edited, original_document=doc, manifest=projection.manifest
    )
    edit = next(item for item in result.edits if item.type == "replace_text")
    assert edit.target_node_id == "text1"
    assert edit.payload["text"] == "Revenue grew 38%"
    assert edit.precondition.expected_old_value == "Revenue increased 38%"
    assert edit.precondition.expected_semantic_digest
    assert edit.precondition.expected_native_locator_digest
    assert edit.source_label == "markdown.identity.v1"


def test_image_alt_change_generates_set_alt_text():
    doc, projection = identity_fixture()
    edited = projection.markdown.replace("![Revenue chart]", "![Updated chart]")
    result = import_identity_markdown(
        edited, original_document=doc, manifest=projection.manifest
    )
    edit = next(item for item in result.edits if item.type == "set_alt_text")
    assert edit.target_node_id == "image1"
    assert edit.payload == {"alt_text": "Updated chart"}
    assert edit.precondition.expected_old_value == "Revenue chart"


def test_stale_document_digest_fails_closed():
    doc, projection = identity_fixture()
    stale = replace(doc, metadata=replace(doc.metadata, author="Other"))
    with pytest.raises(MarkdownIdentityError) as raised:
        import_identity_markdown(
            projection.markdown, original_document=stale, manifest=projection.manifest
        )
    assert raised.value.code == "markdown.header.source_digest_mismatch"


def test_missing_header_fails_closed():
    doc, projection = identity_fixture()
    edited = "\n".join(projection.markdown.splitlines()[2:]) + "\n"
    with pytest.raises(MarkdownIdentityError) as raised:
        import_identity_markdown(
            edited, original_document=doc, manifest=projection.manifest
        )
    assert raised.value.code == "markdown.header.missing"


def test_missing_block_marker_is_not_remove_node():
    doc, projection = identity_fixture()
    first = projection.manifest.blocks[0]
    marker_line = next(
        line
        for line in projection.markdown.splitlines()
        if f'pid="{first.projection_id}"' in line
    )
    edited = projection.markdown.replace(marker_line + "\n\n", "", 1)
    with pytest.raises(MarkdownIdentityError) as raised:
        import_identity_markdown(
            edited, original_document=doc, manifest=projection.manifest
        )
    assert raised.value.code == "markdown.block.missing"


def test_duplicate_projection_id_fails_closed():
    doc, projection = identity_fixture()
    marker = next(
        line for line in projection.markdown.splitlines() if "m2w:block" in line
    )
    edited = projection.markdown + marker + "\n"
    with pytest.raises(MarkdownIdentityError) as raised:
        import_identity_markdown(
            edited, original_document=doc, manifest=projection.manifest
        )
    assert raised.value.code == "markdown.marker.duplicate_projection_id"


def test_unknown_projection_id_fails_closed():
    doc, projection = identity_fixture()
    first = projection.manifest.blocks[0]
    edited = projection.markdown.replace(
        f'pid="{first.projection_id}"', 'pid="p_unknown"', 1
    )
    with pytest.raises(MarkdownIdentityError) as raised:
        import_identity_markdown(
            edited, original_document=doc, manifest=projection.manifest
        )
    assert raised.value.code == "markdown.marker.unknown_projection_id"


def test_marker_metadata_mismatch_fails_closed():
    doc, projection = identity_fixture()
    first = projection.manifest.blocks[0]
    edited = projection.markdown.replace(f'kind="{first.node_kind}"', 'kind="image"', 1)
    with pytest.raises(MarkdownIdentityError) as raised:
        import_identity_markdown(
            edited, original_document=doc, manifest=projection.manifest
        )
    assert raised.value.code == "markdown.marker.metadata_mismatch"


def test_substantive_unanchored_content_fails_closed():
    doc, projection = identity_fixture()
    lines = projection.markdown.splitlines()
    lines.insert(2, "UNANCHORED")
    edited = "\n".join(lines) + "\n"
    with pytest.raises(MarkdownImportError) as raised:
        import_identity_markdown(
            edited, original_document=doc, manifest=projection.manifest
        )
    assert raised.value.code == "markdown.block.unanchored_content"


def test_clean_manifest_cannot_be_identity_imported():
    doc = make_representative_document()
    projection = project_markdown(doc)
    with pytest.raises(MarkdownIdentityError):
        import_identity_markdown(
            projection.markdown, original_document=doc, manifest=projection.manifest
        )


def test_formatting_only_text_change_is_not_silently_ignored():
    doc, projection = identity_fixture()
    edited = projection.markdown.replace("**38%**", "38%")
    with pytest.raises(MarkdownImportError) as raised:
        import_identity_markdown(
            edited, original_document=doc, manifest=projection.manifest
        )
    assert raised.value.code == "markdown.edit.unsupported"


def test_read_only_table_change_fails_closed():
    doc, projection = identity_fixture()
    edited = projection.markdown.replace("| Region | Revenue |", "| Region | Sales |")
    with pytest.raises(MarkdownImportError) as raised:
        import_identity_markdown(
            edited, original_document=doc, manifest=projection.manifest
        )
    assert raised.value.code == "markdown.edit.read_only"


def test_harmless_extra_blank_lines_do_not_create_edit():
    doc, projection = identity_fixture()
    marker = next(
        line for line in projection.markdown.splitlines() if "m2w:block" in line
    )
    edited = projection.markdown.replace(marker + "\n\n", marker + "\n\n\n\n", 1)
    result = import_identity_markdown(
        edited, original_document=doc, manifest=projection.manifest
    )
    assert result.edits == ()


def test_operation_ids_are_deterministic():
    doc, projection = identity_fixture()
    edited = projection.markdown.replace("Revenue increased", "Revenue grew")
    a = import_identity_markdown(
        edited, original_document=doc, manifest=projection.manifest
    )
    b = import_identity_markdown(
        edited, original_document=doc, manifest=projection.manifest
    )
    assert a.edits[0].operation_id == b.edits[0].operation_id


def test_duplicate_node_assignment_fails_closed_before_guessing():
    doc, projection = identity_fixture()
    first, second = projection.manifest.blocks[:2]
    second_marker = next(
        line
        for line in projection.markdown.splitlines()
        if f'pid="{second.projection_id}"' in line
    )
    edited_marker = second_marker.replace(
        f'node="{second.node_id}"', f'node="{first.node_id}"'
    )
    edited = projection.markdown.replace(second_marker, edited_marker, 1)
    with pytest.raises(MarkdownIdentityError) as raised:
        import_identity_markdown(
            edited, original_document=doc, manifest=projection.manifest
        )
    assert raised.value.code == "markdown.marker.duplicate_node"


def test_image_resource_target_change_is_not_promoted_to_replace_resource():
    doc, projection = identity_fixture()
    edited = projection.markdown.replace("m2w-resource:img1", "m2w-resource:other")
    with pytest.raises(MarkdownImportError) as raised:
        import_identity_markdown(
            edited, original_document=doc, manifest=projection.manifest
        )
    assert raised.value.code == "markdown.edit.unsupported"


def test_permissive_unknown_marker_key_is_reported_as_diagnostic():
    doc, projection = identity_fixture()
    first = projection.manifest.blocks[0]
    marker = next(
        line
        for line in projection.markdown.splitlines()
        if f'pid="{first.projection_id}"' in line
    )
    edited_marker = marker.replace(" -->", ' extension="x" -->')
    edited = projection.markdown.replace(marker, edited_marker, 1)
    result = import_identity_markdown(
        edited,
        original_document=doc,
        manifest=projection.manifest,
        strict=False,
    )
    assert any(d.code == "markdown.marker.unknown_key" for d in result.diagnostics)
