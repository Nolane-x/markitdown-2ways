from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CsvFieldLexeme:
    row: int
    column: int
    value: str
    start: int
    end: int
    raw: str
    quoted: bool
    multiline: bool
    raw_digest: str

    def __post_init__(self) -> None:
        if self.row < 0 or self.column < 0:
            raise ValueError("CSV field coordinates must be non-negative")
        if self.start < 0 or self.end < self.start:
            raise ValueError("CSV field span is invalid")
        if not isinstance(self.value, str) or not isinstance(self.raw, str):
            raise TypeError("CSV field value/raw must be strings")
        if not self.raw_digest:
            raise ValueError("CSV field raw digest must be non-empty")


@dataclass(frozen=True)
class CsvRowLexeme:
    index: int
    fields: tuple[CsvFieldLexeme, ...]
    terminator: str

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("CSV row index must be non-negative")
        if self.terminator not in {"", "\n", "\r", "\r\n"}:
            raise ValueError("CSV row terminator is invalid")
        object.__setattr__(self, "fields", tuple(self.fields))


@dataclass(frozen=True)
class CsvLexicalDocument:
    delimiter: str
    rows: tuple[CsvRowLexeme, ...]
    dialect_proven: bool = True
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if len(self.delimiter) != 1 or self.delimiter in {"\r", "\n", '"'}:
            raise ValueError("CSV delimiter must be one non-newline, non-quote character")
        object.__setattr__(self, "rows", tuple(self.rows))
        if self.dialect_proven and self.reason_code is not None:
            raise ValueError("proven CSV dialect cannot carry a read-only reason")
        if not self.dialect_proven and not self.reason_code:
            raise ValueError("unproven CSV dialect requires a reason code")
