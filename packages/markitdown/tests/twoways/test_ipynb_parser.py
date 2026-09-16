from __future__ import annotations

import pytest

from markitdown.twoways.formats.ipynb.parser import IpynbParseError, parse_ipynb_source


def test_parses_nbformat4_source_evidence_without_normalizing_json() -> None:
    source = (
        b'{"cells":[{"cell_type":"code","execution_count":7,'
        b'"id":"cell-a","metadata":{"tag":"x"},'
        b'"outputs":[{"output_type":"stream","text":["ok\\n"]}],'
        b'"source":["print(1)\\n","print(2)"]}],'
        b'"metadata":{"title":"N"},"nbformat":4,"nbformat_minor":5}'
    )

    parsed = parse_ipynb_source(source)

    assert parsed.nbformat == 4
    assert parsed.nbformat_minor == 5
    assert parsed.writable_version is True
    assert parsed.read_only_reason is None
    assert len(parsed.cells) == 1
    assert parsed.top_level_non_cells_digest
    assert parsed.representation.byte_roundtrip is True

    cell = parsed.cells[0]
    assert cell.index == 0
    assert cell.cell_type == "code"
    assert cell.cell_id == "cell-a"
    assert cell.non_source_digest
    assert cell.source_pointer == "/cells/0/source"
    assert cell.source_representation == "string-array"
    assert cell.source_segment_pointers == (
        "/cells/0/source/0",
        "/cells/0/source/1",
    )
    assert len(cell.source_segment_raw_digests) == 2
    assert cell.logical_source == "print(1)\nprint(2)"
    assert (
        source.decode("utf-8")[cell.source_start : cell.source_end]
        == '["print(1)\\n","print(2)"]'
    )


def test_parses_string_source_and_raw_cell() -> None:
    source = (
        b'{"cells":['
        b'{"cell_type":"markdown","metadata":{},"source":"# Title\\n"},'
        b'{"cell_type":"raw","metadata":{},"source":["literal\\n"]}'
        b'],"metadata":{},"nbformat":4,"nbformat_minor":5}'
    )

    parsed = parse_ipynb_source(source)

    markdown, raw = parsed.cells
    assert markdown.source_representation == "string"
    assert markdown.source_segment_pointers == ("/cells/0/source",)
    assert markdown.logical_source == "# Title\n"
    assert raw.source_representation == "string-array"
    assert raw.source_segment_pointers == ("/cells/1/source/0",)
    assert raw.logical_source == "literal\n"


def test_parser_records_non_source_evidence_for_outputs_metadata_and_attachments() -> (
    None
):
    source = (
        b'{"cells":['
        b'{"cell_type":"markdown","attachments":{"a.txt":{"text/plain":"YQ=="}},'
        b'"metadata":{"tags":["keep"]},"source":["hello"]},'
        b'{"cell_type":"code","execution_count":11,"metadata":{"collapsed":false},'
        b'"outputs":[{"name":"stdout","output_type":"stream","text":["x\\n"]}],'
        b'"source":"print(1)"}'
        b'],"metadata":{"kernelspec":{"name":"python3"}},"nbformat":4,"nbformat_minor":5}'
    )

    parsed = parse_ipynb_source(source)

    assert parsed.top_level_non_cells_digest
    assert parsed.cells[0].non_source_digest
    assert parsed.cells[1].non_source_digest
    assert parsed.cells[0].non_source_digest != parsed.cells[1].non_source_digest


@pytest.mark.parametrize(
    "source",
    [
        b"[]",
        b'{"cells":[],"metadata":{},"nbformat":true,"nbformat_minor":5}',
        b'{"cells":[],"metadata":{},"nbformat":4,"nbformat_minor":false}',
        b'{"metadata":{},"nbformat":4,"nbformat_minor":5}',
        b'{"cells":{},"metadata":{},"nbformat":4,"nbformat_minor":5}',
        b'{"cells":[1],"metadata":{},"nbformat":4,"nbformat_minor":5}',
        b'{"cells":[{"cell_type":1,"source":"x"}],"metadata":{},"nbformat":4,"nbformat_minor":5}',
        b'{"cells":[{"cell_type":"code","source":1}],"metadata":{},"nbformat":4,"nbformat_minor":5}',
        b'{"cells":[{"cell_type":"code","source":["x",1]}],"metadata":{},"nbformat":4,"nbformat_minor":5}',
    ],
)
def test_malformed_nbformat4_shapes_fail_closed(source: bytes) -> None:
    with pytest.raises(IpynbParseError):
        parse_ipynb_source(source)


def test_duplicate_json_keys_fail_through_strict_json_ownership() -> None:
    source = b'{"cells":[],"metadata":{},"nbformat":4,"nbformat":4,"nbformat_minor":5}'

    with pytest.raises((IpynbParseError, ValueError)):
        parse_ipynb_source(source)


def test_unsupported_nbformat_is_deterministically_read_only() -> None:
    parsed = parse_ipynb_source(
        b'{"cells":[],"metadata":{},"nbformat":3,"nbformat_minor":0}'
    )

    assert parsed.nbformat == 3
    assert parsed.writable_version is False
    assert parsed.read_only_reason == "ipynb.nbformat.unsupported_version"
    assert parsed.cells == ()
