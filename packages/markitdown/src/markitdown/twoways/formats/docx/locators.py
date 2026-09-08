from __future__ import annotations

from hashlib import sha256
from typing import Any

from ..._errors import AmbiguousNativeLocatorError
from ...ir.provenance import NativeLocator

_BACKEND = "docx-ooxml"


def paragraph_locator(
    part_uri: str, *, paragraph_index: int, path: str
) -> NativeLocator:
    return NativeLocator(
        backend=_BACKEND,
        part_uri=part_uri,
        object_id=f"paragraph:{paragraph_index}",
        path=path,
        attributes={"paragraph_index": paragraph_index},
    )


def picture_locator(
    part_uri: str,
    *,
    docpr_id: str | None,
    relationship_id: str | None,
    path: str,
) -> NativeLocator:
    if not docpr_id:
        raise ValueError("picture locator requires wp:docPr id")
    return NativeLocator(
        backend=_BACKEND,
        part_uri=part_uri,
        object_id=str(docpr_id),
        relationship_id=relationship_id,
        path=path,
        attributes={"native_kind": "picture", "docpr_id": str(docpr_id)},
    )


def stable_docx_node_id(locator: NativeLocator, kind: str) -> str:
    if locator.backend != _BACKEND or not locator.part_uri:
        raise ValueError("DOCX node locator requires docx-ooxml backend and part_uri")
    stable_key = locator.path or locator.object_id
    if not stable_key:
        raise ValueError("DOCX node locator requires stable path or object id")
    material = f"{locator.part_uri}\0{stable_key}\0{kind}".encode("utf-8")
    return f"docx-{kind}-{sha256(material).hexdigest()[:24]}"


def _validate_part(locator: NativeLocator, part_uri: str) -> None:
    if locator.backend != _BACKEND:
        raise AmbiguousNativeLocatorError(
            "Native locator backend does not match DOCX patcher.",
            details={"reason": "backend_mismatch", "backend": locator.backend},
        )
    if not locator.part_uri or locator.part_uri != part_uri:
        raise AmbiguousNativeLocatorError(
            "Native locator is not bound to the designated DOCX part.",
            details={
                "reason": "part_mismatch",
                "expected_part": locator.part_uri,
                "actual_part": part_uri,
            },
        )


def _root_container(root: Any) -> tuple[Any, str]:
    root_name = root.tag.rsplit("}", 1)[-1]
    if root_name == "document":
        bodies = root.xpath('./*[local-name()="body"]')
        if len(bodies) != 1:
            raise AmbiguousNativeLocatorError(
                "DOCX document root does not contain one body.",
                details={"reason": "native_structure_mismatch"},
            )
        return bodies[0], "/*[local-name()='document']/*[local-name()='body']"
    if root_name in {"hdr", "ftr"}:
        return root, f"/*[local-name()='{root_name}']"
    raise AmbiguousNativeLocatorError(
        "DOCX locator cannot resolve against this XML root.",
        details={"reason": "unsupported_root", "root": root_name},
    )


def _indexed_child(
    root: Any,
    locator: NativeLocator,
    *,
    child_name: str,
    index_attribute: str,
) -> Any:
    raw_index = locator.attributes.get(index_attribute)
    if not isinstance(raw_index, int) or raw_index < 0:
        raise AmbiguousNativeLocatorError(
            "DOCX structural locator requires a non-negative index.",
            details={"reason": "insufficient_identity", "field": index_attribute},
        )
    container, prefix = _root_container(root)
    candidates = [
        child for child in container if child.tag.rsplit("}", 1)[-1] == child_name
    ]
    if raw_index >= len(candidates):
        raise AmbiguousNativeLocatorError(
            "DOCX structural locator points beyond available native elements.",
            details={"reason": "not_found", "index": raw_index},
        )
    expected_path = (
        f"{prefix}/*[local-name()='{child_name}'][{raw_index + 1}]"
    )
    if locator.path != expected_path:
        raise AmbiguousNativeLocatorError(
            "DOCX structural locator path does not match its indexed identity.",
            details={
                "reason": "path_mismatch",
                "expected_path": expected_path,
                "actual_path": locator.path,
            },
        )
    return candidates[raw_index]


def resolve_paragraph_element(
    root: Any, locator: NativeLocator, *, part_uri: str
) -> Any:
    _validate_part(locator, part_uri)
    return _indexed_child(
        root,
        locator,
        child_name="p",
        index_attribute="paragraph_index",
    )


def resolve_table_element(root: Any, locator: NativeLocator, *, part_uri: str) -> Any:
    _validate_part(locator, part_uri)
    return _indexed_child(
        root,
        locator,
        child_name="tbl",
        index_attribute="table_index",
    )


def resolve_picture_docpr(root: Any, locator: NativeLocator, *, part_uri: str) -> Any:
    _validate_part(locator, part_uri)
    docpr_id = locator.attributes.get("docpr_id") or locator.object_id
    if not docpr_id:
        raise AmbiguousNativeLocatorError(
            "DOCX picture locator requires wp:docPr id.",
            details={"reason": "insufficient_identity"},
        )
    matches = root.xpath(f'.//*[local-name()="docPr" and @id="{docpr_id}"]')
    if len(matches) != 1:
        raise AmbiguousNativeLocatorError(
            "DOCX picture locator did not resolve uniquely.",
            details={"reason": "not_found" if not matches else "ambiguous"},
        )
    return matches[0]
