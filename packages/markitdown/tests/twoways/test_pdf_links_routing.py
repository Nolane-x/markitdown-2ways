from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NumberObject, RectangleObject, TextStringObject

from markitdown.twoways._errors import PatchPreconditionError, SourcePackageMismatchError, UnsupportedEditError
from markitdown.twoways.formats.pdf.reader import read_pdf_ir
from markitdown.twoways.formats.pdf.routing import resolve_pdf_link_uri_edit
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.provenance import NativeLocator


def _link_pdf(uri: str = "https://example.com/old") -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    writer.add_metadata({"/Title": "H10 routing"})
    action = DictionaryObject({NameObject("/S"): NameObject("/URI"), NameObject("/URI"): TextStringObject(uri)})
    annotation = DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"),
        NameObject("/Subtype"): NameObject("/Link"),
        NameObject("/Rect"): RectangleObject([NumberObject(10), NumberObject(10), NumberObject(120), NumberObject(30)]),
        NameObject("/A"): action,
    })
    page[NameObject("/Annots")] = ArrayObject([writer._add_object(annotation)])
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


def _link(document):
    return next(node for node in document.nodes.values() if node.semantic_role == "pdf-link-uri")


def _edit(document, uri: str = "https://example.com/new") -> EditOperation:
    node = _link(document)
    return EditOperation(
        operation_id="link-1",
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


def _replace_node(document, node):
    nodes = dict(document.nodes)
    nodes[node.node_id] = node
    return replace(document, nodes=nodes)


def test_pdf_link_routing_revalidates_fresh_native_authority() -> None:
    source = _link_pdf()
    document = read_pdf_ir(BytesIO(source), filename="links.pdf")
    routed = resolve_pdf_link_uri_edit(document, source, _edit(document))
    assert routed.operation_id == "link-1"
    assert routed.page_index == 0
    assert routed.annotation_index == 0
    assert routed.old_uri == "https://example.com/old"
    assert routed.uri == "https://example.com/new"
    assert routed.owner_kind == "annotation"
    assert routed.annotation_objgen == routed.mutation_owner_objgen
    assert routed.locator_digest == _link(document).metadata["pdf.link_locator_digest"]


def test_pdf_link_routing_rejects_stale_source() -> None:
    source = _link_pdf()
    document = read_pdf_ir(BytesIO(source), filename="links.pdf")
    with pytest.raises(SourcePackageMismatchError):
        resolve_pdf_link_uri_edit(document, _link_pdf("https://example.com/stale"), _edit(document))


def test_pdf_link_routing_rejects_stale_old_uri() -> None:
    source = _link_pdf()
    document = read_pdf_ir(BytesIO(source), filename="links.pdf")
    edit = _edit(document)
    edit = replace(edit, payload={**edit.payload, "old_uri": "https://example.com/stale"})
    with pytest.raises(PatchPreconditionError) as exc:
        resolve_pdf_link_uri_edit(document, source, edit)
    assert exc.value.details["reason"] == "pdf.link.old_uri"


@pytest.mark.parametrize("key,value", [("page_index", True), ("annotation_index", -1)])
def test_pdf_link_routing_rejects_invalid_coordinates(key: str, value: object) -> None:
    source = _link_pdf()
    document = read_pdf_ir(BytesIO(source), filename="links.pdf")
    edit = _edit(document)
    edit = replace(edit, payload={**edit.payload, key: value})
    with pytest.raises(UnsupportedEditError) as exc:
        resolve_pdf_link_uri_edit(document, source, edit)
    assert exc.value.details["reason"] == "pdf.link.payload_coordinates"


def test_pdf_link_routing_rejects_forged_native_evidence() -> None:
    source = _link_pdf()
    document = read_pdf_ir(BytesIO(source), filename="links.pdf")
    node = _link(document)
    forged_metadata = dict(node.metadata)
    forged_metadata["pdf.mutation_owner_objgen"] = (999, 0)
    forged_metadata["pdf.link_locator_digest"] = "0" * 64
    assert node.native_locator is not None
    forged = replace(
        node,
        metadata=forged_metadata,
        native_locator=NativeLocator(
            backend="pdf",
            part_uri=node.native_locator.part_uri,
            object_id="999:0",
            path=node.native_locator.path,
        ),
    )
    forged_document = _replace_node(document, forged)
    with pytest.raises(PatchPreconditionError) as exc:
        resolve_pdf_link_uri_edit(forged_document, source, _edit(forged_document))
    assert exc.value.details["reason"] in {"pdf.link.native_binding", "pdf.link.native_locator"}


def test_pdf_link_routing_rejects_semantic_noop() -> None:
    source = _link_pdf()
    document = read_pdf_ir(BytesIO(source), filename="links.pdf")
    with pytest.raises(UnsupportedEditError) as exc:
        resolve_pdf_link_uri_edit(document, source, _edit(document, uri="https://example.com/old"))
    assert exc.value.details["reason"] == "pdf.link.semantic_noop"


def test_pdf_link_routing_rejects_empty_uri() -> None:
    source = _link_pdf()
    document = read_pdf_ir(BytesIO(source), filename="links.pdf")
    with pytest.raises(UnsupportedEditError) as exc:
        resolve_pdf_link_uri_edit(document, source, _edit(document, uri=""))
    assert exc.value.details["reason"] == "pdf.link.uri_empty"
