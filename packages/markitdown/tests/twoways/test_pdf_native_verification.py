from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfWriter

from markitdown.twoways._errors import RoundTripVerificationError
from markitdown.twoways.formats.pdf.limits import PdfNativeLimits
from markitdown.twoways.formats.pdf.reader import read_pdf_ir
from markitdown.twoways.formats.pdf.routing import resolve_pdf_metadata_edit
from markitdown.twoways.formats.pdf.verification import verify_pdf_candidate
from markitdown.twoways.ir.edits import EditOperation

from ._pdf_fixtures import make_metadata_pdf


def _title_edit(source: bytes, value: str = "Updated"):
    document = read_pdf_ir(BytesIO(source), filename="sample.pdf")
    title = next(
        node
        for node in document.nodes.values()
        if node.metadata.get("pdf.info_key") == "/Title"
    )
    edit = EditOperation(
        operation_id="title",
        type="update_pdf_metadata",
        target_node_id=title.node_id,
        payload={"field": "Title", "value": value},
    )
    return resolve_pdf_metadata_edit(document, source, edit)


def _candidate(source: bytes, metadata: dict[str, str], *, add_page: bool = False):
    writer = PdfWriter(BytesIO(source), incremental=True, strict=True)
    writer.add_metadata(metadata)
    if add_page:
        writer.add_blank_page(width=612, height=792)
    changed = tuple(
        (ref.idnum, ref.generation) for ref in writer.list_objects_in_increment()
    )
    output = BytesIO()
    writer.write(output)
    return output.getvalue(), changed


def _assert_reason(exc, reason: str) -> None:
    assert exc.value.details["reason"] == reason


def test_pdf_verifier_accepts_authorized_increment_and_pdfminer_agrees() -> None:
    source = make_metadata_pdf()
    routed = (_title_edit(source, "Café Updated"),)
    candidate, changed = _candidate(source, {"/Title": "Café Updated"})

    verify_pdf_candidate(source, candidate, routed, changed_objects=changed)


def test_pdf_verifier_rejects_broken_source_prefix() -> None:
    source = make_metadata_pdf()
    routed = (_title_edit(source),)
    candidate, changed = _candidate(source, {"/Title": "Updated"})
    broken = b"X" + candidate[1:]

    with pytest.raises(RoundTripVerificationError) as exc:
        verify_pdf_candidate(source, broken, routed, changed_objects=changed)
    _assert_reason(exc, "pdf.candidate.source_prefix")


def test_pdf_verifier_rejects_unexpected_changed_object() -> None:
    source = make_metadata_pdf()
    routed = (_title_edit(source),)
    candidate, changed = _candidate(source, {"/Title": "Updated"})

    with pytest.raises(RoundTripVerificationError) as exc:
        verify_pdf_candidate(
            source,
            candidate,
            routed,
            changed_objects=changed + ((1, 0),),
        )
    _assert_reason(exc, "pdf.writer.unexpected_increment_object")


def test_pdf_verifier_rejects_unrequested_metadata_drift() -> None:
    source = make_metadata_pdf()
    routed = (_title_edit(source),)
    candidate, changed = _candidate(
        source,
        {"/Title": "Updated", "/Author": "Changed"},
    )

    with pytest.raises(RoundTripVerificationError) as exc:
        verify_pdf_candidate(source, candidate, routed, changed_objects=changed)
    _assert_reason(exc, "pdf.candidate.unrequested_metadata")


def test_pdf_verifier_rejects_requested_semantic_mismatch() -> None:
    source = make_metadata_pdf()
    routed = (_title_edit(source, "Updated"),)
    candidate, changed = _candidate(source, {"/Title": "Wrong"})

    with pytest.raises(RoundTripVerificationError) as exc:
        verify_pdf_candidate(source, candidate, routed, changed_objects=changed)
    _assert_reason(exc, "pdf.candidate.requested_semantic")


def test_pdf_verifier_rejects_page_count_drift() -> None:
    source = make_metadata_pdf()
    routed = (_title_edit(source),)
    candidate, _changed = _candidate(
        source,
        {"/Title": "Updated"},
        add_page=True,
    )

    with pytest.raises(RoundTripVerificationError) as exc:
        verify_pdf_candidate(
            source,
            candidate,
            routed,
            changed_objects=((4, 0),),
            limits=PdfNativeLimits(),
        )
    _assert_reason(exc, "pdf.candidate.page_count")
