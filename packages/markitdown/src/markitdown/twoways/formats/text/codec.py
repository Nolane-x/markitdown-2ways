from __future__ import annotations

import codecs
import re

from charset_normalizer import from_bytes

from .model import TextRepresentation


_BOM_DEFINITIONS: tuple[tuple[bytes, str, str], ...] = (
    (codecs.BOM_UTF32_LE, "utf-32-le", "utf-32-le"),
    (codecs.BOM_UTF32_BE, "utf-32-be", "utf-32-be"),
    (codecs.BOM_UTF8, "utf-8", "utf-8"),
    (codecs.BOM_UTF16_LE, "utf-16-le", "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be", "utf-16-be"),
)
_BOM_BYTES = {name: value for value, name, _encoding in _BOM_DEFINITIONS}
_BOM_BYTES["none"] = b""
_LINE_BREAK_RE = re.compile(r"\r\n|\r|\n")


def _canonical_encoding(value: str) -> str:
    return codecs.lookup(value).name


def _detect_bom(source: bytes) -> tuple[str, str | None, bytes]:
    for marker, name, encoding in _BOM_DEFINITIONS:
        if source.startswith(marker):
            return name, encoding, source[len(marker) :]
    return "none", None, source


def _bom_compatible_encoding(explicit: str, detected: str) -> bool:
    if explicit == detected:
        return True
    if detected == "utf-8" and explicit == "utf-8-sig":
        return True
    if detected.startswith("utf-16-") and explicit == "utf-16":
        return True
    if detected.startswith("utf-32-") and explicit == "utf-32":
        return True
    return False


def _classify_newlines(text: str) -> str:
    tokens = set(_LINE_BREAK_RE.findall(text))
    if not tokens:
        return "none"
    if len(tokens) > 1:
        return "mixed"
    token = next(iter(tokens))
    return {"\n": "lf", "\r\n": "crlf", "\r": "cr"}[token]


def decode_text_source(
    source: bytes,
    *,
    encoding: str | None = None,
) -> tuple[str, TextRepresentation]:
    if not isinstance(source, bytes):
        raise TypeError("text source must be bytes")

    bom, bom_encoding, payload = _detect_bom(source)
    explicit = _canonical_encoding(encoding) if encoding is not None else None

    if bom_encoding is not None:
        if explicit is not None and not _bom_compatible_encoding(
            explicit, bom_encoding
        ):
            raise ValueError("explicit encoding does not match detected Unicode BOM")
        resolved = bom_encoding
        text = payload.decode(resolved, errors="strict")
        roundtrip = text.encode(resolved, errors="strict") == payload
    elif explicit is not None:
        resolved = explicit
        text = payload.decode(resolved, errors="strict")
        roundtrip = text.encode(resolved, errors="strict") == payload
    else:
        try:
            resolved = "utf-8"
            text = payload.decode(resolved, errors="strict")
            roundtrip = text.encode(resolved, errors="strict") == payload
        except UnicodeDecodeError:
            best = from_bytes(payload).best()
            if best is None or not best.encoding:
                raise ValueError("text source encoding could not be determined")
            resolved = _canonical_encoding(best.encoding)
            text = str(best)
            try:
                roundtrip = text.encode(resolved, errors="strict") == payload
            except UnicodeEncodeError:
                roundtrip = False

    representation = TextRepresentation(
        encoding=resolved,
        bom=bom,
        newline=_classify_newlines(text),
        byte_roundtrip=roundtrip,
    )
    return text, representation


def normalize_newlines(text: str, newline: str) -> str:
    if not isinstance(text, str):
        raise TypeError("replacement text must be a string")
    if newline == "mixed":
        raise ValueError("mixed newline sources cannot be normalized safely")
    if newline == "none":
        if _LINE_BREAK_RE.search(text):
            raise ValueError("source has no newline convention")
        return text

    separators = {"lf": "\n", "crlf": "\r\n", "cr": "\r"}
    if newline not in separators:
        raise ValueError("text newline convention is unsupported")
    return _LINE_BREAK_RE.sub(separators[newline], text)


def encode_text_source(text: str, representation: TextRepresentation) -> bytes:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if not representation.byte_roundtrip:
        raise ValueError("source encoding is not byte-roundtrippable")
    payload = text.encode(representation.encoding, errors="strict")
    return _BOM_BYTES[representation.bom] + payload
