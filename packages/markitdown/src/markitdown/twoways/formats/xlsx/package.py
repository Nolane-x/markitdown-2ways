from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import posixpath
from urllib.parse import urlsplit
from zipfile import ZipFile

from ..._errors import OOXMLPackageError
from ...ooxml import parse_xml_part, snapshot_package
from .model import (
    CONTENT_TYPES_NS,
    OFFICE_REL_STRICT_NS,
    OFFICE_REL_TRANSITIONAL_NS,
    PACKAGE_REL_NS,
    SHARED_STRINGS_CONTENT_TYPE,
    SPREADSHEETML_STRICT_NS,
    SPREADSHEETML_TRANSITIONAL_NS,
    STYLES_CONTENT_TYPE,
    WORKBOOK_CONTENT_TYPE,
    WORKSHEET_CONTENT_TYPE,
    XlsxPackageParts,
    XlsxWorksheetPart,
)


@dataclass(frozen=True)
class _Relationship:
    relationship_id: str
    relationship_type: str
    target: str
    target_mode: str | None
    resolved_target: str | None

    @property
    def external(self) -> bool:
        return self.target_mode == "External"


def _fail(reason: str, message: str, **details: object) -> None:
    raise OOXMLPackageError(message, details={"reason": reason, **details})


def _local_name(tag: object) -> str | None:
    if not isinstance(tag, str):
        return None
    return tag.rsplit("}", 1)[-1]


def _read_members(source_bytes: bytes) -> dict[str, bytes]:
    with ZipFile(BytesIO(source_bytes), "r") as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def _relationship_part_name(part_uri: str) -> str:
    normalized = part_uri.lstrip("/")
    directory, filename = posixpath.split(normalized)
    if not filename:
        raise ValueError("part_uri must identify a package member")
    return posixpath.join(directory, "_rels", f"{filename}.rels")


def _resolve_target(part_uri: str, target: str) -> str:
    if not target or "\\" in target or target.startswith("/") or urlsplit(target).scheme:
        raise ValueError("internal relationship target must be a safe relative path")
    base_dir = posixpath.dirname(part_uri.lstrip("/"))
    resolved = posixpath.normpath(posixpath.join(base_dir, target))
    if resolved in {"", ".", ".."} or resolved.startswith("../"):
        raise ValueError("relationship target escapes the package root")
    return f"/{resolved}"


def _parse_relationships(data: bytes, *, source_part_uri: str) -> tuple[_Relationship, ...]:
    root = parse_xml_part(data)
    expected_root = f"{{{PACKAGE_REL_NS}}}Relationships"
    expected_child = f"{{{PACKAGE_REL_NS}}}Relationship"
    if root.tag != expected_root:
        _fail(
            "malformed_relationship_part",
            "XLSX relationship part uses an invalid namespace.",
            part_uri=source_part_uri,
        )
    result: list[_Relationship] = []
    seen: set[str] = set()
    for element in root:
        if not isinstance(element.tag, str):
            continue
        if element.tag != expected_child:
            _fail(
                "malformed_relationship_part",
                "XLSX relationship part contains an unexpected element.",
                part_uri=source_part_uri,
            )
        relationship_id = element.get("Id")
        relationship_type = element.get("Type")
        target = element.get("Target")
        target_mode = element.get("TargetMode")
        if not relationship_id or not relationship_type or not target:
            _fail(
                "malformed_relationship",
                "XLSX relationship is missing a required attribute.",
                part_uri=source_part_uri,
            )
        if relationship_id in seen:
            _fail(
                "duplicate_relationship_id",
                "XLSX relationship part contains duplicate relationship IDs.",
                relationship_id=relationship_id,
                part_uri=source_part_uri,
            )
        seen.add(relationship_id)
        if target_mode not in {None, "Internal", "External"}:
            _fail(
                "malformed_relationship",
                "XLSX relationship has an invalid TargetMode.",
                relationship_id=relationship_id,
            )
        resolved = None if target_mode == "External" else _resolve_target(source_part_uri, target)
        result.append(
            _Relationship(
                relationship_id=relationship_id,
                relationship_type=relationship_type,
                target=target,
                target_mode=target_mode,
                resolved_target=resolved,
            )
        )
    return tuple(result)


def _content_type_overrides(data: bytes) -> dict[str, str]:
    root = parse_xml_part(data)
    if root.tag != f"{{{CONTENT_TYPES_NS}}}Types":
        _fail(
            "malformed_content_types",
            "XLSX Content Types part uses an invalid namespace.",
        )
    overrides: dict[str, str] = {}
    for element in root:
        if not isinstance(element.tag, str):
            continue
        if _local_name(element.tag) != "Override":
            continue
        if element.tag != f"{{{CONTENT_TYPES_NS}}}Override":
            _fail(
                "malformed_content_types",
                "XLSX Content Types contains a foreign Override element.",
            )
        part_name = element.get("PartName")
        content_type = element.get("ContentType")
        if not part_name or not content_type or not part_name.startswith("/") or part_name.startswith("//"):
            _fail(
                "malformed_content_types",
                "XLSX Content Types contains an invalid Override.",
            )
        previous = overrides.get(part_name)
        if previous is not None and previous != content_type:
            _fail(
                "conflicting_content_type",
                "XLSX Content Types contains conflicting Overrides.",
                part_uri=part_name,
            )
        overrides[part_name] = content_type
    return overrides


def _namespace_authority(root: object, *, expected_local: str) -> str:
    tag = getattr(root, "tag", None)
    if not isinstance(tag, str) or not tag.startswith("{") or "}" not in tag:
        _fail(
            "invalid_spreadsheet_namespace",
            "XLSX SpreadsheetML root namespace is invalid.",
        )
    namespace, local = tag[1:].split("}", 1)
    if local != expected_local or namespace not in {
        SPREADSHEETML_TRANSITIONAL_NS,
        SPREADSHEETML_STRICT_NS,
    }:
        _fail(
            "invalid_spreadsheet_namespace",
            "XLSX SpreadsheetML root namespace is invalid.",
        )
    return namespace


def _office_relationship_namespace(spreadsheet_namespace: str) -> str:
    if spreadsheet_namespace == SPREADSHEETML_TRANSITIONAL_NS:
        return OFFICE_REL_TRANSITIONAL_NS
    return OFFICE_REL_STRICT_NS


def _relationship_base(spreadsheet_namespace: str) -> str:
    return _office_relationship_namespace(spreadsheet_namespace)


def _require_part_type(
    overrides: dict[str, str],
    part_uri: str,
    expected: str,
    *,
    reason: str,
) -> None:
    if overrides.get(part_uri) != expected:
        _fail(
            reason,
            "XLSX package part does not have the required content type.",
            part_uri=part_uri,
            expected=expected,
            actual=overrides.get(part_uri),
        )


def discover_xlsx_parts(source_bytes: bytes) -> XlsxPackageParts:
    snapshot_package(source_bytes)
    members = _read_members(source_bytes)
    content_types_data = members.get("[Content_Types].xml")
    root_rels_data = members.get("_rels/.rels")
    if content_types_data is None or root_rels_data is None:
        _fail(
            "missing_package_authority",
            "XLSX package is missing Content Types or root relationships.",
        )
    overrides = _content_type_overrides(content_types_data)
    root_relationships = _parse_relationships(root_rels_data, source_part_uri="/")
    office_types = {
        f"{OFFICE_REL_TRANSITIONAL_NS}/officeDocument",
        f"{OFFICE_REL_STRICT_NS}/officeDocument",
    }
    workbook_candidates = [
        relationship
        for relationship in root_relationships
        if relationship.relationship_type in office_types
    ]
    if len(workbook_candidates) != 1:
        _fail(
            "ambiguous_workbook_part",
            "XLSX package must expose exactly one officeDocument relationship.",
            count=len(workbook_candidates),
        )
    workbook_relationship = workbook_candidates[0]
    if workbook_relationship.external or workbook_relationship.resolved_target is None:
        _fail(
            "external_workbook_target",
            "XLSX workbook relationship must be internal.",
        )
    workbook_part = workbook_relationship.resolved_target
    if workbook_part.lstrip("/") not in members:
        _fail(
            "missing_workbook_part",
            "XLSX workbook relationship targets a missing part.",
            part_uri=workbook_part,
        )
    _require_part_type(
        overrides,
        workbook_part,
        WORKBOOK_CONTENT_TYPE,
        reason="wrong_workbook_content_type",
    )

    workbook_root = parse_xml_part(members[workbook_part.lstrip("/")])
    spreadsheet_namespace = _namespace_authority(workbook_root, expected_local="workbook")
    expected_rel_base = _relationship_base(spreadsheet_namespace)
    if workbook_relationship.relationship_type != f"{expected_rel_base}/officeDocument":
        _fail(
            "relationship_namespace_mismatch",
            "XLSX workbook relationship family does not match SpreadsheetML authority.",
        )

    sheets_elements = []
    for child in workbook_root:
        if not isinstance(child.tag, str):
            continue
        if _local_name(child.tag) == "sheets":
            if child.tag != f"{{{spreadsheet_namespace}}}sheets":
                _fail(
                    "mixed_spreadsheet_namespace",
                    "XLSX workbook mixes SpreadsheetML namespaces.",
                )
            sheets_elements.append(child)
    if len(sheets_elements) != 1:
        _fail(
            "ambiguous_sheets_container",
            "XLSX workbook must contain exactly one sheets container.",
            count=len(sheets_elements),
        )

    workbook_rels_name = _relationship_part_name(workbook_part)
    workbook_rels_data = members.get(workbook_rels_name)
    if workbook_rels_data is None:
        _fail(
            "missing_workbook_relationships",
            "XLSX workbook relationships part is missing.",
        )
    workbook_relationships = {
        relationship.relationship_id: relationship
        for relationship in _parse_relationships(
            workbook_rels_data,
            source_part_uri=workbook_part,
        )
    }

    worksheet_type = f"{expected_rel_base}/worksheet"
    relationship_attribute = f"{{{_office_relationship_namespace(spreadsheet_namespace)}}}id"
    worksheets: list[XlsxWorksheetPart] = []
    sheet_names: set[str] = set()
    for element in sheets_elements[0]:
        if not isinstance(element.tag, str):
            continue
        if _local_name(element.tag) != "sheet":
            continue
        if element.tag != f"{{{spreadsheet_namespace}}}sheet":
            _fail(
                "mixed_spreadsheet_namespace",
                "XLSX workbook mixes SpreadsheetML namespaces.",
            )
        name = element.get("name")
        relationship_id = element.get(relationship_attribute)
        raw_sheet_id = element.get("sheetId")
        if not name or not relationship_id or not raw_sheet_id:
            _fail(
                "malformed_sheet",
                "XLSX sheet declaration is missing required attributes.",
            )
        try:
            sheet_id = int(raw_sheet_id)
        except ValueError as exc:
            raise OOXMLPackageError(
                "XLSX sheetId must be an integer.",
                details={"reason": "malformed_sheet", "sheet_id": raw_sheet_id},
            ) from exc
        if sheet_id <= 0 or name in sheet_names:
            _fail(
                "malformed_sheet",
                "XLSX sheet identifiers and names must be unique and valid.",
                sheet_name=name,
            )
        sheet_names.add(name)
        relationship = workbook_relationships.get(relationship_id)
        if relationship is None or relationship.relationship_type != worksheet_type:
            _fail(
                "wrong_worksheet_relationship",
                "XLSX sheet does not resolve through an authoritative worksheet relationship.",
                relationship_id=relationship_id,
            )
        if relationship.external or relationship.resolved_target is None:
            _fail(
                "external_worksheet_target",
                "XLSX worksheet relationship must be internal.",
                relationship_id=relationship_id,
            )
        part_uri = relationship.resolved_target
        if part_uri.lstrip("/") not in members:
            _fail(
                "missing_worksheet_part",
                "XLSX worksheet relationship targets a missing part.",
                part_uri=part_uri,
            )
        _require_part_type(
            overrides,
            part_uri,
            WORKSHEET_CONTENT_TYPE,
            reason="wrong_worksheet_content_type",
        )
        worksheets.append(
            XlsxWorksheetPart(
                name=name,
                sheet_id=sheet_id,
                relationship_id=relationship_id,
                part_uri=part_uri,
            )
        )

    def optional_part(suffix: str, content_type: str) -> str | None:
        relationship_type = f"{expected_rel_base}/{suffix}"
        candidates = [
            relationship
            for relationship in workbook_relationships.values()
            if relationship.relationship_type == relationship_type
        ]
        if len(candidates) > 1:
            _fail(
                "ambiguous_optional_part",
                "XLSX workbook exposes duplicate optional part relationships.",
                relationship_type=relationship_type,
            )
        if not candidates:
            return None
        relationship = candidates[0]
        if relationship.external or relationship.resolved_target is None:
            _fail(
                "external_optional_part",
                "XLSX optional workbook part must be internal.",
                relationship_type=relationship_type,
            )
        part_uri = relationship.resolved_target
        if part_uri.lstrip("/") not in members:
            _fail(
                "missing_optional_part",
                "XLSX optional workbook relationship targets a missing part.",
                part_uri=part_uri,
            )
        _require_part_type(
            overrides,
            part_uri,
            content_type,
            reason="wrong_optional_part_content_type",
        )
        return part_uri

    return XlsxPackageParts(
        workbook_part=workbook_part,
        spreadsheet_namespace=spreadsheet_namespace,
        worksheets=tuple(worksheets),
        shared_strings_part=optional_part("sharedStrings", SHARED_STRINGS_CONTENT_TYPE),
        styles_part=optional_part("styles", STYLES_CONTENT_TYPE),
    )
