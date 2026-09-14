from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pdfplumber
import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    RectangleObject,
    TextStringObject,
)

from markitdown.twoways._errors import RoundTripVerificationError
from markitdown.twoways.formats.pdf.reader import read_pdf_ir
from markitdown.twoways.formats.pdf.writer import patch_pdf
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition


def _link_pdf() -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    writer.add_metadata({"/Title": "H10 verification", "/Author": "Ada"})
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


def _link_edit(document, uri: str = "https://example.com/new") -> EditOperation:
    node = next(
        node for node in document.nodes.values() if node.semantic_role == "pdf-link-uri"
    )
    return EditOperation(
        operation_id="link-oracle",
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


class _FakePdf:
    def __init__(self, hyperlinks):
        self.pages = [SimpleNamespace(height=200.0, hyperlinks=hyperlinks)]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _hyperlink(uri: str) -> dict[str, object]:
    return {
        "uri": uri,
        "x0": 10.0,
        "x1": 120.0,
        "top": 170.0,
        "bottom": 190.0,
    }


def _install_oracle(monkeypatch, responses, calls: list[object]) -> None:
    pending = iter(responses)

    def fake_open(stream):
        calls.append(stream)
        return _FakePdf(next(pending))

    monkeypatch.setattr(pdfplumber, "open", fake_open)


def test_pdf_link_verifier_invokes_pdfplumber_oracle(monkeypatch) -> None:
    source = _link_pdf()
    document = read_pdf_ir(BytesIO(source), filename="links.pdf")
    calls: list[object] = []
    _install_oracle(
        monkeypatch,
        (
            [_hyperlink("https://example.com/old")],
            [_hyperlink("https://example.com/new")],
        ),
        calls,
    )

    output = BytesIO()
    patch_pdf(
        document,
        BytesIO(source),
        output,
        edits=(_link_edit(document),),
    )

    assert len(calls) == 2
    assert output.getvalue().startswith(source)


def test_pdf_link_verifier_rejects_pdfplumber_uri_disagreement_before_output(
    monkeypatch,
) -> None:
    source = _link_pdf()
    document = read_pdf_ir(BytesIO(source), filename="links.pdf")
    calls: list[object] = []
    _install_oracle(
        monkeypatch,
        (
            [_hyperlink("https://example.com/old")],
            [_hyperlink("https://example.com/wrong")],
        ),
        calls,
    )

    output = BytesIO()
    with pytest.raises(RoundTripVerificationError) as exc:
        patch_pdf(
            document,
            BytesIO(source),
            output,
            edits=(_link_edit(document),),
        )

    assert exc.value.details["reason"] == "pdf.candidate.pdfplumber_link"
    assert output.getvalue() == b""


def test_pdf_link_verifier_rejects_ambiguous_pdfplumber_match_before_output(
    monkeypatch,
) -> None:
    source = _link_pdf()
    document = read_pdf_ir(BytesIO(source), filename="links.pdf")
    calls: list[object] = []
    matching = _hyperlink("https://example.com/new")
    _install_oracle(
        monkeypatch,
        (
            [_hyperlink("https://example.com/old")],
            [matching, dict(matching)],
        ),
        calls,
    )

    output = BytesIO()
    with pytest.raises(RoundTripVerificationError) as exc:
        patch_pdf(
            document,
            BytesIO(source),
            output,
            edits=(_link_edit(document),),
        )

    assert exc.value.details["reason"] == "pdf.candidate.pdfplumber_link"
    assert output.getvalue() == b""
