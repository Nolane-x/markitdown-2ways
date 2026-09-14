from __future__ import annotations

from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    RectangleObject,
    TextStringObject,
)

from markitdown.twoways.capabilities import CapabilityState, capabilities_for_node
from markitdown.twoways.formats.pdf.reader import read_pdf_ir
from markitdown.twoways.ir.serialization import canonical_json_digest, validate_document


def _link_pdf(*, competing_dest: bool = False) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    writer.add_metadata({"/Title": "H10 reader"})
    action = DictionaryObject(
        {
            NameObject("/S"): NameObject("/URI"),
            NameObject("/URI"): TextStringObject("https://example.com/old"),
        }
    )
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
            NameObject("/A"): action,
        }
    )
    if competing_dest:
        annotation[NameObject("/Dest")] = ArrayObject()
    page[NameObject("/Annots")] = ArrayObject([writer._add_object(annotation)])
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


def _link_node(document):
    return next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "pdf-link-uri"
    )


def test_pdf_reader_materializes_deterministic_writable_uri_link() -> None:
    source = _link_pdf()

    first = read_pdf_ir(BytesIO(source), filename="links.pdf")
    second = read_pdf_ir(BytesIO(source), filename="links.pdf")

    validate_document(first)
    assert canonical_json_digest(first) == canonical_json_digest(second)
    link = _link_node(first)
    assert link.payload.text == "https://example.com/old"
    assert link.metadata["pdf.page_index"] == 0
    assert link.metadata["pdf.annotation_index"] == 0
    assert link.metadata["pdf.action_owner_kind"] == "annotation"
    assert (
        link.metadata["pdf.annotation_objgen"]
        == link.metadata["pdf.mutation_owner_objgen"]
    )
    assert link.metadata["pdf.identity_markdown"] is False
    assert link.native_locator is not None
    assert link.native_locator.backend == "pdf"
    assert link.native_locator.path == "/A/URI"

    decision = capabilities_for_node(link).for_operation("update_pdf_link_uri")
    assert decision.state is CapabilityState.WRITABLE
    assert decision.reason_code is None
    assert decision.constraints["identity_markdown"] is False
    assert decision.constraints["source_preservation"] == "incremental-source-prefix"


def test_pdf_reader_materializes_policy_read_only_uri_link() -> None:
    document = read_pdf_ir(
        BytesIO(_link_pdf(competing_dest=True)), filename="links.pdf"
    )
    link = _link_node(document)

    decision = capabilities_for_node(link).for_operation("update_pdf_link_uri")
    assert decision.state is CapabilityState.READ_ONLY
    assert decision.reason_code == "pdf.link.competing_destination"
