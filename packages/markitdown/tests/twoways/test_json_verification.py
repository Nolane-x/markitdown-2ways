from __future__ import annotations

import codecs
from io import BytesIO

import pytest

from markitdown.twoways._errors import RoundTripVerificationError
from markitdown.twoways.formats.json import writer as json_writer
from markitdown.twoways.formats.json.reader import read_json_ir


def _verify(document, candidate: bytes, requested: dict[str, object]) -> None:
    json_writer._verify_candidate(
        document,
        candidate,
        json_writer._representation(document),
        requested,
    )


def test_candidate_verifier_rejects_unrequested_scalar_semantic_change() -> None:
    source = b'{"a":1,"b":2}'
    document = read_json_ir(BytesIO(source), filename="data.json")

    with pytest.raises(RoundTripVerificationError, match="unrequested"):
        _verify(document, b'{"a":9,"b":3}', {"/b": 3})


def test_candidate_verifier_rejects_unrequested_raw_lexical_drift() -> None:
    source = b'{"a":"\\u0041","b":2}'
    document = read_json_ir(BytesIO(source), filename="data.json")

    with pytest.raises(RoundTripVerificationError, match="raw"):
        _verify(document, b'{"a":"A","b":3}', {"/b": 3})


def test_candidate_verifier_rejects_pointer_set_change() -> None:
    source = b'{"a":1,"b":2}'
    document = read_json_ir(BytesIO(source), filename="data.json")

    with pytest.raises(RoundTripVerificationError, match="pointer"):
        _verify(document, b'{"a":1,"b":3,"c":4}', {"/b": 3})


def test_candidate_verifier_rejects_child_order_change() -> None:
    source = b'{"a":1,"b":2}'
    document = read_json_ir(BytesIO(source), filename="data.json")

    with pytest.raises(RoundTripVerificationError, match="topology"):
        _verify(document, b'{"b":3,"a":1}', {"/b": 3})


def test_candidate_verifier_rejects_requested_semantic_mismatch() -> None:
    source = b'{"a":1,"b":2}'
    document = read_json_ir(BytesIO(source), filename="data.json")

    with pytest.raises(RoundTripVerificationError, match="requested"):
        _verify(document, b'{"a":1,"b":4}', {"/b": 3})


def test_candidate_verifier_rejects_bom_representation_drift() -> None:
    source = codecs.BOM_UTF8 + b'{"a":1,"b":2}'
    document = read_json_ir(BytesIO(source), filename="data.json")

    with pytest.raises(RoundTripVerificationError, match="representation"):
        _verify(document, b'{"a":1,"b":3}', {"/b": 3})
