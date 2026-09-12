from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from html import unescape
from urllib.parse import quote

from .codec import decode_html_source
from .model import (
    HtmlLexicalDocument,
    HtmlLexicalError,
    HtmlLexicalNode,
    HtmlRecoveryEntry,
    HtmlRecoverySignature,
    ParsedHtmlSource,
)
from .recovery import build_recovery_signature


_VOID_ELEMENTS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
_RAWTEXT_ELEMENTS = frozenset({"script", "style"})
_RCDATA_ELEMENTS = frozenset({"title", "textarea"})
_FOREIGN_ELEMENTS = frozenset({"svg", "math"})
_TABLE_ELEMENTS = frozenset(
    {"table", "caption", "colgroup", "tbody", "tfoot", "thead", "tr", "td", "th"}
)
_OPTIONAL_REPEAT_ELEMENTS = frozenset(
    {"p", "li", "dt", "dd", "option", "optgroup", "rt", "rp"}
)
_P_BREAK_ELEMENTS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "div",
        "dl",
        "fieldset",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hgroup",
        "hr",
        "main",
        "menu",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "ul",
    }
)
_NAME_STOP = frozenset(" \t\r\n/>=\f")
_SPACE = frozenset(" \t\r\n\f")


def _digest(raw: str) -> str:
    return sha256(raw.encode("utf-8")).hexdigest()


def _normalize_name(name: str) -> str:
    return name.lower()


def _path_name(name: str) -> str:
    return quote(name, safe="-._~")


@dataclass
class _Owner:
    path: str
    kind: str
    start: int
    end: int
    raw: str
    order: int
    parent_path: str | None = None
    children: list[str] = field(default_factory=list)
    qname: str | None = None
    normalized_name: str | None = None
    value: object = None
    value_start: int | None = None
    value_end: int | None = None
    quote: str | None = None
    start_tag_start: int | None = None
    start_tag_end: int | None = None
    end_tag_start: int | None = None
    end_tag_end: int | None = None
    recovery_reason: str | None = None

    def freeze(self) -> HtmlLexicalNode:
        return HtmlLexicalNode(
            path=self.path,
            kind=self.kind,
            start=self.start,
            end=self.end,
            raw=self.raw,
            raw_digest=_digest(self.raw),
            order=self.order,
            parent_path=self.parent_path,
            children=tuple(self.children),
            qname=self.qname,
            normalized_name=self.normalized_name,
            value=self.value,
            value_start=self.value_start,
            value_end=self.value_end,
            quote=self.quote,
            start_tag_start=self.start_tag_start,
            start_tag_end=self.start_tag_end,
            end_tag_start=self.end_tag_start,
            end_tag_end=self.end_tag_end,
            recovery_reason=self.recovery_reason,
        )


@dataclass
class _Frame:
    owner: _Owner
    element_counts: dict[str, int] = field(default_factory=dict)
    kind_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class _AttributeToken:
    qname: str
    normalized_name: str
    start: int
    end: int
    value: str | None
    value_start: int | None
    value_end: int | None
    quote: str | None


class _Scanner:
    def __init__(self, text: str) -> None:
        self.text = text
        self.length = len(text)
        self.position = 0
        self.owners: list[_Owner] = []
        self.by_path: dict[str, _Owner] = {}
        self.stack: list[_Frame] = []
        self.top_element_counts: dict[str, int] = {}
        self.top_kind_counts: dict[str, int] = {}
        self.root_path: str | None = None
        self.recovery_reason: str | None = None

    def _set_reason(self, reason: str) -> None:
        if self.recovery_reason is None:
            self.recovery_reason = reason

    def _current_parent(self) -> _Frame | None:
        return self.stack[-1] if self.stack else None

    def _append_owner(self, owner: _Owner) -> None:
        if owner.path in self.by_path:
            raise HtmlLexicalError(f"HTML lexical ownership path is ambiguous: {owner.path}")
        self.owners.append(owner)
        self.by_path[owner.path] = owner
        if owner.parent_path is not None:
            parent = self.by_path.get(owner.parent_path)
            if parent is None:
                raise HtmlLexicalError("HTML lexical parent ownership is missing")
            parent.children.append(owner.path)

    def _next_element_path(self, normalized_name: str) -> tuple[str, str | None]:
        parent = self._current_parent()
        counts = parent.element_counts if parent is not None else self.top_element_counts
        counts[normalized_name] = counts.get(normalized_name, 0) + 1
        segment = f"{_path_name(normalized_name)}[{counts[normalized_name]}]"
        if parent is None:
            return f"/{segment}", None
        return f"{parent.owner.path}/{segment}", parent.owner.path

    def _next_kind_path(self, kind: str, parent: _Frame | None) -> tuple[str, str | None]:
        counts = parent.kind_counts if parent is not None else self.top_kind_counts
        counts[kind] = counts.get(kind, 0) + 1
        segment = f"#{kind}[{counts[kind]}]"
        if parent is None:
            return f"/{segment}", None
        return f"{parent.owner.path}/{segment}", parent.owner.path

    def _skip_space(self, position: int) -> int:
        while position < self.length and self.text[position] in _SPACE:
            position += 1
        return position

    def _parse_name(self, position: int) -> tuple[str, int]:
        start = position
        while position < self.length and self.text[position] not in _NAME_STOP:
            if self.text[position] == "<":
                break
            position += 1
        if position == start:
            raise HtmlLexicalError("HTML tag or attribute name is missing")
        return self.text[start:position], position

    def _parse_start_tag(
        self, start: int
    ) -> tuple[str, str, int, tuple[_AttributeToken, ...], bool]:
        position = start + 1
        qname, position = self._parse_name(position)
        normalized_name = _normalize_name(qname)
        attributes: list[_AttributeToken] = []
        self_closing = False

        while True:
            position = self._skip_space(position)
            if position >= self.length:
                raise HtmlLexicalError("HTML start tag is unterminated")
            if self.text.startswith("/>", position):
                position += 2
                self_closing = True
                break
            if self.text[position] == ">":
                position += 1
                break
            if self.text[position] == "<":
                raise HtmlLexicalError("HTML start tag contains unexpected '<'")

            attr_start = position
            attr_qname, position = self._parse_name(position)
            attr_name = _normalize_name(attr_qname)
            position = self._skip_space(position)
            value: str | None = None
            value_start: int | None = None
            value_end: int | None = None
            quote_character: str | None = None

            if position < self.length and self.text[position] == "=":
                position += 1
                position = self._skip_space(position)
                if position >= self.length:
                    raise HtmlLexicalError("HTML attribute value is missing")
                if self.text[position] in {"'", '"'}:
                    quote_character = self.text[position]
                    position += 1
                    value_start = position
                    end = self.text.find(quote_character, position)
                    if end < 0:
                        raise HtmlLexicalError("HTML quoted attribute value is unterminated")
                    value_end = end
                    value = unescape(self.text[value_start:value_end])
                    position = end + 1
                else:
                    value_start = position
                    while position < self.length:
                        character = self.text[position]
                        if character in _SPACE or character == ">":
                            break
                        if character in {'"', "'", "<", "=", "`"}:
                            raise HtmlLexicalError(
                                "HTML unquoted attribute contains an ambiguous character"
                            )
                        if character == "/" and self.text.startswith("/>", position):
                            break
                        position += 1
                    if position == value_start:
                        raise HtmlLexicalError("HTML unquoted attribute value is empty")
                    value_end = position
                    value = unescape(self.text[value_start:value_end])
            attr_end = position
            attributes.append(
                _AttributeToken(
                    qname=attr_qname,
                    normalized_name=attr_name,
                    start=attr_start,
                    end=attr_end,
                    value=value,
                    value_start=value_start,
                    value_end=value_end,
                    quote=quote_character,
                )
            )

        return qname, normalized_name, position, tuple(attributes), self_closing

    def _parse_end_tag(self, start: int) -> tuple[str, str, int]:
        position = start + 2
        position = self._skip_space(position)
        qname, position = self._parse_name(position)
        normalized_name = _normalize_name(qname)
        position = self._skip_space(position)
        if position >= self.length or self.text[position] != ">":
            raise HtmlLexicalError("HTML end tag is malformed")
        return qname, normalized_name, position + 1

    def _close_frame(
        self,
        frame: _Frame,
        end: int,
        *,
        end_tag_start: int | None = None,
        end_tag_end: int | None = None,
    ) -> None:
        frame.owner.end = end
        frame.owner.raw = self.text[frame.owner.start:end]
        frame.owner.end_tag_start = end_tag_start
        frame.owner.end_tag_end = end_tag_end

    def _implicitly_close_top(self, at: int, reason: str) -> None:
        frame = self.stack.pop()
        frame.owner.recovery_reason = reason
        self._close_frame(frame, at)
        self._set_reason(reason)

    def _apply_start_recovery_rules(self, normalized_name: str, at: int) -> None:
        if normalized_name in _FOREIGN_ELEMENTS:
            self._set_reason("html.foreign_content.unsupported")
        elif normalized_name == "template":
            self._set_reason("html.template.recovery_sensitive")
        elif normalized_name in _TABLE_ELEMENTS:
            self._set_reason("html.table.recovery_sensitive")

        if not self.stack:
            return
        top_name = self.stack[-1].owner.normalized_name
        if top_name == normalized_name and normalized_name in _OPTIONAL_REPEAT_ELEMENTS:
            self._implicitly_close_top(at, "html.recovery.optional_end_tag")
            return
        if any(frame.owner.normalized_name == "p" for frame in self.stack):
            if normalized_name in _P_BREAK_ELEMENTS and top_name == "p":
                self._implicitly_close_top(at, "html.recovery.nested_p")

    def _add_attributes(
        self,
        element: _Owner,
        attributes: tuple[_AttributeToken, ...],
    ) -> None:
        totals: dict[str, int] = {}
        for token in attributes:
            totals[token.normalized_name] = totals.get(token.normalized_name, 0) + 1
        occurrences: dict[str, int] = {}
        if any(count > 1 for count in totals.values()):
            self._set_reason("html.attribute.duplicate_name")

        for token in attributes:
            occurrences[token.normalized_name] = occurrences.get(token.normalized_name, 0) + 1
            suffix = (
                f"[{occurrences[token.normalized_name]}]"
                if totals[token.normalized_name] > 1
                else ""
            )
            path = f"{element.path}/@{_path_name(token.normalized_name)}{suffix}"
            raw = self.text[token.start : token.end]
            owner = _Owner(
                path=path,
                kind="attribute",
                start=token.start,
                end=token.end,
                raw=raw,
                order=len(self.owners),
                parent_path=element.path,
                qname=token.qname,
                normalized_name=token.normalized_name,
                value=token.value,
                value_start=token.value_start,
                value_end=token.value_end,
                quote=token.quote,
                recovery_reason=(
                    "html.attribute.duplicate_name"
                    if totals[token.normalized_name] > 1
                    else None
                ),
            )
            self._append_owner(owner)

    def _add_data_owner(self, kind: str, start: int, end: int) -> None:
        if end <= start:
            return
        parent = self._current_parent()
        path, parent_path = self._next_kind_path(kind, parent)
        raw = self.text[start:end]
        value = raw if kind == "rawtext" else unescape(raw)
        self._append_owner(
            _Owner(
                path=path,
                kind=kind,
                start=start,
                end=end,
                raw=raw,
                order=len(self.owners),
                parent_path=parent_path,
                value=value,
            )
        )

    def _parse_comment(self) -> None:
        start = self.position
        end_marker = self.text.find("-->", start + 4)
        if end_marker < 0:
            raise HtmlLexicalError("HTML comment is unterminated")
        end = end_marker + 3
        parent = self._current_parent()
        path, parent_path = self._next_kind_path("comment", parent)
        self._append_owner(
            _Owner(
                path=path,
                kind="comment",
                start=start,
                end=end,
                raw=self.text[start:end],
                order=len(self.owners),
                parent_path=parent_path,
                value=self.text[start + 4 : end_marker],
            )
        )
        self.position = end

    def _parse_doctype(self) -> None:
        start = self.position
        end_marker = self.text.find(">", start + 2)
        if end_marker < 0:
            raise HtmlLexicalError("HTML doctype is unterminated")
        end = end_marker + 1
        parent = self._current_parent()
        path, parent_path = self._next_kind_path("doctype", parent)
        self._append_owner(
            _Owner(
                path=path,
                kind="doctype",
                start=start,
                end=end,
                raw=self.text[start:end],
                order=len(self.owners),
                parent_path=parent_path,
                value=self.text[start + 2 : end_marker].strip(),
            )
        )
        self.position = end

    def _consume_special_content(self, frame: _Frame, kind: str) -> None:
        name = frame.owner.normalized_name
        assert name is not None
        lower_text = self.text.lower()
        marker = f"</{name}"
        end_start = lower_text.find(marker, self.position)
        if end_start < 0:
            self._add_data_owner(kind, self.position, self.length)
            self.position = self.length
            self.stack.pop()
            frame.owner.recovery_reason = "html.recovery.unclosed_tag"
            self._close_frame(frame, self.length)
            self._set_reason("html.recovery.unclosed_tag")
            return

        self._add_data_owner(kind, self.position, end_start)
        _qname, end_name, end = self._parse_end_tag(end_start)
        if end_name != name:
            raise HtmlLexicalError("HTML special-content end tag is inconsistent")
        self.position = end
        self.stack.pop()
        self._close_frame(frame, end, end_tag_start=end_start, end_tag_end=end)

    def _parse_start(self) -> None:
        start = self.position
        qname, normalized_name, end, attributes, self_closing = self._parse_start_tag(start)
        self._apply_start_recovery_rules(normalized_name, start)
        path, parent_path = self._next_element_path(normalized_name)
        owner = _Owner(
            path=path,
            kind="element",
            start=start,
            end=end,
            raw=self.text[start:end],
            order=len(self.owners),
            parent_path=parent_path,
            qname=qname,
            normalized_name=normalized_name,
            start_tag_start=start,
            start_tag_end=end,
        )
        self._append_owner(owner)
        self._add_attributes(owner, attributes)
        if parent_path is None:
            if self.root_path is None:
                self.root_path = path
            elif self.root_path != path:
                self._set_reason("html.recovery.multiple_roots")

        self.position = end
        if normalized_name in _VOID_ELEMENTS:
            if self_closing:
                owner.end = end
                owner.raw = self.text[start:end]
            return
        if self_closing:
            owner.recovery_reason = "html.recovery.nonvoid_self_closing"
            self._set_reason("html.recovery.nonvoid_self_closing")
            return

        frame = _Frame(owner)
        self.stack.append(frame)
        if normalized_name in _RAWTEXT_ELEMENTS:
            self._consume_special_content(frame, "rawtext")
        elif normalized_name in _RCDATA_ELEMENTS:
            self._consume_special_content(frame, "rcdata")

    def _parse_end(self) -> None:
        start = self.position
        _qname, normalized_name, end = self._parse_end_tag(start)
        self.position = end
        if normalized_name in _VOID_ELEMENTS:
            self._set_reason("html.recovery.void_end_tag")
            return
        if not self.stack:
            self._set_reason("html.recovery.mismatched_tag")
            return

        match_index: int | None = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index].owner.normalized_name == normalized_name:
                match_index = index
                break
        if match_index is None:
            self._set_reason("html.recovery.mismatched_tag")
            return
        while len(self.stack) - 1 > match_index:
            frame = self.stack.pop()
            frame.owner.recovery_reason = "html.recovery.mismatched_tag"
            self._close_frame(frame, start)
            self._set_reason("html.recovery.mismatched_tag")
        frame = self.stack.pop()
        self._close_frame(frame, end, end_tag_start=start, end_tag_end=end)

    def scan(self) -> HtmlLexicalDocument:
        while self.position < self.length:
            if self.text.startswith("<!--", self.position):
                self._parse_comment()
                continue
            if self.text[self.position : self.position + 9].lower() == "<!doctype":
                self._parse_doctype()
                continue
            if self.text.startswith("</", self.position):
                self._parse_end()
                continue
            if self.text[self.position] == "<":
                if self.text.startswith("<!", self.position) or self.text.startswith(
                    "<?", self.position
                ):
                    raise HtmlLexicalError("HTML declaration token is unsupported")
                self._parse_start()
                continue

            start = self.position
            next_tag = self.text.find("<", start)
            self.position = self.length if next_tag < 0 else next_tag
            self._add_data_owner("text", start, self.position)

        while self.stack:
            frame = self.stack.pop()
            frame.owner.recovery_reason = "html.recovery.unclosed_tag"
            self._close_frame(frame, self.length)
            self._set_reason("html.recovery.unclosed_tag")

        frozen = tuple(owner.freeze() for owner in self.owners)
        return HtmlLexicalDocument(
            root_path=self.root_path,
            nodes=frozen,
            recovery_reason=self.recovery_reason,
        )


def _lexical_recovery_signature(document: HtmlLexicalDocument) -> HtmlRecoverySignature:
    by_path = {node.path: node for node in document.nodes}
    entries: list[HtmlRecoveryEntry] = []

    def depth_of(node: HtmlLexicalNode) -> int:
        depth = 0
        parent_path = node.parent_path
        while parent_path is not None:
            parent = by_path[parent_path]
            if parent.kind == "element":
                depth += 1
            parent_path = parent.parent_path
        return depth

    for node in sorted(document.nodes, key=lambda item: item.order):
        depth = depth_of(node)
        if node.kind == "attribute":
            continue
        if node.kind == "element":
            attributes = tuple(
                sorted(
                    child.normalized_name or ""
                    for child in document.nodes
                    if child.parent_path == node.path and child.kind == "attribute"
                )
            )
            entries.append(
                HtmlRecoveryEntry(
                    kind="tag",
                    name=node.normalized_name,
                    depth=depth,
                    attribute_names=attributes,
                )
            )
        elif node.kind in {"text", "rawtext", "rcdata"}:
            entries.append(HtmlRecoveryEntry("text", None, depth))
        elif node.kind == "comment":
            entries.append(HtmlRecoveryEntry("comment", None, depth))
        elif node.kind == "doctype":
            entries.append(HtmlRecoveryEntry("doctype", None, depth))
    return HtmlRecoverySignature(tuple(entries))


def scan_html_text(text: str) -> HtmlLexicalDocument:
    if not isinstance(text, str):
        raise TypeError("HTML lexical source must be a string")
    return _Scanner(text).scan()


def parse_html_source(
    source: bytes,
    *,
    encoding: str | None = None,
) -> ParsedHtmlSource:
    text, representation, declarations = decode_html_source(source, encoding=encoding)
    lexical = scan_html_text(text)
    recovered = build_recovery_signature(text)
    reason = lexical.recovery_reason
    if reason is None and _lexical_recovery_signature(lexical) != recovered:
        reason = "html.recovery.unstable"
    return ParsedHtmlSource(
        text=text,
        representation=representation,
        lexical=lexical,
        encoding_declarations=declarations,
        recovery_signature=recovered,
        recovery_stable=reason is None,
        recovery_reason=reason,
    )
