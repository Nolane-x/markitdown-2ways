from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import posixpath
from typing import Mapping
from urllib.parse import urlsplit
from zipfile import ZipFile

from ..._errors import OOXMLPackageError
from ...ooxml import parse_xml_part

_RELATIONSHIPS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_RELATIONSHIPS_TAG = f"{{{_RELATIONSHIPS_NS}}}Relationships"
_RELATIONSHIP_TAG = f"{{{_RELATIONSHIPS_NS}}}Relationship"


@dataclass(frozen=True)
class DocxRelationship:
    relationship_id: str
    relationship_type: str
    target: str
    target_mode: str | None = None
    resolved_target: str | None = None

    @property
    def external(self) -> bool:
        return (self.target_mode or "").lower() == "external"


def _rels_member_name(part_uri: str) -> str:
    normalized = part_uri.lstrip("/")
    directory, filename = posixpath.split(normalized)
    if not filename:
        raise ValueError("part_uri must identify a package member")
    return posixpath.join(directory, "_rels", f"{filename}.rels")


def resolve_relationship_target(part_uri: str, target: str) -> str:
    if not target or "\\" in target:
        raise ValueError("relationship target must be a safe relative package path")
    if urlsplit(target).scheme or target.startswith("/"):
        raise ValueError("internal relationship target must be relative")
    base_dir = posixpath.dirname(part_uri.lstrip("/"))
    resolved = posixpath.normpath(posixpath.join(base_dir, target))
    if resolved in {"", ".", ".."} or resolved.startswith("../"):
        raise ValueError("relationship target escapes the package root")
    return f"/{resolved}"


def relationships_for_part(
    source_bytes: bytes, part_uri: str
) -> Mapping[str, DocxRelationship]:
    rels_name = _rels_member_name(part_uri)
    with ZipFile(BytesIO(source_bytes), "r") as archive:
        try:
            data = archive.read(rels_name)
        except KeyError:
            return {}
    try:
        root = parse_xml_part(data)
    except SyntaxError as exc:
        raise OOXMLPackageError(
            "DOCX relationship part contains malformed XML.",
            details={
                "reason": "malformed_relationship_part",
                "part_uri": part_uri,
                "relationship_part": rels_name,
            },
        ) from exc
    if root.tag != _RELATIONSHIPS_TAG:
        raise OOXMLPackageError(
            "DOCX relationship part uses an invalid namespace.",
            details={
                "reason": "malformed_relationship_part",
                "part_uri": part_uri,
                "relationship_part": rels_name,
            },
        )
    result: dict[str, DocxRelationship] = {}
    for element in root:
        if not isinstance(element.tag, str):
            continue
        if element.tag != _RELATIONSHIP_TAG:
            raise OOXMLPackageError(
                "DOCX relationship part contains an unexpected element.",
                details={
                    "reason": "malformed_relationship_part",
                    "part_uri": part_uri,
                    "relationship_part": rels_name,
                    "element": element.tag,
                },
            )
        for attribute in ("Id", "Type", "Target"):
            if not element.get(attribute):
                raise OOXMLPackageError(
                    "DOCX relationship is missing a required attribute.",
                    details={
                        "reason": "malformed_relationship",
                        "attribute": attribute,
                        "part_uri": part_uri,
                        "relationship_part": rels_name,
                    },
                )
        relationship_id = element.get("Id")
        relationship_type = element.get("Type")
        target = element.get("Target")
        target_mode = element.get("TargetMode")
        if target_mode not in {None, "Internal", "External"}:
            raise OOXMLPackageError(
                "DOCX relationship has an invalid TargetMode.",
                details={
                    "reason": "malformed_relationship",
                    "attribute": "TargetMode",
                    "value": target_mode,
                    "part_uri": part_uri,
                    "relationship_part": rels_name,
                },
            )
        if relationship_id in result:
            raise OOXMLPackageError(
                "DOCX relationship part contains duplicate relationship IDs.",
                details={
                    "reason": "duplicate_relationship_id",
                    "relationship_id": relationship_id,
                    "part_uri": part_uri,
                    "relationship_part": rels_name,
                },
            )
        external = target_mode == "External"
        resolved_target = (
            None if external else resolve_relationship_target(part_uri, target)
        )
        result[relationship_id] = DocxRelationship(
            relationship_id=relationship_id,
            relationship_type=relationship_type,
            target=target,
            target_mode=target_mode,
            resolved_target=resolved_target,
        )
    return result
