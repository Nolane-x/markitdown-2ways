from __future__ import annotations

import pytest

from markitdown.twoways.formats.csv.lexical import (
    CsvDialectError,
    CsvLexicalError,
    resolve_csv_text,
    scan_csv_text,
)


def test_scanner_records_exact_field_lexemes_and_row_terminators() -> None:
    text = 'a,"b,c","d""e"\r\nx,,z\n'

    parsed = scan_csv_text(text, delimiter=",")

    assert parsed.delimiter == ","
    assert parsed.dialect_proven is True
    assert parsed.reason_code is None
    assert [row.terminator for row in parsed.rows] == ["\r\n", "\n"]

    first = parsed.rows[0].fields
    assert [(field.row, field.column, field.value) for field in first] == [
        (0, 0, "a"),
        (0, 1, "b,c"),
        (0, 2, 'd"e'),
    ]
    assert [(field.start, field.end, field.raw, field.quoted) for field in first] == [
        (0, 1, "a", False),
        (2, 7, '"b,c"', True),
        (8, 14, '"d""e"', True),
    ]

    second = parsed.rows[1].fields
    assert [(field.value, field.start, field.end, field.raw) for field in second] == [
        ("x", 16, 17, "x"),
        ("", 18, 18, ""),
        ("z", 19, 20, "z"),
    ]


def test_scanner_preserves_blank_records_and_ragged_rows() -> None:
    parsed = scan_csv_text("a,b\r\n\r\nc\n", delimiter=",")

    assert [len(row.fields) for row in parsed.rows] == [2, 0, 1]
    assert [row.terminator for row in parsed.rows] == ["\r\n", "\r\n", "\n"]
    assert [field.value for field in parsed.rows[2].fields] == ["c"]


def test_scanner_supports_existing_multiline_quoted_fields() -> None:
    text = '"alpha\nbeta",tail\r\n'

    parsed = scan_csv_text(text, delimiter=",")
    field = parsed.rows[0].fields[0]

    assert field.value == "alpha\nbeta"
    assert field.raw == '"alpha\nbeta"'
    assert field.quoted is True
    assert field.multiline is True
    assert parsed.rows[0].terminator == "\r\n"


@pytest.mark.parametrize(
    "text",
    [
        '"unterminated',
        'abc"def,tail\n',
        '"abc"junk,tail\n',
    ],
)
def test_scanner_rejects_ambiguous_or_malformed_quote_structure(text: str) -> None:
    with pytest.raises(CsvLexicalError):
        scan_csv_text(text, delimiter=",")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a,b\nc,d\n", ","),
        ("a;b\nc;d\n", ";"),
        ("a\tb\nc\td\n", "\t"),
        ("a|b\nc|d\n", "|"),
    ],
)
def test_resolver_proves_unique_common_delimiters(text: str, expected: str) -> None:
    parsed = resolve_csv_text(text)

    assert parsed.delimiter == expected
    assert parsed.dialect_proven is True
    assert parsed.reason_code is None
    assert [[field.value for field in row.fields] for row in parsed.rows] == [
        ["a", "b"],
        ["c", "d"],
    ]


def test_explicit_delimiter_is_authoritative_for_single_column_csv() -> None:
    parsed = resolve_csv_text("alpha\nbeta\n", delimiter=";")

    assert parsed.delimiter == ";"
    assert parsed.dialect_proven is True
    assert parsed.reason_code is None
    assert [[field.value for field in row.fields] for row in parsed.rows] == [
        ["alpha"],
        ["beta"],
    ]


def test_unproven_single_column_csv_is_readable_but_not_dialect_proven() -> None:
    parsed = resolve_csv_text("alpha\nbeta\n")

    assert parsed.delimiter == ","
    assert parsed.dialect_proven is False
    assert parsed.reason_code == "csv.dialect.unproven_single_column"
    assert [[field.value for field in row.fields] for row in parsed.rows] == [
        ["alpha"],
        ["beta"],
    ]


def test_materially_ambiguous_delimiters_fail_closed() -> None:
    with pytest.raises(CsvDialectError, match="ambiguous"):
        resolve_csv_text("a,b;c\n1,2;3\n")


def test_delimiters_inside_quotes_do_not_count_as_dialect_evidence() -> None:
    parsed = resolve_csv_text('"a,b";c\n"d,e";f\n')

    assert parsed.delimiter == ";"
    assert parsed.dialect_proven is True
    assert [[field.value for field in row.fields] for row in parsed.rows] == [
        ["a,b", "c"],
        ["d,e", "f"],
    ]


def test_invalid_explicit_delimiter_fails_closed() -> None:
    for delimiter in ("", "::", "\n", "\r"):
        with pytest.raises(ValueError):
            resolve_csv_text("a,b\n", delimiter=delimiter)
