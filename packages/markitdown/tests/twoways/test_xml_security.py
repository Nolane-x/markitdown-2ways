from __future__ import annotations

import codecs

import pytest

from markitdown.twoways.formats.xml.lexical import (
    XmlLexicalError,
    parse_xml_source,
)


@pytest.mark.parametrize(
    "source",
    [
        b'<!DOCTYPE r [<!ENTITY x "boom">]><r>&x;</r>',
        b'<!DOCTYPE r SYSTEM "https://example.invalid/a.dtd"><r/>',
        b'<!DOCTYPE r [<!ENTITY % p SYSTEM "https://example.invalid/p.dtd">%p;]><r/>',
        b'<?xml version="1.1"?><r/>',
        b'<r xmlns:p="u"><p:x></r>',
        b'<r p:x="1"/>',
        b'<r a="1" a="2"/>',
        b'<r><a></r>',
    ],
)
def test_unsafe_or_malformed_xml_fails_closed(source: bytes) -> None:
    with pytest.raises(XmlLexicalError):
        parse_xml_source(source)


def test_utf8_declaration_and_bom_are_recorded_exactly() -> None:
    source = codecs.BOM_UTF8 + b'<?xml version="1.0" encoding="UTF-8"?><r>ok</r>'
    parsed = parse_xml_source(source)

    assert parsed.representation.encoding == "utf-8"
    assert parsed.representation.bom == "utf-8"
    assert parsed.declaration is not None
    assert parsed.declaration.version == "1.0"
    assert parsed.declaration.encoding == "UTF-8"
    assert parsed.declaration.raw == '<?xml version="1.0" encoding="UTF-8"?>'


def test_utf16_endianness_is_resolved_from_bom() -> None:
    text = '<?xml version="1.0" encoding="UTF-16"?><r>ok</r>'
    source = codecs.BOM_UTF16_LE + text.encode("utf-16-le")
    parsed = parse_xml_source(source)

    assert parsed.representation.encoding == "utf-16-le"
    assert parsed.representation.bom == "utf-16-le"
    assert parsed.declaration is not None
    assert parsed.declaration.encoding == "UTF-16"


def test_declaration_encoding_conflict_fails_closed() -> None:
    source = b'<?xml version="1.0" encoding="ISO-8859-1"?><r>ok</r>'

    with pytest.raises(XmlLexicalError, match="encoding"):
        parse_xml_source(source, encoding="utf-8")


def test_external_entity_text_is_not_treated_as_a_normal_reference() -> None:
    source = (
        b'<!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        b'<r>&x;</r>'
    )

    with pytest.raises(XmlLexicalError):
        parse_xml_source(source)


def test_processing_instruction_cannot_use_xml_target_outside_declaration() -> None:
    with pytest.raises(XmlLexicalError):
        parse_xml_source(b'<r><?xml bad?></r>')
