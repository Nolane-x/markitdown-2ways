from __future__ import annotations

from dataclasses import replace
from io import BytesIO

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
from markitdown.twoways.formats.pdf import verification as pdf_verification
from markitdown.twoways.formats.pdf.parser import parse_pdf_source
from markitdown.twoways.formats.pdf.routing import PdfRoutedLinkEdit


def _pdf_with_link_and_sibling_annotation() -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    writer.add_metadata({"/Title": "H10 topology"})

    action = DictionaryObject(
        {
            NameObject("/S"): NameObject("/URI"),
            NameObject("/URI"): TextStringObject("https://example.com/old"),
        }
    )
    link = DictionaryObject(
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
            NameObject("/Border"): ArrayObject(
                [NumberObject(0), NumberObject(0), NumberObject(0)]
            ),
            NameObject("/A"): action,
        }
    )
    sibling = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Text"),
            NameObject("/Rect"): RectangleObject(
                [
                    NumberObject(140),
                    NumberObject(10),
                    NumberObject(180),
                    NumberObject(40),
                ]
            ),
            NameObject("/Contents"): TextStringObject("sibling note"),
        }
    )
    page[NameObject("/Annots")] = ArrayObject(
        [writer._add_object(link), writer._add_object(sibling)]
    )

    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


def _routed(link, uri: str = "https://example.com/new") -> PdfRoutedLinkEdit:
    return PdfRoutedLinkEdit(
        operation_id="topology-link",
        target_node_id="link-node",
        page_index=link.page_index,
        annotation_index=link.annotation_index,
        annotation_objgen=link.annotation_objgen,
        action_objgen=link.action_objgen,
        owner_kind=link.owner_kind,
        mutation_owner_objgen=link.mutation_owner_objgen,
        locator_digest=link.locator_digest,
        old_uri=link.uri,
        uri=uri,
    )


def test_pdf_parser_records_complete_page_and_annotation_topology() -> None:
    parsed = parse_pdf_source(_pdf_with_link_and_sibling_annotation())

    assert len(parsed.snapshot.page_objgens) == 1
    assert parsed.snapshot.page_objgens[0] is not None
    assert len(parsed.snapshot.annotation_topology) == 1
    assert len(parsed.snapshot.annotation_topology[0]) == 2
    assert all(objgen is not None for objgen in parsed.snapshot.annotation_topology[0])
    assert len(parsed.snapshot.annotation_fingerprints) == 1
    assert len(parsed.snapshot.annotation_fingerprints[0]) == 2
    assert all(
        len(fingerprint) == 64
        for fingerprint in parsed.snapshot.annotation_fingerprints[0]
    )

    link = parsed.links[0]
    assert parsed.snapshot.annotation_topology[0][0] == link.annotation_objgen
    assert len(link.immutable_digest) == 64


def test_pdf_topology_verifier_rejects_page_identity_drift() -> None:
    parsed = parse_pdf_source(_pdf_with_link_and_sibling_annotation())
    candidate = replace(parsed.snapshot, page_objgens=((999, 0),))

    with pytest.raises(RoundTripVerificationError) as exc:
        pdf_verification._verify_annotation_authority(
            parsed.snapshot,
            candidate,
            direct_action_targets=frozenset({(0, 0)}),
        )

    assert exc.value.details["reason"] == "pdf.candidate.page_identity"


def test_pdf_topology_verifier_rejects_annotation_order_drift() -> None:
    parsed = parse_pdf_source(_pdf_with_link_and_sibling_annotation())
    candidate = replace(
        parsed.snapshot,
        annotation_topology=(tuple(reversed(parsed.snapshot.annotation_topology[0])),),
    )

    with pytest.raises(RoundTripVerificationError) as exc:
        pdf_verification._verify_annotation_authority(
            parsed.snapshot,
            candidate,
            direct_action_targets=frozenset({(0, 0)}),
        )

    assert exc.value.details["reason"] == "pdf.candidate.annotation_topology"


def test_pdf_topology_verifier_rejects_unauthorized_sibling_drift() -> None:
    parsed = parse_pdf_source(_pdf_with_link_and_sibling_annotation())
    fingerprints = list(parsed.snapshot.annotation_fingerprints[0])
    fingerprints[1] = "0" * 64
    candidate = replace(
        parsed.snapshot,
        annotation_fingerprints=(tuple(fingerprints),),
    )

    with pytest.raises(RoundTripVerificationError) as exc:
        pdf_verification._verify_annotation_authority(
            parsed.snapshot,
            candidate,
            direct_action_targets=frozenset({(0, 0)}),
        )

    assert exc.value.details["reason"] == "pdf.candidate.annotation_sibling"


def test_pdf_topology_verifier_allows_direct_target_raw_fingerprint_change() -> None:
    parsed = parse_pdf_source(_pdf_with_link_and_sibling_annotation())
    fingerprints = list(parsed.snapshot.annotation_fingerprints[0])
    fingerprints[0] = "0" * 64
    candidate = replace(
        parsed.snapshot,
        annotation_fingerprints=(tuple(fingerprints),),
    )

    pdf_verification._verify_annotation_authority(
        parsed.snapshot,
        candidate,
        direct_action_targets=frozenset({(0, 0)}),
    )


def test_pdf_link_verifier_rejects_immutable_target_semantic_drift() -> None:
    parsed = parse_pdf_source(_pdf_with_link_and_sibling_annotation())
    link = parsed.links[0]
    candidate_link = replace(
        link,
        uri="https://example.com/new",
        immutable_digest="0" * 64,
    )
    candidate = replace(parsed, links=(candidate_link,))

    with pytest.raises(RoundTripVerificationError) as exc:
        pdf_verification._verify_links(parsed, candidate, (_routed(link),))

    assert exc.value.details["reason"] == "pdf.candidate.link_binding"
