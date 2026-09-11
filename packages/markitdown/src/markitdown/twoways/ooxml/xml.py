from __future__ import annotations

from typing import Any


def parse_xml_part(data: bytes) -> Any:
    from lxml import etree

    parser = etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        huge_tree=False,
        remove_blank_text=False,
    )
    return etree.fromstring(data, parser=parser)


def serialize_xml_part(root: Any) -> bytes:
    from lxml import etree

    return etree.tostring(
        root,
        encoding="UTF-8",
        xml_declaration=True,
        standalone=None,
    )
