from __future__ import annotations

from dataclasses import dataclass
from html import escape as html_escape, unescape as html_unescape
import re

from .._errors import MarkdownIdentityError


_MARKER_RE = re.compile(r'^\s*<!--\s+m2w:(projection|block)(.*?)\s+-->\s*$')
_ENGINE_OPENER_RE = re.compile(r'<!--\s+m2w:')
_ESCAPED_ENGINE_OPENER_RE = re.compile(r'&lt;!--(?=\s+m2w:)')
_ATTR_RE = re.compile(r'\s+([a-z][a-z0-9_-]*)="([^"]*)"')
_ALLOWED = {
    "projection": ("v", "doc", "base"),
    "block": ("pid", "node", "kind", "src"),
}
_REQUIRED = {
    "projection": frozenset({"v", "doc", "base"}),
    "block": frozenset({"pid", "node", "kind", "src"}),
}


@dataclass(frozen=True)
class ParsedMarker:
    marker_type: str
    attributes: dict[str, str]
    unknown_keys: tuple[str, ...] = ()


def _validate_value(value: str, field: str) -> str:
    if "\n" in value or "\r" in value:
        raise MarkdownIdentityError(
            "marker values must stay on one physical line",
            details={"field": field},
        )
    return value


def _encode(marker_type: str, ordered_attrs: tuple[tuple[str, str], ...]) -> str:
    if marker_type not in _ALLOWED:
        raise MarkdownIdentityError("unsupported marker type", details={"marker_type": marker_type})
    pieces = []
    for key, value in ordered_attrs:
        _validate_value(value, key)
        pieces.append(f'{key}="{html_escape(value, quote=True)}"')
    return f"<!-- m2w:{marker_type} {' '.join(pieces)} -->"


def encode_projection_header(*, version: str, document_id: str, source_digest: str) -> str:
    return _encode(
        "projection",
        (("v", version), ("doc", document_id), ("base", f"sha256:{source_digest}")),
    )


def encode_block_marker(*, projection_id: str, node_id: str, kind: str, source_digest: str) -> str:
    return _encode(
        "block",
        (("pid", projection_id), ("node", node_id), ("kind", kind), ("src", f"sha256:{source_digest}")),
    )


def parse_marker_line(line: str, *, strict: bool = True) -> ParsedMarker | None:
    if _ENGINE_OPENER_RE.search(line) is None:
        return None
    match = _MARKER_RE.fullmatch(line)
    if match is None:
        raise MarkdownIdentityError("malformed m2w marker", details={"line": line})
    marker_type, attr_text = match.groups()
    attrs: dict[str, str] = {}
    consumed = ""
    pos = 0
    for attr_match in _ATTR_RE.finditer(attr_text):
        if attr_match.start() != pos:
            gap = attr_text[pos:attr_match.start()]
            if gap.strip():
                raise MarkdownIdentityError("malformed marker attributes", details={"fragment": gap})
        key, raw_value = attr_match.groups()
        if key in attrs:
            raise MarkdownIdentityError("duplicate marker key", details={"key": key})
        if strict and key not in _ALLOWED[marker_type]:
            raise MarkdownIdentityError(
                "unknown marker key",
                details={"key": key, "marker_type": marker_type},
            )
        attrs[key] = html_unescape(raw_value)
        pos = attr_match.end()
    if attr_text[pos:].strip():
        raise MarkdownIdentityError("malformed marker attributes", details={"fragment": attr_text[pos:]})
    missing = _REQUIRED[marker_type] - attrs.keys()
    if missing:
        raise MarkdownIdentityError("missing marker key", details={"missing": sorted(missing), "marker_type": marker_type})
    if strict:
        expected_order = [key for key in _ALLOWED[marker_type] if key in attrs]
        actual_order = [m.group(1) for m in _ATTR_RE.finditer(attr_text)]
        if actual_order != expected_order:
            raise MarkdownIdentityError(
                "marker keys are not in canonical order",
                details={"expected": expected_order, "actual": actual_order},
            )
    unknown_keys = tuple(sorted(set(attrs) - set(_ALLOWED[marker_type])))
    return ParsedMarker(
        marker_type=marker_type,
        attributes=attrs,
        unknown_keys=unknown_keys,
    )


def escape_marker_like_text(text: str) -> str:
    return _ENGINE_OPENER_RE.sub(
        lambda match: "&lt;!--" + match.group(0)[4:],
        text,
    )


def unescape_marker_like_text(text: str) -> str:
    return _ESCAPED_ENGINE_OPENER_RE.sub("<!--", text)
