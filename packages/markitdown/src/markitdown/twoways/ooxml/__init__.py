from io import BytesIO
from zipfile import ZipFile

from .._errors import OOXMLPackageError
from .limits import OOXMLPackageLimits
from .package import (
    OOXMLPackageEntry,
    OOXMLPackageSnapshot,
    snapshot_package as _snapshot_package,
    write_package,
)
from .xml import parse_xml_part, serialize_xml_part


_RELATIONSHIPS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_RELATIONSHIPS_TAG = f"{{{_RELATIONSHIPS_NS}}}Relationships"
_RELATIONSHIP_TAG = f"{{{_RELATIONSHIPS_NS}}}Relationship"


def _validate_relationship_ids(source_bytes: bytes) -> None:
    with ZipFile(BytesIO(source_bytes), "r") as archive:
        for info in archive.infolist():
            if not info.filename.lower().endswith(".rels"):
                continue
            try:
                root = parse_xml_part(archive.read(info))
            except SyntaxError as exc:
                raise OOXMLPackageError(
                    "OOXML relationship part contains malformed XML.",
                    details={
                        "reason": "malformed_relationship_part",
                        "relationship_part": info.filename,
                    },
                ) from exc
            if root.tag != _RELATIONSHIPS_TAG:
                raise OOXMLPackageError(
                    "OOXML relationship part uses an invalid namespace.",
                    details={
                        "reason": "malformed_relationship_part",
                        "relationship_part": info.filename,
                    },
                )
            seen: set[str] = set()
            for element in root:
                if element.tag.rsplit("}", 1)[-1] != "Relationship":
                    continue
                if element.tag != _RELATIONSHIP_TAG:
                    raise OOXMLPackageError(
                        "OOXML relationship uses an invalid namespace.",
                        details={
                            "reason": "malformed_relationship_part",
                            "relationship_part": info.filename,
                        },
                    )
                for attribute in ("Id", "Type", "Target"):
                    if not element.get(attribute):
                        raise OOXMLPackageError(
                            "OOXML relationship is missing a required attribute.",
                            details={
                                "reason": "malformed_relationship",
                                "attribute": attribute,
                                "relationship_part": info.filename,
                            },
                        )
                relationship_id = element.get("Id")
                if relationship_id in seen:
                    raise OOXMLPackageError(
                        "OOXML relationship part contains duplicate relationship IDs.",
                        details={
                            "reason": "duplicate_relationship_id",
                            "relationship_id": relationship_id,
                            "relationship_part": info.filename,
                        },
                    )
                seen.add(relationship_id)


def snapshot_package(
    source_bytes: bytes,
    *,
    limits: OOXMLPackageLimits | None = None,
) -> OOXMLPackageSnapshot:
    snapshot = _snapshot_package(source_bytes, limits=limits)
    _validate_relationship_ids(source_bytes)
    return snapshot


__all__ = [
    "OOXMLPackageEntry",
    "OOXMLPackageLimits",
    "OOXMLPackageSnapshot",
    "parse_xml_part",
    "serialize_xml_part",
    "snapshot_package",
    "write_package",
]
