from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import posixpath
from typing import Mapping
from zipfile import ZipFile

from ...ooxml import parse_xml_part


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
    if "://" in target or target.startswith("/"):
        raise ValueError("internal relationship target must be relative")
    base_dir = posixpath.dirname(part_uri.lstrip("/"))
    resolved = posixpath.normpath(posixpath.join(base_dir, target))
    if resolved in {"", ".", ".."} or resolved.startswith("../"):
        raise ValueError("relationship target escapes the package root")
    return f"/{resolved}"


def relationships_for_part(source_bytes: bytes, part_uri: str) -> Mapping[str, DocxRelationship]:
    rels_name = _rels_member_name(part_uri)
    with ZipFile(BytesIO(source_bytes), "r") as archive:
        try:
            data = archive.read(rels_name)
        except KeyError:
            return {}
    root = parse_xml_part(data)
    result: dict[str, DocxRelationship] = {}
    for element in root:
        if element.tag.rsplit("}", 1)[-1] != "Relationship":
            continue
        relationship_id = element.get("Id")
        relationship_type = element.get("Type")
        target = element.get("Target")
        if not relationship_id or not relationship_type or target is None:
            continue
        target_mode = element.get("TargetMode")
        external = (target_mode or "").lower() == "external"
        resolved_target = None if external else resolve_relationship_target(part_uri, target)
        result[relationship_id] = DocxRelationship(
            relationship_id=relationship_id,
            relationship_type=relationship_type,
            target=target,
            target_mode=target_mode,
            resolved_target=resolved_target,
        )
    return result
