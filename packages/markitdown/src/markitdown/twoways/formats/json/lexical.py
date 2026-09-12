from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
import json
import re
from typing import Any

from .model import JsonLexicalDocument, JsonLexicalNode


_JSON_WHITESPACE = frozenset({" ", "\t", "\r", "\n"})
_NUMBER_RE = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
_HEX = frozenset("0123456789abcdefABCDEF")
_SIMPLE_ESCAPES = frozenset('"\\/bfnrt')


class JsonLexicalError(ValueError):
    """Raised when strict JSON lexical ownership cannot be proven."""


def _digest(raw: str) -> str:
    return sha256(raw.encode("utf-8")).hexdigest()


def _escape_pointer_segment(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _child_pointer(parent: str, segment: str) -> str:
    return f"{parent}/{_escape_pointer_segment(segment)}"


def _reject_constant(value: str) -> Any:
    raise JsonLexicalError(f"non-standard JSON constant is unsupported: {value}")


def _pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise JsonLexicalError(f"duplicate JSON object key is ambiguous: {key!r}")
        result[key] = value
    return result


def _strict_stdlib_check(text: str) -> None:
    try:
        json.loads(
            text,
            parse_int=Decimal,
            parse_float=Decimal,
            parse_constant=_reject_constant,
            object_pairs_hook=_pairs_hook,
        )
    except JsonLexicalError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise JsonLexicalError(f"strict JSON decoder rejected source: {exc}") from exc


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.length = len(text)
        self.position = 0

    def parse(self) -> JsonLexicalDocument:
        self._skip_whitespace()
        if self.position >= self.length:
            raise JsonLexicalError("JSON source contains no root value")
        root_nodes = self._parse_value("", None)
        self._skip_whitespace()
        if self.position != self.length:
            raise JsonLexicalError("JSON source contains trailing data after root value")
        _strict_stdlib_check(self.text)
        return JsonLexicalDocument(root_pointer="", nodes=tuple(root_nodes))

    def _skip_whitespace(self) -> None:
        while self.position < self.length and self.text[self.position] in _JSON_WHITESPACE:
            self.position += 1

    def _node(
        self,
        *,
        pointer: str,
        kind: str,
        start: int,
        end: int,
        parent_pointer: str | None,
        children: tuple[str, ...] = (),
        value: Any = None,
        number_value: Decimal | None = None,
    ) -> JsonLexicalNode:
        raw = self.text[start:end]
        return JsonLexicalNode(
            pointer=pointer,
            kind=kind,
            start=start,
            end=end,
            raw=raw,
            raw_digest=_digest(raw),
            parent_pointer=parent_pointer,
            children=children,
            value=value,
            number_value=number_value,
        )

    def _parse_value(
        self, pointer: str, parent_pointer: str | None
    ) -> list[JsonLexicalNode]:
        if self.position >= self.length:
            raise JsonLexicalError("JSON value is missing")
        character = self.text[self.position]
        if character == "{":
            return self._parse_object(pointer, parent_pointer)
        if character == "[":
            return self._parse_array(pointer, parent_pointer)
        if character == '"':
            start = self.position
            value, end = self._parse_string_token()
            return [
                self._node(
                    pointer=pointer,
                    kind="string",
                    start=start,
                    end=end,
                    parent_pointer=parent_pointer,
                    value=value,
                )
            ]
        if character == "t" and self.text.startswith("true", self.position):
            return [self._parse_literal(pointer, parent_pointer, "true", "boolean", True)]
        if character == "f" and self.text.startswith("false", self.position):
            return [
                self._parse_literal(pointer, parent_pointer, "false", "boolean", False)
            ]
        if character == "n" and self.text.startswith("null", self.position):
            return [self._parse_literal(pointer, parent_pointer, "null", "null", None)]
        if character == "-" or character.isdigit():
            return [self._parse_number(pointer, parent_pointer)]
        raise JsonLexicalError(
            f"unexpected JSON token at character {self.position}: {character!r}"
        )

    def _parse_literal(
        self,
        pointer: str,
        parent_pointer: str | None,
        token: str,
        kind: str,
        value: Any,
    ) -> JsonLexicalNode:
        start = self.position
        self.position += len(token)
        return self._node(
            pointer=pointer,
            kind=kind,
            start=start,
            end=self.position,
            parent_pointer=parent_pointer,
            value=value,
        )

    def _parse_number(
        self, pointer: str, parent_pointer: str | None
    ) -> JsonLexicalNode:
        start = self.position
        match = _NUMBER_RE.match(self.text, self.position)
        if match is None:
            raise JsonLexicalError(f"invalid JSON number at character {self.position}")
        self.position = match.end()
        raw = self.text[start : self.position]
        try:
            number_value = Decimal(raw)
        except Exception as exc:  # Decimal failure is a lexical failure at this boundary.
            raise JsonLexicalError(f"invalid JSON number token: {raw!r}") from exc
        return self._node(
            pointer=pointer,
            kind="number",
            start=start,
            end=self.position,
            parent_pointer=parent_pointer,
            number_value=number_value,
        )

    def _parse_string_token(self) -> tuple[str, int]:
        start = self.position
        if self.text[self.position] != '"':
            raise JsonLexicalError("JSON string must start with a double quote")
        self.position += 1
        while self.position < self.length:
            character = self.text[self.position]
            if character == '"':
                self.position += 1
                raw = self.text[start : self.position]
                try:
                    value = json.loads(raw)
                except (json.JSONDecodeError, ValueError) as exc:
                    raise JsonLexicalError(f"invalid JSON string token: {exc}") from exc
                if not isinstance(value, str):
                    raise JsonLexicalError("JSON string token did not decode to a string")
                return value, self.position
            if ord(character) < 0x20:
                raise JsonLexicalError("JSON string contains an unescaped control character")
            if character == "\\":
                self.position += 1
                if self.position >= self.length:
                    raise JsonLexicalError("JSON string ends in an incomplete escape")
                escape = self.text[self.position]
                if escape == "u":
                    if self.position + 4 >= self.length:
                        raise JsonLexicalError("JSON unicode escape is incomplete")
                    digits = self.text[self.position + 1 : self.position + 5]
                    if len(digits) != 4 or any(digit not in _HEX for digit in digits):
                        raise JsonLexicalError("JSON unicode escape contains non-hex digits")
                    self.position += 5
                    continue
                if escape not in _SIMPLE_ESCAPES:
                    raise JsonLexicalError(f"unsupported JSON escape: \\{escape}")
                self.position += 1
                continue
            self.position += 1
        raise JsonLexicalError("JSON string is unterminated")

    def _parse_object(
        self, pointer: str, parent_pointer: str | None
    ) -> list[JsonLexicalNode]:
        start = self.position
        self.position += 1
        self._skip_whitespace()
        child_nodes: list[JsonLexicalNode] = []
        child_pointers: list[str] = []
        seen_keys: set[str] = set()

        if self.position < self.length and self.text[self.position] == "}":
            self.position += 1
            return [
                self._node(
                    pointer=pointer,
                    kind="object",
                    start=start,
                    end=self.position,
                    parent_pointer=parent_pointer,
                    children=(),
                    value=0,
                )
            ]

        while True:
            if self.position >= self.length or self.text[self.position] != '"':
                raise JsonLexicalError("JSON object member key must be a string")
            key, _key_end = self._parse_string_token()
            if key in seen_keys:
                raise JsonLexicalError(f"duplicate JSON object key is ambiguous: {key!r}")
            seen_keys.add(key)
            self._skip_whitespace()
            if self.position >= self.length or self.text[self.position] != ":":
                raise JsonLexicalError("JSON object member is missing ':'")
            self.position += 1
            self._skip_whitespace()
            child_pointer = _child_pointer(pointer, key)
            parsed_child = self._parse_value(child_pointer, pointer)
            child_nodes.extend(parsed_child)
            child_pointers.append(child_pointer)
            self._skip_whitespace()
            if self.position >= self.length:
                raise JsonLexicalError("JSON object is unterminated")
            if self.text[self.position] == "}":
                self.position += 1
                break
            if self.text[self.position] != ",":
                raise JsonLexicalError("JSON object members must be separated by ','")
            self.position += 1
            self._skip_whitespace()

        root = self._node(
            pointer=pointer,
            kind="object",
            start=start,
            end=self.position,
            parent_pointer=parent_pointer,
            children=tuple(child_pointers),
            value=len(child_pointers),
        )
        return [root, *child_nodes]

    def _parse_array(
        self, pointer: str, parent_pointer: str | None
    ) -> list[JsonLexicalNode]:
        start = self.position
        self.position += 1
        self._skip_whitespace()
        child_nodes: list[JsonLexicalNode] = []
        child_pointers: list[str] = []

        if self.position < self.length and self.text[self.position] == "]":
            self.position += 1
            return [
                self._node(
                    pointer=pointer,
                    kind="array",
                    start=start,
                    end=self.position,
                    parent_pointer=parent_pointer,
                    children=(),
                    value=0,
                )
            ]

        index = 0
        while True:
            child_pointer = _child_pointer(pointer, str(index))
            parsed_child = self._parse_value(child_pointer, pointer)
            child_nodes.extend(parsed_child)
            child_pointers.append(child_pointer)
            index += 1
            self._skip_whitespace()
            if self.position >= self.length:
                raise JsonLexicalError("JSON array is unterminated")
            if self.text[self.position] == "]":
                self.position += 1
                break
            if self.text[self.position] != ",":
                raise JsonLexicalError("JSON array values must be separated by ','")
            self.position += 1
            self._skip_whitespace()

        root = self._node(
            pointer=pointer,
            kind="array",
            start=start,
            end=self.position,
            parent_pointer=parent_pointer,
            children=tuple(child_pointers),
            value=len(child_pointers),
        )
        return [root, *child_nodes]


def scan_json_text(text: str) -> JsonLexicalDocument:
    if not isinstance(text, str):
        raise TypeError("JSON source text must be a string")
    return _Parser(text).parse()
