from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    RectangleObject,
    TextStringObject,
)

from markitdown.twoways.formats.pdf import PdfPatchWriter, patch_pdf, read_pdf_ir
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.writers.base import TargetInfo


def _link_pdf() -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    writer.add_metadata({"/Title": "H10 public"})
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
    page[NameObject("/Annots")] = ArrayObject([writer._add_object(annotation)])
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


def _link_edit(document) -> EditOperation:
    node = next(
        node for node in document.nodes.values() if node.semantic_role == "pdf-link-uri"
    )
    return EditOperation(
        operation_id="public-link",
        type="update_pdf_link_uri",
        target_node_id=node.node_id,
        precondition=EditPrecondition(expected_old_value=node.payload.text),
        payload={
            "page_index": node.metadata["pdf.page_index"],
            "annotation_index": node.metadata["pdf.annotation_index"],
            "old_uri": node.payload.text,
            "uri": "https://example.com/public",
        },
    )


def _uri(data: bytes) -> str:
    reader = PdfReader(BytesIO(data), strict=True)
    annotation = reader.pages[0]["/Annots"][0].get_object()
    return str(annotation["/A"]["/URI"])


def test_pdf_public_patch_surface_accepts_uri_link_edit() -> None:
    source = _link_pdf()
    document = read_pdf_ir(BytesIO(source), filename="links.pdf")
    output = BytesIO()

    result = patch_pdf(
        document,
        BytesIO(source),
        output,
        edits=(_link_edit(document),),
    )

    assert result.format == "pdf"
    assert _uri(output.getvalue()) == "https://example.com/public"


def test_pdf_patch_writer_adapter_accepts_uri_link_edit() -> None:
    source = _link_pdf()
    document = read_pdf_ir(BytesIO(source), filename="links.pdf")
    output = BytesIO()

    result = PdfPatchWriter().write(
        document,
        output,
        TargetInfo(format="pdf", extension=".pdf"),
        source_stream=BytesIO(source),
        edits=(_link_edit(document),),
    )

    assert result.format == "pdf"
    assert _uri(output.getvalue()) == "https://example.com/public"
