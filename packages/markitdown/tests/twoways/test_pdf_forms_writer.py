from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfReader

from markitdown.twoways._errors import UnsupportedEditError
from markitdown.twoways.formats.pdf import writer as pdf_writer
from markitdown.twoways.formats.pdf.limits import PdfNativeLimits
from markitdown.twoways.formats.pdf.parser import parse_pdf_source
from markitdown.twoways.formats.pdf.reader import read_pdf_ir
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


def _link_node(document):
    return next(
        node for node in document.nodes.values() if node.semantic_role == "pdf-link-uri"
    )


def _metadata_node(document, key: str = "/Title"):
    return next(
        node
        for node in document.nodes.values()
        if node.metadata.get("pdf.info_key") == key
    )


def _form_edit(
    document,
    value: str,
    *,
    field_name: str = "customer.name",
    operation_id: str = "form-1",
) -> EditOperation:
    node = _form_node(document, field_name)
    return EditOperation(
        operation_id=operation_id,
        type="update_pdf_text_field_value",
        target_node_id=node.node_id,
        precondition=EditPrecondition(expected_old_value=node.payload.text),
        payload={
            "field_name": field_name,
            "old_value": node.payload.text,
            "value": value,
        },
    )


def _link_edit(document, uri: str) -> EditOperation:
    node = _link_node(document)
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


def _metadata_edit(document, value: str) -> EditOperation:
    node = _metadata_node(document)
    return EditOperation(
        operation_id="metadata-title",
        type="update_pdf_metadata",
        target_node_id=node.node_id,
        precondition=EditPrecondition(expected_old_value=node.payload.text),
        payload={"field": node.metadata["pdf.info_field"], "value": value},
    )


def _form_values(data: bytes) -> dict[str, str]:
    return {
        field.field_name: field.value for field in parse_pdf_source(data).form_fields
    }


def _disable_verifier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pdf_writer, "verify_pdf_candidate", lambda *args, **kwargs: None
    )


def test_pdf_writer_updates_one_text_field_incrementally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_verifier(monkeypatch)
    source = make_text_form_pdf()
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    output = BytesIO()

    result = patch_pdf(
        document,
        BytesIO(source),
        output,
        edits=(_form_edit(document, "Bob"),),
    )
    candidate = output.getvalue()

    assert candidate.startswith(source)
    assert len(candidate) > len(source)
    assert _form_values(candidate)["customer.name"] == "Bob"
    assert result.bytes_written == len(candidate)
    assert result.fidelity.claimed_tier == "high"


def test_pdf_writer_updates_two_distinct_text_fields_atomically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_verifier(monkeypatch)
    source = make_text_form_pdf(second_field=True)
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    output = BytesIO()

    patch_pdf(
        document,
        BytesIO(source),
        output,
        edits=(
            _form_edit(document, "Bob", operation_id="form-name"),
            _form_edit(
                document,
                "b@example.test",
                field_name="customer.email",
                operation_id="form-email",
            ),
        ),
    )

    values = _form_values(output.getvalue())
    assert values["customer.name"] == "Bob"
    assert values["customer.email"] == "b@example.test"


def test_pdf_writer_applies_metadata_link_and_form_in_one_increment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_verifier(monkeypatch)
    source = make_text_form_pdf(with_uri_link=True)
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    output = BytesIO()

    patch_pdf(
        document,
        BytesIO(source),
        output,
        edits=(
            _metadata_edit(document, "Updated H11 title"),
            _link_edit(document, "https://example.test/new"),
            _form_edit(document, "Bob"),
        ),
    )

    candidate = output.getvalue()
    strict = PdfReader(BytesIO(candidate), strict=True)
    reparsed = parse_pdf_source(candidate)
    assert candidate.startswith(source)
    assert strict.metadata is not None
    assert strict.metadata.title == "Updated H11 title"
    assert reparsed.links[0].uri == "https://example.test/new"
    assert {field.field_name: field.value for field in reparsed.form_fields}[
        "customer.name"
    ] == "Bob"


def test_pdf_writer_rejects_duplicate_form_target_before_output() -> None:
    source = make_text_form_pdf()
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError) as exc:
        patch_pdf(
            document,
            BytesIO(source),
            output,
            edits=(
                _form_edit(document, "Bob", operation_id="form-1"),
                _form_edit(document, "Carol", operation_id="form-2"),
            ),
        )

    assert exc.value.details["reason"] == "pdf.form.duplicate_target"
    assert output.getvalue() == b""


def test_pdf_writer_rejects_cross_kind_native_owner_collision_before_output() -> None:
    source = make_text_form_pdf(shared_link_owner=True)
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    assert _form_node(document).metadata["pdf.form_field_objgen"] == (6, 0)
    assert _link_node(document).metadata["pdf.mutation_owner_objgen"] == (6, 0)
    output = BytesIO()

    with pytest.raises(UnsupportedEditError) as exc:
        patch_pdf(
            document,
            BytesIO(source),
            output,
            edits=(
                _form_edit(document, "Bob"),
                _link_edit(document, "https://example.test/new"),
            ),
        )

    assert exc.value.details["reason"] == "pdf.writer.owner_collision"
    assert output.getvalue() == b""


def test_pdf_writer_rejects_transaction_total_form_value_limit_before_output() -> None:
    source = make_text_form_pdf(second_field=True)
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    output = BytesIO()
    limits = PdfNativeLimits(max_total_form_value_chars=25)

    with pytest.raises(UnsupportedEditError) as exc:
        patch_pdf(
            document,
            BytesIO(source),
            output,
            edits=(
                _form_edit(document, "ABCDEFGHIJ", operation_id="form-name"),
                _form_edit(
                    document,
                    "abcdefghijklmnopqrst",
                    field_name="customer.email",
                    operation_id="form-email",
                ),
            ),
            limits=limits,
        )

    assert exc.value.details["reason"] == "pdf.form.total_value_too_large"
    assert output.getvalue() == b""
