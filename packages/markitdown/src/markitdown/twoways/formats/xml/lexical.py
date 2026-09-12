from __future__ import annotations

import codecs
from hashlib import sha256
import re
from urllib.parse import quote
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree as DefusedElementTree
from defusedxml.common import DefusedXmlException

from ..text.codec import decode_text_source, encode_text_source
from .model import (
    ParsedXmlSource,
    XmlDeclaration,
    XmlLexicalDocument,
    XmlLexicalError,
    XmlLexicalNode,
)


_XML_URI = "http://www.w3.org/XML/1998/namespace"
_XMLNS_URI = "http://www.w3.org/2000/xmlns/"
_PREDEFINED = {
    "amp": "&",
    "lt": "<",
    "gt": ">",
    "apos": "'",
    "quot": '"',
}
_DECL_RE = re.compile(
    r"""<\?xml\s+version\s*=\s*(?P<vq>['"])(?P<version>[^'"]+)(?P=vq)"""
    r"""(?:\s+encoding\s*=\s*(?P<eq>['"])(?P<encoding>[A-Za-z][A-Za-z0-9._-]*)(?P=eq))?"""
    r"""(?:\s+standalone\s*=\s*(?P<sq>['"])(?P<standalone>yes|no)(?P=sq))?\s*\?>"""
)
_BYTES_DECL_ENCODING_RE = re.compile(
    rb"""^<\?xml\s+version\s*=\s*['"][^'"]+['"]"""
    rb""".*?\s+encoding\s*=\s*['"](?P<encoding>[A-Za-z][A-Za-z0-9._-]*)['"]""",
    re.DOTALL,
)
_NAME_DELIMITERS = frozenset(" \t\r\n/><=?")


def _digest(raw: str) -> str:
    return sha256(raw.encode("utf-8")).hexdigest()


def _is_xml_char(character: str) -> bool:
    value = ord(character)
    return (
        value in {0x9, 0xA, 0xD}
        or 0x20 <= value <= 0xD7FF
        or 0xE000 <= value <= 0xFFFD
        or 0x10000 <= value <= 0x10FFFF
    )


def _validate_xml_characters(value: str) -> None:
    if any(not _is_xml_char(character) for character in value):
        raise XmlLexicalError("XML source contains a character forbidden by XML 1.0")


def _split_qname(qname: str) -> tuple[str | None, str]:
    if not qname or qname.count(":") > 1:
        raise XmlLexicalError(f"invalid XML qualified name: {qname!r}")
    if ":" not in qname:
        return None, qname
    prefix, local = qname.split(":", 1)
    if not prefix or not local:
        raise XmlLexicalError(f"invalid XML qualified name: {qname!r}")
    return prefix, local


def _expanded_name(
    qname: str,
    namespaces: dict[str, str],
    *,
    attribute: bool,
) -> str:
    prefix, local = _split_qname(qname)
    if prefix is None:
        uri = "" if attribute else namespaces.get("", "")
    else:
        if prefix not in namespaces or not namespaces[prefix]:
            raise XmlLexicalError(f"undeclared XML namespace prefix: {prefix!r}")
        uri = namespaces[prefix]
    return f"{{{uri}}}{local}" if uri else local


def _path_component(expanded_name: str) -> str:
    return quote(expanded_name, safe="")


def _decode_reference(reference: str) -> str:
    if reference.startswith("#x"):
        digits = reference[2:]
        base = 16
    elif reference.startswith("#"):
        digits = reference[1:]
        base = 10
    else:
        if reference not in _PREDEFINED:
            raise XmlLexicalError(f"unsupported XML entity reference: &{reference};")
        return _PREDEFINED[reference]
    if not digits:
        raise XmlLexicalError("XML numeric character reference is empty")
    try:
        value = int(digits, base)
        character = chr(value)
    except (ValueError, OverflowError) as exc:
        raise XmlLexicalError("XML numeric character reference is invalid") from exc
    if not _is_xml_char(character):
        raise XmlLexicalError("XML numeric character reference is forbidden by XML 1.0")
    return character


def _decode_value(raw: str, *, attribute: bool) -> str:
    result: list[str] = []
    index = 0
    while index < len(raw):
        character = raw[index]
        if character == "&":
            end = raw.find(";", index + 1)
            if end < 0:
                raise XmlLexicalError("XML character/entity reference is unterminated")
            result.append(_decode_reference(raw[index + 1 : end]))
            index = end + 1
            continue
        if character == "\r":
            if index + 1 < len(raw) and raw[index + 1] == "\n":
                index += 2
            else:
                index += 1
            result.append(" " if attribute else "\n")
            continue
        if character == "\n":
            result.append(" " if attribute else "\n")
            index += 1
            continue
        if attribute and character == "\t":
            result.append(" ")
            index += 1
            continue
        if not _is_xml_char(character):
            raise XmlLexicalError(
                "XML source contains a character forbidden by XML 1.0"
            )
        result.append(character)
        index += 1
    value = "".join(result)
    _validate_xml_characters(value)
    return value


def _declaration(text: str) -> XmlDeclaration | None:
    if not text.startswith("<?xml"):
        return None
    match = _DECL_RE.match(text)
    if match is None:
        raise XmlLexicalError("XML declaration is malformed or unsupported")
    version = match.group("version")
    if version != "1.0":
        raise XmlLexicalError("XML 1.1 and other XML versions are unsupported in H4")
    raw = match.group(0)
    return XmlDeclaration(
        start=0,
        end=match.end(),
        raw=raw,
        raw_digest=_digest(raw),
        version=version,
        encoding=match.group("encoding"),
        standalone=match.group("standalone"),
    )


class _Scanner:
    def __init__(self, text: str) -> None:
        self.text = text
        self.length = len(text)
        self.position = 0
        self.top_kind_counts = {
            "comment": 0,
            "processing_instruction": 0,
        }

    def parse(self) -> XmlLexicalDocument:
        declaration = _declaration(self.text)
        if declaration is not None:
            self.position = declaration.end
        before = self._parse_misc()
        self._skip_space()
        if self.position >= self.length:
            raise XmlLexicalError("XML source has no document element")
        if self.text.startswith("<!DOCTYPE", self.position) or self.text.startswith(
            "<!doctype", self.position
        ):
            raise XmlLexicalError("XML DTDs are forbidden in H4")
        root_nodes = self._parse_element(
            parent_path=None,
            inherited_namespaces={"xml": _XML_URI},
            sibling_counts={},
        )
        root = root_nodes[0]
        after = self._parse_misc()
        self._skip_space()
        if self.position != self.length:
            if self.text.startswith("<!", self.position):
                raise XmlLexicalError("unsupported XML markup declaration")
            raise XmlLexicalError("XML source contains data after the document element")
        nodes = tuple(before + root_nodes + after)
        return XmlLexicalDocument(
            root_path=root.path,
            nodes=nodes,
            declaration=declaration,
        )

    def _skip_space(self) -> None:
        while self.position < self.length and self.text[self.position] in " \t\r\n":
            self.position += 1

    def _parse_misc(self) -> list[XmlLexicalNode]:
        nodes: list[XmlLexicalNode] = []
        while True:
            self._skip_space()
            if self.text.startswith("<!--", self.position):
                nodes.append(self._parse_comment(None, self.top_kind_counts))
                continue
            if self.text.startswith("<?", self.position):
                nodes.append(self._parse_pi(None, self.top_kind_counts))
                continue
            if self.text.startswith("<!", self.position):
                raise XmlLexicalError("XML DTDs and markup declarations are forbidden")
            return nodes

    def _parse_qname(self) -> str:
        start = self.position
        while (
            self.position < self.length
            and self.text[self.position] not in _NAME_DELIMITERS
        ):
            self.position += 1
        if self.position == start:
            raise XmlLexicalError("expected XML qualified name")
        qname = self.text[start : self.position]
        _split_qname(qname)
        return qname

    def _parse_attribute_token(self) -> dict[str, object]:
        start = self.position
        qname = self._parse_qname()
        self._skip_space()
        if self.position >= self.length or self.text[self.position] != "=":
            raise XmlLexicalError("XML attribute is missing '='")
        self.position += 1
        self._skip_space()
        if self.position >= self.length or self.text[self.position] not in {'"', "'"}:
            raise XmlLexicalError("XML attribute value must be quoted")
        quote_character = self.text[self.position]
        self.position += 1
        value_start = self.position
        while (
            self.position < self.length and self.text[self.position] != quote_character
        ):
            if self.text[self.position] == "<":
                raise XmlLexicalError("XML attribute value contains '<'")
            self.position += 1
        if self.position >= self.length:
            raise XmlLexicalError("XML attribute value is unterminated")
        value_end = self.position
        raw_value = self.text[value_start:value_end]
        self.position += 1
        end = self.position
        return {
            "start": start,
            "end": end,
            "qname": qname,
            "quote": quote_character,
            "value_start": value_start,
            "value_end": value_end,
            "raw_value": raw_value,
            "value": _decode_value(raw_value, attribute=True),
        }

    def _apply_namespace_declarations(
        self,
        attributes: list[dict[str, object]],
        inherited_namespaces: dict[str, str],
    ) -> tuple[dict[str, str], list[dict[str, object]], list[dict[str, object]]]:
        namespaces = dict(inherited_namespaces)
        declarations: list[dict[str, object]] = []
        normal: list[dict[str, object]] = []
        seen_qnames: set[str] = set()
        for attribute in attributes:
            qname = str(attribute["qname"])
            if qname in seen_qnames:
                raise XmlLexicalError(f"duplicate XML attribute qname: {qname!r}")
            seen_qnames.add(qname)
            if qname == "xmlns":
                prefix = ""
            elif qname.startswith("xmlns:"):
                prefix = qname.split(":", 1)[1]
                if not prefix or ":" in prefix:
                    raise XmlLexicalError("XML namespace declaration prefix is invalid")
            else:
                normal.append(attribute)
                continue

            uri = str(attribute["value"])
            if prefix == "xmlns":
                raise XmlLexicalError("the xmlns prefix cannot be rebound")
            if uri == _XMLNS_URI:
                raise XmlLexicalError("the xmlns namespace URI cannot be rebound")
            if prefix == "xml":
                if uri != _XML_URI:
                    raise XmlLexicalError("the xml prefix has a fixed namespace URI")
            elif uri == _XML_URI:
                raise XmlLexicalError(
                    "the XML namespace URI belongs only to prefix xml"
                )
            if prefix and not uri:
                raise XmlLexicalError("prefixed XML namespaces cannot be undeclared")
            namespaces[prefix] = uri
            declared = dict(attribute)
            declared["namespace_prefix"] = prefix
            declarations.append(declared)
        return namespaces, declarations, normal

    def _parse_element(
        self,
        *,
        parent_path: str | None,
        inherited_namespaces: dict[str, str],
        sibling_counts: dict[str, int],
    ) -> list[XmlLexicalNode]:
        if self.position >= self.length or self.text[self.position] != "<":
            raise XmlLexicalError("expected XML element")
        if self.text.startswith(("</", "<!", "<?"), self.position):
            raise XmlLexicalError("expected XML start tag")
        element_start = self.position
        self.position += 1
        qname = self._parse_qname()

        attributes: list[dict[str, object]] = []
        self_closing = False
        while True:
            self._skip_space()
            if self.position >= self.length:
                raise XmlLexicalError("XML start tag is unterminated")
            if self.text.startswith("/>", self.position):
                self.position += 2
                self_closing = True
                break
            if self.text[self.position] == ">":
                self.position += 1
                break
            attributes.append(self._parse_attribute_token())

        namespaces, namespace_attrs, normal_attrs = self._apply_namespace_declarations(
            attributes,
            inherited_namespaces,
        )
        expanded = _expanded_name(qname, namespaces, attribute=False)
        sibling_counts[expanded] = sibling_counts.get(expanded, 0) + 1
        element_index = sibling_counts[expanded]
        component = f"{_path_component(expanded)}[{element_index}]"
        path = f"/{component}" if parent_path is None else f"{parent_path}/{component}"

        owned_attributes: list[XmlLexicalNode] = []
        for attribute in namespace_attrs:
            prefix = str(attribute["namespace_prefix"])
            attribute_path = path + (
                "/@xmlns" if prefix == "" else f"/@xmlns%3A{quote(prefix, safe='')}"
            )
            start = int(attribute["start"])
            end = int(attribute["end"])
            raw = self.text[start:end]
            owned_attributes.append(
                XmlLexicalNode(
                    path=attribute_path,
                    kind="namespace",
                    start=start,
                    end=end,
                    raw=raw,
                    raw_digest=_digest(raw),
                    parent_path=path,
                    qname=str(attribute["qname"]),
                    value=attribute["value"],
                    value_start=int(attribute["value_start"]),
                    value_end=int(attribute["value_end"]),
                    quote=str(attribute["quote"]),
                    namespace_prefix=prefix,
                    namespace_uri=str(attribute["value"]),
                )
            )

        seen_expanded_attributes: set[str] = set()
        for attribute in normal_attrs:
            attribute_qname = str(attribute["qname"])
            attribute_expanded = _expanded_name(
                attribute_qname,
                namespaces,
                attribute=True,
            )
            if attribute_expanded in seen_expanded_attributes:
                raise XmlLexicalError(
                    f"duplicate XML expanded attribute name: {attribute_expanded!r}"
                )
            seen_expanded_attributes.add(attribute_expanded)
            attribute_path = f"{path}/@{_path_component(attribute_expanded)}"
            start = int(attribute["start"])
            end = int(attribute["end"])
            raw = self.text[start:end]
            owned_attributes.append(
                XmlLexicalNode(
                    path=attribute_path,
                    kind="attribute",
                    start=start,
                    end=end,
                    raw=raw,
                    raw_digest=_digest(raw),
                    parent_path=path,
                    qname=attribute_qname,
                    expanded_name=attribute_expanded,
                    value=attribute["value"],
                    value_start=int(attribute["value_start"]),
                    value_end=int(attribute["value_end"]),
                    quote=str(attribute["quote"]),
                )
            )

        content_nodes: list[XmlLexicalNode] = []
        if not self_closing:
            element_child_counts: dict[str, int] = {}
            lexical_kind_counts = {
                "text": 0,
                "cdata": 0,
                "comment": 0,
                "processing_instruction": 0,
            }
            while True:
                if self.position >= self.length:
                    raise XmlLexicalError("XML element is missing its end tag")
                if self.text.startswith("</", self.position):
                    self.position += 2
                    end_qname = self._parse_qname()
                    self._skip_space()
                    if self.position >= self.length or self.text[self.position] != ">":
                        raise XmlLexicalError("XML end tag is malformed")
                    self.position += 1
                    if end_qname != qname:
                        raise XmlLexicalError(
                            f"XML end tag {end_qname!r} does not match {qname!r}"
                        )
                    break
                if self.text.startswith("<!--", self.position):
                    content_nodes.append(self._parse_comment(path, lexical_kind_counts))
                    continue
                if self.text.startswith("<![CDATA[", self.position):
                    content_nodes.append(self._parse_cdata(path, lexical_kind_counts))
                    continue
                if self.text.startswith(
                    "<!DOCTYPE", self.position
                ) or self.text.startswith("<!", self.position):
                    raise XmlLexicalError(
                        "XML DTDs and markup declarations are forbidden in H4"
                    )
                if self.text.startswith("<?", self.position):
                    content_nodes.append(self._parse_pi(path, lexical_kind_counts))
                    continue
                if self.text[self.position] == "<":
                    content_nodes.extend(
                        self._parse_element(
                            parent_path=path,
                            inherited_namespaces=namespaces,
                            sibling_counts=element_child_counts,
                        )
                    )
                    continue
                content_nodes.append(self._parse_text(path, lexical_kind_counts))

        element_end = self.position
        raw = self.text[element_start:element_end]
        child_paths = tuple(
            node.path
            for node in content_nodes
            if node.parent_path == path
            and node.kind
            in {
                "element",
                "text",
                "cdata",
                "comment",
                "processing_instruction",
            }
        )
        element = XmlLexicalNode(
            path=path,
            kind="element",
            start=element_start,
            end=element_end,
            raw=raw,
            raw_digest=_digest(raw),
            parent_path=parent_path,
            children=child_paths,
            qname=qname,
            expanded_name=expanded,
        )
        return [element, *owned_attributes, *content_nodes]

    def _parse_text(
        self,
        parent_path: str,
        kind_counts: dict[str, int],
    ) -> XmlLexicalNode:
        start = self.position
        while self.position < self.length and self.text[self.position] != "<":
            self.position += 1
        if self.position == start:
            raise XmlLexicalError("empty XML text ownership")
        raw = self.text[start : self.position]
        if "]] >".replace(" ", "") in raw:
            raise XmlLexicalError("XML character data cannot contain ']]>'")
        value = _decode_value(raw, attribute=False)
        kind_counts["text"] += 1
        path = f"{parent_path}/#text[{kind_counts['text']}]"
        return XmlLexicalNode(
            path=path,
            kind="text",
            start=start,
            end=self.position,
            raw=raw,
            raw_digest=_digest(raw),
            parent_path=parent_path,
            value=value,
            value_start=start,
            value_end=self.position,
        )

    def _parse_comment(
        self,
        parent_path: str | None,
        kind_counts: dict[str, int],
    ) -> XmlLexicalNode:
        start = self.position
        end_marker = self.text.find("-->", start + 4)
        if end_marker < 0:
            raise XmlLexicalError("XML comment is unterminated")
        content = self.text[start + 4 : end_marker]
        if "--" in content:
            raise XmlLexicalError("XML comment contains forbidden '--'")
        self.position = end_marker + 3
        raw = self.text[start : self.position]
        kind_counts["comment"] += 1
        base = "" if parent_path is None else parent_path
        path = f"{base}/#comment[{kind_counts['comment']}]"
        return XmlLexicalNode(
            path=path,
            kind="comment",
            start=start,
            end=self.position,
            raw=raw,
            raw_digest=_digest(raw),
            parent_path=parent_path,
            value=content,
        )

    def _parse_pi(
        self,
        parent_path: str | None,
        kind_counts: dict[str, int],
    ) -> XmlLexicalNode:
        start = self.position
        self.position += 2
        target = self._parse_qname()
        if target.lower() == "xml":
            raise XmlLexicalError("processing-instruction target 'xml' is reserved")
        end_marker = self.text.find("?>", self.position)
        if end_marker < 0:
            raise XmlLexicalError("XML processing instruction is unterminated")
        data = self.text[self.position : end_marker].strip()
        self.position = end_marker + 2
        raw = self.text[start : self.position]
        kind_counts["processing_instruction"] += 1
        base = "" if parent_path is None else parent_path
        path = f"{base}/#pi[{kind_counts['processing_instruction']}]"
        return XmlLexicalNode(
            path=path,
            kind="processing_instruction",
            start=start,
            end=self.position,
            raw=raw,
            raw_digest=_digest(raw),
            parent_path=parent_path,
            qname=target,
            value=data,
        )

    def _parse_cdata(
        self,
        parent_path: str,
        kind_counts: dict[str, int],
    ) -> XmlLexicalNode:
        start = self.position
        content_start = start + len("<![CDATA[")
        end_marker = self.text.find("]]>", content_start)
        if end_marker < 0:
            raise XmlLexicalError("XML CDATA section is unterminated")
        raw_value = self.text[content_start:end_marker]
        value = raw_value.replace("\r\n", "\n").replace("\r", "\n")
        _validate_xml_characters(value)
        self.position = end_marker + 3
        raw = self.text[start : self.position]
        kind_counts["cdata"] += 1
        path = f"{parent_path}/#cdata[{kind_counts['cdata']}]"
        return XmlLexicalNode(
            path=path,
            kind="cdata",
            start=start,
            end=self.position,
            raw=raw,
            raw_digest=_digest(raw),
            parent_path=parent_path,
            value=value,
            value_start=content_start,
            value_end=end_marker,
        )


def _security_cross_check(text: str) -> None:
    try:
        DefusedElementTree.fromstring(
            text,
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
    except (DefusedXmlException, ParseError, ValueError) as exc:
        raise XmlLexicalError(
            f"XML security/well-formedness check failed: {exc}"
        ) from exc


def scan_xml_text(text: str) -> XmlLexicalDocument:
    if not isinstance(text, str):
        raise TypeError("XML text must be a string")
    if text.startswith("\ufeff"):
        raise XmlLexicalError("decoded XML text must not retain a BOM character")
    scanner = _Scanner(text)
    document = scanner.parse()
    _security_cross_check(text)
    return document


def _signature_encoding(source: bytes) -> str | None:
    if source.startswith(codecs.BOM_UTF32_LE):
        return "utf-32-le"
    if source.startswith(codecs.BOM_UTF32_BE):
        return "utf-32-be"
    if source.startswith(codecs.BOM_UTF8):
        return "utf-8"
    if source.startswith(codecs.BOM_UTF16_LE):
        return "utf-16-le"
    if source.startswith(codecs.BOM_UTF16_BE):
        return "utf-16-be"
    if source.startswith(b"\x00\x00\x00<"):
        return "utf-32-be"
    if source.startswith(b"<\x00\x00\x00"):
        return "utf-32-le"
    if source.startswith(b"\x00<\x00?"):
        return "utf-16-be"
    if source.startswith(b"<\x00?\x00"):
        return "utf-16-le"
    return None


def _declared_encoding_from_ascii_prefix(source: bytes) -> str | None:
    prefix = source[:512]
    if b"\x00" in prefix:
        return None
    match = _BYTES_DECL_ENCODING_RE.match(prefix)
    if match is None:
        return None
    return match.group("encoding").decode("ascii")


def _canonical_codec(name: str) -> str:
    try:
        return codecs.lookup(name).name
    except LookupError as exc:
        raise XmlLexicalError(f"unknown XML source encoding: {name!r}") from exc


def _encoding_compatible(resolved: str, declared: str) -> bool:
    resolved_canonical = _canonical_codec(resolved)
    declared_canonical = _canonical_codec(declared)
    if resolved_canonical == declared_canonical:
        return True
    if declared_canonical == "utf-16" and resolved_canonical in {
        "utf-16-le",
        "utf-16-be",
    }:
        return True
    if declared_canonical == "utf-32" and resolved_canonical in {
        "utf-32-le",
        "utf-32-be",
    }:
        return True
    return declared_canonical == "utf-8" and resolved_canonical == "utf-8"


def parse_xml_source(
    source: bytes,
    *,
    encoding: str | None = None,
) -> ParsedXmlSource:
    if not isinstance(source, bytes):
        raise TypeError("XML source must be bytes")
    signature = _signature_encoding(source)
    declared_hint = _declared_encoding_from_ascii_prefix(source)
    hint = encoding or signature or declared_hint
    if encoding is not None and signature is not None:
        explicit = _canonical_codec(encoding)
        compatible = {_canonical_codec(signature)}
        if signature.startswith("utf-16-"):
            compatible.add("utf-16")
        if signature.startswith("utf-32-"):
            compatible.add("utf-32")
        if explicit not in compatible:
            raise XmlLexicalError(
                "explicit XML encoding conflicts with byte-order/BOM evidence"
            )
    try:
        text, representation = decode_text_source(source, encoding=hint)
    except (UnicodeError, LookupError, ValueError) as exc:
        raise XmlLexicalError(
            f"XML source encoding could not be decoded safely: {exc}"
        ) from exc

    lexical = scan_xml_text(text)
    declaration = lexical.declaration
    if declaration is not None and declaration.encoding is not None:
        if not _encoding_compatible(representation.encoding, declaration.encoding):
            raise XmlLexicalError(
                "XML declaration encoding conflicts with resolved source encoding"
            )
    try:
        if encode_text_source(text, representation) != source:
            raise XmlLexicalError(
                "XML source fails exact decode/encode authority proof"
            )
    except (UnicodeError, ValueError) as exc:
        raise XmlLexicalError(
            "XML source fails exact decode/encode authority proof"
        ) from exc
    return ParsedXmlSource(
        text=text,
        representation=representation,
        lexical=lexical,
    )
