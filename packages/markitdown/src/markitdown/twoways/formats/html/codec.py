from __future__ import annotations

import codecs
import re
from hashlib import sha256

from ..text.codec import decode_text_source
from ..text.model import TextRepresentation
from .model import HtmlEncodingDeclaration, HtmlLexicalError


_META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_CHARSET_ATTR_RE = re.compile(
    r"\bcharset\s*=\s*(?:\"(?P<dq>[^\"]+)\"|'(?P<sq>[^']+)'|(?P<bare>[^\s/>]+))",
    re.IGNORECASE,
)
_HTTP_EQUIV_RE = re.compile(
    r"\bhttp-equiv\s*=\s*(?:\"content-type\"|'content-type'|content-type)(?=\s|/?>)",
    re.IGNORECASE,
)
_CONTENT_RE = re.compile(
    r"\bcontent\s*=\s*(?:\"(?P<dq>[^\"]*)\"|'(?P<sq>[^']*)'|(?P<bare>[^\s>]+))",
    re.IGNORECASE,
)
_CONTENT_CHARSET_RE = re.compile(r"\bcharset\s*=\s*([^\s;\"']+)", re.IGNORECASE)
_BYTES_META_CHARSET_RE = re.compile(
    rb"<meta\b[^>]*\bcharset\s*=\s*(?:\"([^\"]+)\"|'([^']+)'|([^\s/>]+))[^>]*>",
    re.IGNORECASE,
)
_BYTES_HTTP_EQUIV_RE = re.compile(
    rb"<meta\b(?=[^>]*\bhttp-equiv\s*=\s*(?:\"content-type\"|'content-type'|content-type)(?=\s|/?>))"
    rb"(?=[^>]*\bcontent\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+)))[^>]*>",
    re.IGNORECASE,
)
_PREFIX_LIMIT = 4096


def _canonical_encoding(value: str) -> str:
    try:
        return codecs.lookup(value.strip()).name
    except (LookupError, AttributeError) as exc:
        raise HtmlLexicalError(f"HTML encoding is unsupported: {value!r}") from exc


def _extract_group(
    match: re.Match[str] | re.Match[bytes], names: tuple[str, ...] = ()
) -> str:
    if names:
        for name in names:
            value = match.groupdict().get(name)
            if value:
                return value.decode("ascii") if isinstance(value, bytes) else value
    for value in match.groups():
        if value:
            return value.decode("ascii") if isinstance(value, bytes) else value
    raise HtmlLexicalError("HTML encoding declaration is empty")


def _raw_prefix_encoding_hints(source: bytes) -> tuple[str, ...]:
    prefix = source[:_PREFIX_LIMIT]
    hints: list[str] = []
    for match in _BYTES_META_CHARSET_RE.finditer(prefix):
        try:
            hints.append(_canonical_encoding(_extract_group(match)))
        except UnicodeDecodeError as exc:
            raise HtmlLexicalError(
                "HTML meta encoding must be ASCII-compatible"
            ) from exc
    for match in _BYTES_HTTP_EQUIV_RE.finditer(prefix):
        try:
            content = _extract_group(match)
        except UnicodeDecodeError as exc:
            raise HtmlLexicalError(
                "HTML content-type declaration must be ASCII-compatible"
            ) from exc
        charset_match = _CONTENT_CHARSET_RE.search(content)
        if charset_match:
            hints.append(_canonical_encoding(charset_match.group(1)))
    return tuple(hints)


def _text_encoding_declarations(text: str) -> tuple[HtmlEncodingDeclaration, ...]:
    declarations: list[HtmlEncodingDeclaration] = []
    for tag_match in _META_TAG_RE.finditer(text[:_PREFIX_LIMIT]):
        raw = tag_match.group(0)
        encoding: str | None = None
        charset_match = _CHARSET_ATTR_RE.search(raw)
        if charset_match:
            encoding = _canonical_encoding(
                charset_match.group("dq")
                or charset_match.group("sq")
                or charset_match.group("bare")
                or ""
            )
        elif _HTTP_EQUIV_RE.search(raw):
            content_match = _CONTENT_RE.search(raw)
            if content_match:
                content = (
                    content_match.group("dq")
                    or content_match.group("sq")
                    or content_match.group("bare")
                    or ""
                )
                value_match = _CONTENT_CHARSET_RE.search(content)
                if value_match:
                    encoding = _canonical_encoding(value_match.group(1))
        if encoding is None:
            continue
        declarations.append(
            HtmlEncodingDeclaration(
                start=tag_match.start(),
                end=tag_match.end(),
                raw=raw,
                raw_digest=sha256(raw.encode("utf-8")).hexdigest(),
                encoding=encoding,
            )
        )
    return tuple(declarations)


def _one_declared_encoding(values: tuple[str, ...]) -> str | None:
    if not values:
        return None
    unique = set(values)
    if len(unique) != 1:
        raise HtmlLexicalError("HTML source contains conflicting encoding declarations")
    return values[0]


def decode_html_source(
    source: bytes,
    *,
    encoding: str | None = None,
) -> tuple[str, TextRepresentation, tuple[HtmlEncodingDeclaration, ...]]:
    if not isinstance(source, bytes):
        raise TypeError("HTML source must be bytes")

    explicit = _canonical_encoding(encoding) if encoding is not None else None
    raw_declared = _one_declared_encoding(_raw_prefix_encoding_hints(source))
    hint = explicit or raw_declared

    try:
        text, representation = decode_text_source(source, encoding=hint)
    except (UnicodeError, LookupError, ValueError) as exc:
        raise HtmlLexicalError(
            f"HTML source encoding could not be decoded safely: {exc}"
        ) from exc

    declarations = _text_encoding_declarations(text)
    declared = _one_declared_encoding(tuple(item.encoding for item in declarations))
    resolved = _canonical_encoding(representation.encoding)

    if explicit is not None and declared is not None and explicit != declared:
        raise HtmlLexicalError(
            "HTML explicit encoding conflicts with meta encoding declaration"
        )
    if declared is not None and resolved != declared:
        raise HtmlLexicalError(
            "HTML source encoding conflicts with meta encoding declaration"
        )
    if raw_declared is not None and declared is not None and raw_declared != declared:
        raise HtmlLexicalError(
            "HTML raw and decoded encoding declaration evidence conflicts"
        )

    return text, representation, declarations
