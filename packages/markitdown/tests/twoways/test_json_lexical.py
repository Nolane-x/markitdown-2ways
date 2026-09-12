from __future__ import annotations

from decimal import Decimal

import pytest

from markitdown.twoways.formats.json.lexical import JsonLexicalError, scan_json_text


def _by_pointer(document):
    return {node.pointer: node for node in document.nodes}


def test_scans_nested_json_with_exact_spans_and_pointers() -> None:
    text = '{"name":"Ada","items":[1,true,null,{"x/y~z":"v"}]}'

    document = scan_json_text(text)
    nodes = _by_pointer(document)

    assert document.root_pointer == ""
    assert nodes[""].kind == "object"
    assert nodes[""].raw == text
    assert nodes[""].start == 0
    assert nodes[""].end == len(text)
    assert nodes[""].children == ("/name", "/items")
    assert nodes["/name"].kind == "string"
    assert nodes["/name"].value == "Ada"
    assert nodes["/name"].raw == '"Ada"'
    assert nodes["/items"].kind == "array"
    assert nodes["/items"].children == ("/items/0", "/items/1", "/items/2", "/items/3")
    assert nodes["/items/0"].kind == "number"
    assert nodes["/items/0"].raw == "1"
    assert nodes["/items/1"].value is True
    assert nodes["/items/2"].value is None
    assert nodes["/items/3/x~1y~0z"].value == "v"
    assert nodes["/items/3/x~1y~0z"].parent_pointer == "/items/3"
    assert all(len(node.raw_digest) == 64 for node in document.nodes)


def test_string_escape_semantics_are_strict_and_span_is_lexical() -> None:
    text = '{"s":"line\\n\\u0041\\\\\\\""}'
    document = scan_json_text(text)
    node = _by_pointer(document)["/s"]

    assert node.value == 'line\nA\\"'
    assert text[node.start : node.end] == node.raw
    assert node.raw.startswith('"') and node.raw.endswith('"')


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("0", Decimal("0")),
        ("-0", Decimal("-0")),
        ("123", Decimal("123")),
        ("-12.50", Decimal("-12.50")),
        ("1e2", Decimal("1e2")),
        ("1E-2", Decimal("1E-2")),
    ],
)
def test_json_number_grammar_and_decimal_semantics(token: str, expected: Decimal) -> None:
    document = scan_json_text(token)
    node = document.nodes[0]

    assert node.kind == "number"
    assert node.raw == token
    assert node.number_value == expected


@pytest.mark.parametrize(
    "text",
    [
        "01",
        "1.",
        ".1",
        "+1",
        "1e",
        "1e+",
        "NaN",
        "Infinity",
        "-Infinity",
        '{"a":1,}',
        '[1,]',
        '{"a":1 // comment\n}',
        '{"a":1} trailing',
        '"unterminated',
        '"control\x01"',
    ],
)
def test_non_strict_json_fails_closed(text: str) -> None:
    with pytest.raises(JsonLexicalError):
        scan_json_text(text)


def test_duplicate_decoded_object_key_fails_closed() -> None:
    with pytest.raises(JsonLexicalError, match="duplicate"):
        scan_json_text('{"a":1,"\\u0061":2}')


def test_root_scalar_and_whitespace_are_supported_without_absorbing_whitespace() -> None:
    text = " \r\n  true\t "
    document = scan_json_text(text)
    node = document.nodes[0]

    assert node.pointer == ""
    assert node.kind == "boolean"
    assert node.value is True
    assert node.raw == "true"
    assert text[node.start : node.end] == "true"
