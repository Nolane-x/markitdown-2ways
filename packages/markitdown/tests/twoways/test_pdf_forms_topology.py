from __future__ import annotations

import pytest

from markitdown.twoways.formats.pdf.limits import PdfNativeLimits
from markitdown.twoways.formats.pdf.model import PdfParseError
from markitdown.twoways.formats.pdf.parser import parse_pdf_source

from ._pdf_fixtures import make_text_form_pdf


def test_parser_records_root_field_order_and_page_bindings() -> None:
    parsed = parse_pdf_source(make_text_form_pdf(second_field=True))
    snapshot = parsed.snapshot

    assert snapshot.acroform_objgen == (5, 0)
    assert snapshot.acroform_fields_topology == ((6, 0), (7, 0))
    assert snapshot.form_field_bindings == (
        ((6, 0), 0, 0),
        ((7, 0), 0, 1),
    )
    assert tuple(objgen for objgen, _ in snapshot.form_field_fingerprints) == (
        (6, 0),
        (7, 0),
    )
    assert all(len(digest) == 64 for _, digest in snapshot.form_field_fingerprints)


def test_text_field_immutable_digest_masks_only_value() -> None:
    first = parse_pdf_source(make_text_form_pdf(value="Alice")).form_fields[0]
    second = parse_pdf_source(make_text_form_pdf(value="Bob")).form_fields[0]

    assert first.locator_digest != second.locator_digest
    assert first.immutable_digest == second.immutable_digest


def test_text_field_immutable_digest_binds_other_semantics() -> None:
    baseline = parse_pdf_source(make_text_form_pdf(value="Alice")).form_fields[0]
    changed = parse_pdf_source(
        make_text_form_pdf(value="Alice", max_len=20)
    ).form_fields[0]

    assert baseline.immutable_digest != changed.immutable_digest


def test_parser_enforces_field_tree_depth_limit() -> None:
    with pytest.raises(PdfParseError) as excinfo:
        parse_pdf_source(
            make_text_form_pdf(with_parent=True),
            limits=PdfNativeLimits(max_field_tree_depth=1),
        )

    assert excinfo.value.reason == "pdf.form.tree_ambiguous"


def test_duplicate_root_owner_fails_closed_without_recursion() -> None:
    parsed = parse_pdf_source(make_text_form_pdf(duplicate_field_name=True))

    assert len(parsed.form_fields) == 2
    assert all(field.reason_code == "pdf.form.tree_ambiguous" for field in parsed.form_fields)
