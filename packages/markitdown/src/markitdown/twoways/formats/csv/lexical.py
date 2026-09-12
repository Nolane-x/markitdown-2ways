from __future__ import annotations

import csv
import io
from dataclasses import replace
from hashlib import sha256

from .model import CsvFieldLexeme, CsvLexicalDocument, CsvRowLexeme


_CANDIDATE_DELIMITERS = (",", ";", "\t", "|")


class CsvLexicalError(ValueError):
    """Raised when source CSV lexical structure is malformed."""


class CsvDialectError(CsvLexicalError):
    """Raised when H2 cannot prove one authoritative delimiter."""


def _validate_delimiter(delimiter: str) -> None:
    if (
        not isinstance(delimiter, str)
        or len(delimiter) != 1
        or delimiter in {"\r", "\n", '"'}
    ):
        raise ValueError("CSV delimiter must be one non-newline, non-quote character")


def _row_terminator(text: str, position: int) -> str | None:
    if position >= len(text):
        return None
    if text.startswith("\r\n", position):
        return "\r\n"
    if text[position] == "\r":
        return "\r"
    if text[position] == "\n":
        return "\n"
    return None


def _strict_reader_rows(text: str, delimiter: str) -> list[list[str]]:
    try:
        return list(
            csv.reader(
                io.StringIO(text, newline=""),
                delimiter=delimiter,
                quotechar='"',
                doublequote=True,
                escapechar=None,
                skipinitialspace=False,
                strict=True,
            )
        )
    except csv.Error as exc:
        raise CsvLexicalError(f"CSV semantic parse failed: {exc}") from exc


def _validate_semantic_parity(
    text: str,
    delimiter: str,
    rows: tuple[CsvRowLexeme, ...],
) -> None:
    expected = [[field.value for field in row.fields] for row in rows]
    observed = _strict_reader_rows(text, delimiter)
    if observed != expected:
        raise CsvLexicalError("CSV lexical spans disagree with strict csv.reader semantics")


def scan_csv_text(text: str, *, delimiter: str) -> CsvLexicalDocument:
    if not isinstance(text, str):
        raise TypeError("CSV source text must be a string")
    _validate_delimiter(delimiter)

    rows: list[CsvRowLexeme] = []
    position = 0
    row_index = 0
    length = len(text)

    while position < length:
        immediate_terminator = _row_terminator(text, position)
        if immediate_terminator is not None:
            rows.append(
                CsvRowLexeme(
                    index=row_index,
                    fields=(),
                    terminator=immediate_terminator,
                )
            )
            position += len(immediate_terminator)
            row_index += 1
            continue

        fields: list[CsvFieldLexeme] = []
        column = 0
        while True:
            start = position
            quoted = position < length and text[position] == '"'
            multiline = False
            value_parts: list[str] = []

            if quoted:
                position += 1
                while True:
                    if position >= length:
                        raise CsvLexicalError("CSV quoted field is unterminated")
                    character = text[position]
                    if character == '"':
                        if position + 1 < length and text[position + 1] == '"':
                            value_parts.append('"')
                            position += 2
                            continue
                        position += 1
                        break
                    if character in {"\r", "\n"}:
                        multiline = True
                    value_parts.append(character)
                    position += 1

                end = position
                next_terminator = _row_terminator(text, position)
                if (
                    position < length
                    and text[position] != delimiter
                    and next_terminator is None
                ):
                    raise CsvLexicalError(
                        "CSV quoted field has content after its closing quote"
                    )
            else:
                while position < length:
                    character = text[position]
                    if character == delimiter or _row_terminator(text, position):
                        break
                    if character == '"':
                        raise CsvLexicalError(
                            "CSV unquoted field contains an ambiguous quote"
                        )
                    value_parts.append(character)
                    position += 1
                end = position

            raw = text[start:end]
            fields.append(
                CsvFieldLexeme(
                    row=row_index,
                    column=column,
                    value="".join(value_parts),
                    start=start,
                    end=end,
                    raw=raw,
                    quoted=quoted,
                    multiline=multiline,
                    raw_digest=sha256(raw.encode("utf-8")).hexdigest(),
                )
            )

            if position >= length:
                rows.append(
                    CsvRowLexeme(index=row_index, fields=tuple(fields), terminator="")
                )
                position = length
                break

            if text[position] == delimiter:
                position += 1
                column += 1
                continue

            terminator = _row_terminator(text, position)
            if terminator is None:
                raise CsvLexicalError("CSV field boundary is malformed")
            rows.append(
                CsvRowLexeme(
                    index=row_index,
                    fields=tuple(fields),
                    terminator=terminator,
                )
            )
            position += len(terminator)
            row_index += 1
            break

    parsed = CsvLexicalDocument(delimiter=delimiter, rows=tuple(rows))
    _validate_semantic_parity(text, delimiter, parsed.rows)
    return parsed


def _delimiter_evidence(parsed: CsvLexicalDocument) -> int:
    return sum(max(0, len(row.fields) - 1) for row in parsed.rows)


def resolve_csv_text(
    text: str,
    *,
    delimiter: str | None = None,
) -> CsvLexicalDocument:
    if delimiter is not None:
        _validate_delimiter(delimiter)
        return scan_csv_text(text, delimiter=delimiter)

    candidates: list[CsvLexicalDocument] = []
    for candidate in _CANDIDATE_DELIMITERS:
        try:
            parsed = scan_csv_text(text, delimiter=candidate)
        except CsvLexicalError:
            continue
        if _delimiter_evidence(parsed) > 0:
            candidates.append(parsed)

    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        raise CsvDialectError("CSV delimiter is ambiguous across supported candidates")

    parsed = scan_csv_text(text, delimiter=",")
    return replace(
        parsed,
        dialect_proven=False,
        reason_code="csv.dialect.unproven_single_column",
    )
