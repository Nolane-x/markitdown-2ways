from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    RectangleObject,
    TextStringObject,
)

from markitdown.twoways._errors import UnsupportedEditError
from markitdown.twoways.formats.pdf.reader import read_pdf_ir
from markitdown.twoways.formats.pdf.writer import patch_pdf
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition


def _link_pdf(*, indirect_action: bool = False) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    writer.add_metadata({"/Title": "H10 writer", "/Author": "Ada"})
    action = DictionaryObject(
        {
            NameObject("/S"): NameObject("/URI"),
            NameObject("/URI"): TextStringObject("https://example.com/old"),
        }
    )
    action_value = writer._add_object(action) if indirect_action else action
    annotation = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Link"),
            NameObject("/Rect"): RectangleObject(
                [
                    NumberObject(10),
                    NumberObject(10),
                    NumberObject(120),
                    NumberObject(30),
                ]
            ),
            NameObject("/A"): action_value,
        }
    )
    page[NameObject("/Annots")] = ArrayObject([writer._add_object(annotation)])
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


def _link_node(document):
    return next(
        node for node in document.nodes.values() if node.semantic_role == "pdf-link-uri"
    )


def _metadata_node(document, key: str):
    return next(
        node
        for node in document.nodes.values()
        if node.metadata.get("pdf.info_key") == key
    )


def _link_edit(document, uri: str, operation_id: str = "link-1") -> EditOperation:
    node = _link_node(document)
    return EditOperation(
        operation_id=operation_id,
        type="update_pdf_link_uri",
        target_node_id=node.node_id,
        precondition=EditPrecondition(expected_old_value=node.payload.text),
        payload={
            "page_index": node.metadata["pdf.page_index"],
            "annotation_index": node.metadata["pdf.annotation_index"],
            "old_uri": node.payload.text,
            "uri": uri,
        },
    )


def _metadata_edit(document, value: str) -> EditOperation:
    node = _metadata_node(document, "/Title")
    return EditOperation(
        operation_id="metadata-title",
        type="update_pdf_metadata",
        target_node_id=node.node_id,
        precondition=EditPrecondition(expected_old_value=node.payload.text),
        payload={"field": node.metadata["pdf.info_field"], "value": value},
    )


def _uri(data: bytes) -> str:
    reader = PdfReader(BytesIO(data), strict=True)
    annotation = reader.pages[0]["/Annots"][0].get_object()
    action = annotation["/A"]
    return str(action["/URI"])


def test_pdf_writer_updates_direct_uri_owner_incrementally() -> None:
    source = _link_pdf()
    document = read_pdf_ir(BytesIO(source), filename="links.pdf")
    output = BytesIO()

    result = patch_pdf(
        document,
        BytesIO(source),
        output,
        edits=(_link_edit(document, "https://example.com/new"),),
    )
    candidate = output.getvalue()

    assert candidate.startswith(source)
    assert len(candidate) > len(source)
    assert _uri(candidate) == "https://example.com/new"
    assert result.bytes_written == len(candidate)
    assert result.fidelity.claimed_tier == "high"


def test_pdf_writer_updates_indirect_uri_action_owner_incrementally() -> None:
    source = _link_pdf(indirect_action=True)
    document = read_pdf_ir(BytesIO(source), filename="links.pdf")
    output = BytesIO()

    patch_pdf(
        document,
        BytesIO(source),
        output,
        edits=(_link_edit(document, "https://example.com/indirect"),),
    )

    candidate = output.getvalue()
    assert candidate.startswith(source)
    assert _uri(candidate) == "https://example.com/indirect"


def test_pdf_writer_applies_metadata_and_uri_in_one_increment() -> None:
    source = _link_pdf()
    document = read_pdf_ir(BytesIO(source), filename="links.pdf")
    output = BytesIO()

    patch_pdf(
        document,
        BytesIO(source),
        output,
        edits=(
            _metadata_edit(document, "Updated title"),
            _link_edit(document, "https://example.com/mixed"),
        ),
    )

    candidate = output.getvalue()
    reader = PdfReader(BytesIO(candidate), strict=True)
    assert candidate.startswith(source)
    assert reader.metadata is not None
    assert reader.metadata.title == "Updated title"
    assert reader.metadata.author == "Ada"
    assert _uri(candidate) == "https://example.com/mixed"


def test_pdf_writer_rejects_duplicate_link_target_before_output() -> None:
    source = _link_pdf()
    document = read_pdf_ir(BytesIO(source), filename="links.pdf")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError) as exc:
        patch_pdf(
            document,
            BytesIO(source),
            output,
            edits=(
                _link_edit(document, "https://example.com/one", "link-1"),
                _link_edit(document, "https://example.com/two", "link-2"),
            ),
        )

    assert exc.value.details["reason"] == "pdf.link.duplicate_target"
    assert output.getvalue() == b""
