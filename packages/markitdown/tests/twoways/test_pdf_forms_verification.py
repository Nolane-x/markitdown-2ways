from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pytest

from markitdown.twoways._errors import RoundTripVerificationError
from markitdown.twoways.formats.pdf import verification as pdf_verification
from markitdown.twoways.formats.pdf import writer as pdf_writer
from markitdown.twoways.formats.pdf.parser import parse_pdf_source
from markitdown.twoways.formats.pdf.reader import read_pdf_ir
from markitdown.twoways.formats.pdf.routing import resolve_pdf_text_field_value_edit
from markitdown.twoways.formats.pdf.verification import verify_pdf_candidate
from markitdown.twoways.formats.pdf.writer import patch_pdf
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition

from ._pdf_fixtures import make_text_form_pdf


def _form_node(document, field_name: str = "customer.name"):
    return next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "pdf-form-text-value"
        and node.metadata.get("pdf.form_field_name") == field_name
    )


def _form_edit(
    document, value: str, field_name: str = "customer.name"
) -> EditOperation:
    node = _form_node(document, field_name)
    return EditOperation(
        operation_id=f"form-{field_name}",
        type="update_pdf_text_field_value",
        target_node_id=node.node_id,
        precondition=EditPrecondition(expected_old_value=node.payload.text),
        payload={
            "field_name": field_name,
            "old_value": node.payload.text,
            "value": value,
        },
    )


def _candidate(
    monkeypatch: pytest.MonkeyPatch,
    source: bytes,
    value: str = "Bob",
    field_name: str = "customer.name",
):
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    edit = _form_edit(document, value, field_name)
    routed = resolve_pdf_text_field_value_edit(document, source, edit)
    output = BytesIO()
    monkeypatch.setattr(
        pdf_writer, "verify_pdf_candidate", lambda *args, **kwargs: None
    )
    patch_pdf(document, BytesIO(source), output, edits=(edit,))
    return routed, output.getvalue()


def _assert_reason(
    exc: pytest.ExceptionInfo[RoundTripVerificationError], reason: str
) -> None:
    assert exc.value.details["reason"] == reason


def test_pdf_form_verifier_accepts_exact_authorized_value_only_increment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = make_text_form_pdf()
    routed, candidate = _candidate(monkeypatch, source)

    verify_pdf_candidate(
        source,
        candidate,
        (routed,),
        changed_objects=(routed.field_objgen,),
    )


def test_pdf_form_verifier_rejects_unexpected_increment_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = make_text_form_pdf()
    routed, candidate = _candidate(monkeypatch, source)

    with pytest.raises(RoundTripVerificationError) as exc:
        verify_pdf_candidate(
            source,
            candidate,
            (routed,),
            changed_objects=(routed.field_objgen, (999, 0)),
        )
    _assert_reason(exc, "pdf.writer.unexpected_increment_object")


def test_pdf_form_verifier_rejects_acroform_identity_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = make_text_form_pdf()
    routed, candidate = _candidate(monkeypatch, source)
    source_parsed = parse_pdf_source(source)
    candidate_parsed = parse_pdf_source(candidate)
    drifted = replace(
        candidate_parsed,
        snapshot=replace(candidate_parsed.snapshot, acroform_objgen=(999, 0)),
    )
    monkeypatch.setattr(
        pdf_verification,
        "parse_pdf_source",
        lambda data, **kwargs: source_parsed if data == source else drifted,
    )

    with pytest.raises(RoundTripVerificationError) as exc:
        verify_pdf_candidate(
            source,
            candidate,
            (routed,),
            changed_objects=(routed.field_objgen,),
        )
    _assert_reason(exc, "pdf.candidate.acroform_authority")


def test_pdf_form_verifier_rejects_root_fields_topology_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = make_text_form_pdf()
    routed, candidate = _candidate(monkeypatch, source)
    source_parsed = parse_pdf_source(source)
    candidate_parsed = parse_pdf_source(candidate)
    drifted = replace(
        candidate_parsed,
        snapshot=replace(
            candidate_parsed.snapshot, acroform_fields_topology=((999, 0),)
        ),
    )
    monkeypatch.setattr(
        pdf_verification,
        "parse_pdf_source",
        lambda data, **kwargs: source_parsed if data == source else drifted,
    )

    with pytest.raises(RoundTripVerificationError) as exc:
        verify_pdf_candidate(
            source,
            candidate,
            (routed,),
            changed_objects=(routed.field_objgen,),
        )
    _assert_reason(exc, "pdf.candidate.form_topology")


def test_pdf_form_verifier_rejects_page_binding_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = make_text_form_pdf()
    routed, candidate = _candidate(monkeypatch, source)
    source_parsed = parse_pdf_source(source)
    candidate_parsed = parse_pdf_source(candidate)
    drifted = replace(
        candidate_parsed,
        snapshot=replace(
            candidate_parsed.snapshot,
            form_field_bindings=((routed.field_objgen, 9, 9),),
        ),
    )
    monkeypatch.setattr(
        pdf_verification,
        "parse_pdf_source",
        lambda data, **kwargs: source_parsed if data == source else drifted,
    )

    with pytest.raises(RoundTripVerificationError) as exc:
        verify_pdf_candidate(
            source,
            candidate,
            (routed,),
            changed_objects=(routed.field_objgen,),
        )
    _assert_reason(exc, "pdf.candidate.form_binding")


def test_pdf_form_verifier_rejects_target_immutable_digest_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = make_text_form_pdf()
    routed, candidate = _candidate(monkeypatch, source)
    source_parsed = parse_pdf_source(source)
    candidate_parsed = parse_pdf_source(candidate)
    target = candidate_parsed.form_fields[0]
    drifted = replace(
        candidate_parsed,
        form_fields=(replace(target, immutable_digest="0" * 64),),
    )
    monkeypatch.setattr(
        pdf_verification,
        "parse_pdf_source",
        lambda data, **kwargs: source_parsed if data == source else drifted,
    )

    with pytest.raises(RoundTripVerificationError) as exc:
        verify_pdf_candidate(
            source,
            candidate,
            (routed,),
            changed_objects=(routed.field_objgen,),
        )
    _assert_reason(exc, "pdf.candidate.form_immutable")


def test_pdf_form_verifier_rejects_sibling_value_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = make_text_form_pdf(second_field=True)
    routed, candidate = _candidate(monkeypatch, source)
    source_parsed = parse_pdf_source(source)
    candidate_parsed = parse_pdf_source(candidate)
    target, sibling = candidate_parsed.form_fields
    drifted_sibling = replace(sibling, value="tampered@example.test")
    drifted = replace(candidate_parsed, form_fields=(target, drifted_sibling))
    monkeypatch.setattr(
        pdf_verification,
        "parse_pdf_source",
        lambda data, **kwargs: source_parsed if data == source else drifted,
    )

    with pytest.raises(RoundTripVerificationError) as exc:
        verify_pdf_candidate(
            source,
            candidate,
            (routed,),
            changed_objects=(routed.field_objgen,),
        )
    _assert_reason(exc, "pdf.candidate.form_sibling")


def test_pdf_form_verifier_rejects_need_appearances_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = make_text_form_pdf()
    routed, candidate = _candidate(monkeypatch, source)
    source_parsed = parse_pdf_source(source)
    candidate_parsed = parse_pdf_source(candidate)
    drifted = replace(
        candidate_parsed,
        snapshot=replace(candidate_parsed.snapshot, need_appearances=False),
    )
    monkeypatch.setattr(
        pdf_verification,
        "parse_pdf_source",
        lambda data, **kwargs: source_parsed if data == source else drifted,
    )

    with pytest.raises(RoundTripVerificationError) as exc:
        verify_pdf_candidate(
            source,
            candidate,
            (routed,),
            changed_objects=(routed.field_objgen,),
        )
    _assert_reason(exc, "pdf.candidate.need_appearances")


def test_pdf_form_verifier_rejects_requested_value_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = make_text_form_pdf()
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    requested = resolve_pdf_text_field_value_edit(
        document, source, _form_edit(document, "Bob")
    )
    _, candidate = _candidate(monkeypatch, source, value="Mallory")

    with pytest.raises(RoundTripVerificationError) as exc:
        verify_pdf_candidate(
            source,
            candidate,
            (requested,),
            changed_objects=(requested.field_objgen,),
        )
    _assert_reason(exc, "pdf.candidate.form_value")


def test_pdf_form_verifier_requires_independent_pdfminer_agreement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = make_text_form_pdf()
    routed, candidate = _candidate(monkeypatch, source)
    monkeypatch.setattr(
        pdf_verification,
        "_pdfminer_form_inventory",
        lambda data, limits: {"customer.name": (routed.field_objgen, "Mallory")},
        raising=False,
    )

    with pytest.raises(RoundTripVerificationError) as exc:
        verify_pdf_candidate(
            source,
            candidate,
            (routed,),
            changed_objects=(routed.field_objgen,),
        )
    _assert_reason(exc, "pdf.candidate.pdfminer_form")
