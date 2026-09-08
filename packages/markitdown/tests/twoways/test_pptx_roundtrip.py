from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest
from pptx import Presentation

from markitdown.twoways import (
    EditOperation,
    EditPrecondition,
    ImagePayload,
    SourcePackageMismatchError,
    TextPayload,
)
from markitdown.twoways.ir.semantics import (
    native_locator_digest,
    node_semantic_digest,
    node_semantic_text,
)

from ._pptx_fixtures import make_pptx_bytes


def _text_node(document, text="Revenue 38%"):
    for node in document.nodes.values():
        if isinstance(node.payload, TextPayload) and node.payload.text == text:
            return node
    raise AssertionError("target text node not found")


def _image_node(document):
    for node in document.nodes.values():
        if isinstance(node.payload, ImagePayload):
            return node
    raise AssertionError("image node not found")


def _edit(node, edit_type: str, payload: dict):
    return EditOperation(
        operation_id=f"test-{edit_type}",
        type=edit_type,
        target_node_id=node.node_id,
        precondition=EditPrecondition(
            expected_semantic_digest=node_semantic_digest(node),
            expected_native_locator_digest=native_locator_digest(node),
            expected_old_value=node_semantic_text(node),
        ),
        payload=payload,
    )


def _assert_only_member_changed(before: bytes, after: bytes, changed: str):
    with ZipFile(BytesIO(before)) as a, ZipFile(BytesIO(after)) as b:
        assert a.namelist() == b.namelist()
        for name in a.namelist():
            if name == changed:
                assert a.read(name) != b.read(name)
            else:
                assert a.read(name) == b.read(name), name


def test_noop_patch_is_exact_archive_copy():
    from markitdown.twoways.formats.pptx import patch_pptx, read_pptx_ir

    source = make_pptx_bytes()
    document = read_pptx_ir(BytesIO(source))
    output = BytesIO()
    result = patch_pptx(document, BytesIO(source), output, edits=())

    assert output.getvalue() == source
    assert result.mode == "patch"
    assert result.fidelity.claimed_tier == "exact-preserve"
    assert result.metadata["touched_parts"] == ()


def test_end_to_end_text_patch_changes_only_one_slide_xml_member():
    from markitdown.twoways.formats.pptx import patch_pptx, read_pptx_ir

    source = make_pptx_bytes()
    document = read_pptx_ir(BytesIO(source))
    node = _text_node(document)
    output = BytesIO()
    result = patch_pptx(
        document,
        BytesIO(source),
        output,
        edits=(_edit(node, "replace_text", {"text": "Revenue 42%"}),),
    )
    patched = output.getvalue()

    presentation = Presentation(BytesIO(patched))
    textbox = next(shape for shape in presentation.slides[0].shapes if shape.shape_id == 3)
    assert textbox.text == "Revenue 42%"
    assert [run.text for run in textbox.text_frame.paragraphs[0].runs] == ["Revenue ", "42%"]
    assert textbox.text_frame.paragraphs[0].runs[0].font.bold is True
    assert textbox.text_frame.paragraphs[0].runs[1].font.italic is True

    _assert_only_member_changed(source, patched, "ppt/slides/slide1.xml")
    assert result.fidelity.claimed_tier == "high"
    assert result.metadata["touched_parts"] == ("ppt/slides/slide1.xml",)


def test_end_to_end_alt_text_patch_changes_only_one_slide_xml_member():
    from markitdown.twoways.formats.pptx import patch_pptx, read_pptx_ir

    source = make_pptx_bytes()
    document = read_pptx_ir(BytesIO(source))
    node = _image_node(document)
    output = BytesIO()
    patch_pptx(
        document,
        BytesIO(source),
        output,
        edits=(_edit(node, "set_alt_text", {"alt_text": "Updated icon"}),),
    )
    patched = output.getvalue()

    presentation = Presentation(BytesIO(patched))
    picture = next(shape for shape in presentation.slides[0].shapes if shape.shape_id == 4)
    assert picture._element._nvXxPr.cNvPr.get("descr") == "Updated icon"
    _assert_only_member_changed(source, patched, "ppt/slides/slide1.xml")


def test_identity_markdown_to_minimal_pptx_patch_vertical_slice():
    from markitdown.twoways import (
        MarkdownProjectionMode,
        MarkdownProjectionOptions,
        import_identity_markdown,
        project_markdown,
    )
    from markitdown.twoways.formats.pptx import patch_pptx, read_pptx_ir

    source = make_pptx_bytes()
    document = read_pptx_ir(BytesIO(source))
    projection = project_markdown(
        document,
        options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY),
    )
    edited_markdown = projection.markdown.replace("**Revenue ***38%*", "**Revenue ***42%*", 1)
    imported = import_identity_markdown(
        edited_markdown,
        original_document=document,
        manifest=projection.manifest,
    )
    assert [edit.type for edit in imported.edits] == ["replace_text"]

    output = BytesIO()
    patch_pptx(document, BytesIO(source), output, edits=imported.edits)
    presentation = Presentation(BytesIO(output.getvalue()))
    textbox = next(shape for shape in presentation.slides[0].shapes if shape.shape_id == 3)
    assert textbox.text == "Revenue 42%"
    _assert_only_member_changed(source, output.getvalue(), "ppt/slides/slide1.xml")


def test_source_digest_mismatch_fails_before_output_is_written():
    from markitdown.twoways.formats.pptx import patch_pptx, read_pptx_ir

    source = make_pptx_bytes(metric="38%")
    wrong_source = make_pptx_bytes(metric="39%")
    document = read_pptx_ir(BytesIO(source))
    node = _text_node(document)
    output = BytesIO()

    with pytest.raises(SourcePackageMismatchError):
        patch_pptx(
            document,
            BytesIO(wrong_source),
            output,
            edits=(_edit(node, "replace_text", {"text": "Revenue 42%"}),),
        )
    assert output.getvalue() == b""


def test_end_to_end_notes_patch_changes_only_notes_slide_xml_member():
    from markitdown.twoways.formats.pptx import patch_pptx, read_pptx_ir

    source = make_pptx_bytes()
    document = read_pptx_ir(BytesIO(source))
    note = next(node for node in document.nodes.values() if node.kind == "note")
    output = BytesIO()
    patch_pptx(
        document,
        BytesIO(source),
        output,
        edits=(_edit(note, "replace_text", {"text": "Speaker note 42%"}),),
    )
    patched = output.getvalue()
    presentation = Presentation(BytesIO(patched))
    assert presentation.slides[0].notes_slide.notes_text_frame.text == "Speaker note 42%"
    _assert_only_member_changed(source, patched, "ppt/notesSlides/notesSlide1.xml")
