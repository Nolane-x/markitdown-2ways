from __future__ import annotations

from hashlib import sha256
from typing import Any

from ...ir.provenance import NativeLocator

_CREATION_ID_LOCAL_NAME = "creationId"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def find_creation_id(element: Any) -> str | None:
    for descendant in element.iter():
        if _local_name(descendant.tag) == _CREATION_ID_LOCAL_NAME:
            value = descendant.get("id")
            if value:
                return value
    return None


def shape_locator(shape: Any, *, part_uri: str, z_order: int) -> NativeLocator:
    creation_id = find_creation_id(shape._element)
    return NativeLocator(
        backend="pptx-ooxml",
        part_uri=part_uri,
        object_id=str(shape.shape_id),
        creation_id=creation_id,
        name=shape.name,
        path=f"/p:sld/p:cSld/p:spTree/*[{z_order + 1}]",
        attributes={
            "z_order": z_order,
            "shape_type": str(shape.shape_type),
        },
    )


def slide_locator(slide: Any, *, index: int, relationship_id: str | None) -> NativeLocator:
    return NativeLocator(
        backend="pptx-ooxml",
        part_uri=str(slide.part.partname),
        creation_id=find_creation_id(slide._element),
        relationship_id=relationship_id,
        attributes={"slide_index": index},
    )


def stable_node_id(locator: NativeLocator, kind: str) -> str:
    if not locator.part_uri:
        raise ValueError("PPTX node locator requires part_uri")
    stable_object_key = locator.creation_id or locator.object_id
    if not stable_object_key:
        raise ValueError("PPTX node locator requires creation_id or object_id")
    material = f"{locator.part_uri}\0{stable_object_key}\0{kind}".encode("utf-8")
    return f"pptx-{kind}-{sha256(material).hexdigest()[:24]}"


def stable_run_id(
    locator: NativeLocator,
    *,
    paragraph_index: int,
    run_index: int,
) -> NativeLocator:
    return NativeLocator(
        backend=locator.backend,
        part_uri=locator.part_uri,
        object_id=locator.object_id,
        creation_id=locator.creation_id,
        name=locator.name,
        path=(
            f"{locator.path or ''}/text/p[{paragraph_index + 1}]/r[{run_index + 1}]"
        ),
        attributes={
            "paragraph_index": paragraph_index,
            "run_index": run_index,
        },
    )


def _shape_container_for_cnvpr(cnvpr: Any) -> Any | None:
    current = cnvpr.getparent()
    shape_names = {"sp", "pic", "graphicFrame", "grpSp", "cxnSp", "contentPart"}
    while current is not None:
        if _local_name(current.tag) in shape_names:
            return current
        current = current.getparent()
    return None


def _shape_identity_records(slide_root: Any) -> list[tuple[Any, Any, str | None, str | None]]:
    records: list[tuple[Any, Any, str | None, str | None]] = []
    for element in slide_root.iter():
        if _local_name(element.tag) != "cNvPr":
            continue
        shape = _shape_container_for_cnvpr(element)
        if shape is None:
            continue
        records.append((shape, element, element.get("id"), find_creation_id(element)))
    return records


def resolve_shape_element(
    slide_root: Any,
    locator: NativeLocator,
    *,
    part_uri: str,
    strict: bool = True,
) -> Any:
    from ..._errors import AmbiguousNativeLocatorError

    if locator.backend != "pptx-ooxml":
        raise AmbiguousNativeLocatorError(
            "Native locator backend does not match PPTX patcher.",
            details={"reason": "backend_mismatch", "backend": locator.backend},
        )
    if not locator.part_uri or locator.part_uri != part_uri:
        raise AmbiguousNativeLocatorError(
            "Native locator is not bound to the designated slide part.",
            details={
                "reason": "part_mismatch",
                "expected_part": locator.part_uri,
                "actual_part": part_uri,
            },
        )
    if not locator.creation_id and not locator.object_id:
        raise AmbiguousNativeLocatorError(
            "Strict PPTX patching requires creation_id or object_id.",
            details={"reason": "insufficient_identity", "name": locator.name},
        )

    records = _shape_identity_records(slide_root)
    object_matches = [record for record in records if locator.object_id and record[2] == locator.object_id]
    creation_matches = [
        record for record in records if locator.creation_id and record[3] == locator.creation_id
    ]

    if locator.object_id and locator.creation_id:
        if len(object_matches) == 1 and len(creation_matches) == 1:
            if object_matches[0][0] is not creation_matches[0][0]:
                raise AmbiguousNativeLocatorError(
                    "PPTX creation_id and object_id identify different shapes.",
                    details={"reason": "identity_mismatch"},
                )
            return object_matches[0][0]
        intersection = [record for record in object_matches if record in creation_matches]
        if len(intersection) == 1:
            return intersection[0][0]
        reason = "not_found" if not intersection else "ambiguous"
        raise AmbiguousNativeLocatorError(
            "PPTX shape locator did not resolve uniquely.",
            details={"reason": reason},
        )

    matches = creation_matches if locator.creation_id else object_matches
    if len(matches) != 1:
        reason = "not_found" if not matches else "ambiguous"
        raise AmbiguousNativeLocatorError(
            "PPTX shape locator did not resolve uniquely.",
            details={"reason": reason},
        )
    return matches[0][0]
