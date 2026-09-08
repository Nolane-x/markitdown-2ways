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


def _validate_relationship_ids(source_bytes: bytes) -> None:
    with ZipFile(BytesIO(source_bytes), "r") as archive:
        for info in archive.infolist():
            if not info.filename.lower().endswith(".rels"):
                continue
            root = parse_xml_part(archive.read(info))
            seen: set[str] = set()
            for element in root:
                if element.tag.rsplit("}", 1)[-1] != "Relationship":
                    continue
                relationship_id = element.get("Id")
                if not relationship_id:
                    continue
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
