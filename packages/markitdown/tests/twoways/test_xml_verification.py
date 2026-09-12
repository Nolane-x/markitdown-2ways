from __future__ import annotations

import codecs
from io import BytesIO

import pytest

from markitdown.twoways._errors import RoundTripVerificationError
from markitdown.twoways.formats.xml import writer as xml_writer
from markitdown.twoways.formats.xml.reader import read_xml_ir


def _verify(document, candidate: bytes, requested: dict[str, str]) -> None:
    xml_writer._verify_candidate(
        document,
        candidate,
        xml_writer._representation(document, require_writable=False),
        requested,
    )


def test_candidate_verifier_rejects_added_or_removed_ownership_path() -> None:
    source = b"<r><a>1</a><b>2</b></r>"
    document = read_xml_ir(BytesIO(source), filename="data.xml")

    with pytest.raises(RoundTripVerificationError, match="path"):
        _verify(
            document,
            b"<r><a>1</a><b>3</b><c>4</c></r>",
            {"/r[1]/b[1]/#text[1]": "3"},
        )


def test_candidate_verifier_rejects_sibling_reorder() -> None:
    source = b"<r><a>1</a><b>2</b></r>"
    document = read_xml_ir(BytesIO(source), filename="data.xml")

    with pytest.raises(RoundTripVerificationError, match="topology"):
        _verify(
            document,
            b"<r><b>3</b><a>1</a></r>",
            {"/r[1]/b[1]/#text[1]": "3"},
        )


def test_candidate_verifier_rejects_namespace_binding_change() -> None:
    source = b'<r xmlns:m="urn:a"><a>1</a><b>2</b></r>'
    document = read_xml_ir(BytesIO(source), filename="data.xml")

    with pytest.raises(RoundTripVerificationError, match="namespace"):
        _verify(
            document,
            b'<r xmlns:m="urn:b"><a>1</a><b>3</b></r>',
            {"/r[1]/b[1]/#text[1]": "3"},
        )


def test_candidate_verifier_rejects_attribute_expanded_identity_change() -> None:
    source = b'<r xmlns:m="urn:a" m:x="v"><b>2</b></r>'
    document = read_xml_ir(BytesIO(source), filename="data.xml")

    with pytest.raises(RoundTripVerificationError, match="path|expanded|namespace"):
        _verify(
            document,
            b'<r xmlns:m="urn:b" m:x="v"><b>3</b></r>',
            {"/r[1]/b[1]/#text[1]": "3"},
        )


def test_candidate_verifier_rejects_requested_semantic_mismatch() -> None:
    source = b"<r><a>1</a><b>2</b></r>"
    document = read_xml_ir(BytesIO(source), filename="data.xml")

    with pytest.raises(RoundTripVerificationError, match="requested"):
        _verify(
            document,
            b"<r><a>1</a><b>4</b></r>",
            {"/r[1]/b[1]/#text[1]": "3"},
        )


def test_candidate_verifier_rejects_unrequested_reference_raw_drift() -> None:
    source = b"<r><a>&#65;</a><b>2</b></r>"
    document = read_xml_ir(BytesIO(source), filename="data.xml")

    with pytest.raises(RoundTripVerificationError, match="raw"):
        _verify(
            document,
            b"<r><a>A</a><b>3</b></r>",
            {"/r[1]/b[1]/#text[1]": "3"},
        )


def test_candidate_verifier_rejects_bom_representation_drift() -> None:
    source = codecs.BOM_UTF8 + b'<r><a>1</a><b>2</b></r>'
    document = read_xml_ir(BytesIO(source), filename="data.xml")

    with pytest.raises(RoundTripVerificationError, match="representation"):
        _verify(
            document,
            b"<r><a>1</a><b>3</b></r>",
            {"/r[1]/b[1]/#text[1]": "3"},
        )


def test_candidate_verifier_rejects_xml_declaration_lexical_drift() -> None:
    source = b"<?xml version='1.0' encoding='UTF-8'?><r><a>1</a><b>2</b></r>"
    document = read_xml_ir(BytesIO(source), filename="data.xml")

    with pytest.raises(RoundTripVerificationError, match="declaration"):
        _verify(
            document,
            b'<?xml version="1.0" encoding="UTF-8"?><r><a>1</a><b>3</b></r>',
            {"/r[1]/b[1]/#text[1]": "3"},
        )
