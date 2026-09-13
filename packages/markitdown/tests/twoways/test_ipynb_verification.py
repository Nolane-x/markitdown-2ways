from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways._errors import RoundTripVerificationError
from markitdown.twoways.formats.ipynb.parser import parse_ipynb_source
from markitdown.twoways.formats.ipynb.verification import verify_ipynb_candidate


def _source() -> bytes:
    return (
        b'{"cells":['
        b'{"cell_type":"markdown","id":"m1","metadata":{"tags":["keep"]},'
        b'"source":["a\\n","b"]},'
        b'{"cell_type":"code","execution_count":7,"metadata":{"x":1},'
        b'"outputs":[{"output_type":"stream","name":"stdout","text":["ok\\n"]}],'
        b'"source":"print(1)"}'
        b'],"metadata":{"kernelspec":{"name":"python3"}},'
        b'"nbformat":4,"nbformat_minor":5}'
    )


def _verify(candidate: bytes, requested=None) -> None:
    source = _source()
    original = parse_ipynb_source(source)
    verify_ipynb_candidate(
        original,
        candidate,
        encoding=original.representation.encoding,
        requested=requested or {},
    )


def test_candidate_accepts_only_requested_logical_source_change() -> None:
    candidate = _source().replace(b'"a\\n"', b'"A\\n"', 1)
    _verify(candidate, {0: "A\nb"})


@pytest.mark.parametrize(
    "candidate",
    [
        _source().replace(b'"nbformat_minor":5', b'"nbformat_minor":4'),
        _source().replace(b'"python3"', b'"python2"'),
        _source().replace(b'"cell_type":"code"', b'"cell_type":"raw"'),
        _source().replace(b'"id":"m1"', b'"id":"m2"'),
        _source().replace(b'"execution_count":7', b'"execution_count":8'),
        _source().replace(b'"x":1', b'"x":2'),
        _source().replace(b'"ok\\n"', b'"changed\\n"'),
        _source().replace(b'["a\\n","b"]', b'"a\\nb"'),
        _source().replace(b'["a\\n","b"]', b'["a\\n","b",""]'),
    ],
)
def test_candidate_rejects_notebook_or_non_source_drift(candidate: bytes) -> None:
    with pytest.raises(RoundTripVerificationError):
        _verify(candidate)


def test_candidate_rejects_wrong_requested_source() -> None:
    candidate = _source().replace(b'"a\\n"', b'"A\\n"', 1)
    with pytest.raises(RoundTripVerificationError):
        _verify(candidate, {0: "WRONG"})


def test_unrequested_source_requires_raw_token_identity() -> None:
    source = (
        b'{"cells":[{"cell_type":"markdown","metadata":{},'
        b'"source":"\\u0061"}],"metadata":{},"nbformat":4,"nbformat_minor":5}'
    )
    original = parse_ipynb_source(source)
    candidate = source.replace(b'"\\u0061"', b'"a"')

    with pytest.raises(RoundTripVerificationError):
        verify_ipynb_candidate(
            original,
            candidate,
            encoding=original.representation.encoding,
            requested={},
        )


def test_candidate_parse_failure_is_verification_failure() -> None:
    original = parse_ipynb_source(_source())
    with pytest.raises(RoundTripVerificationError):
        verify_ipynb_candidate(
            original,
            b"not-json",
            encoding=original.representation.encoding,
            requested={},
        )
