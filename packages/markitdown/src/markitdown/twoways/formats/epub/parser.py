from __future__ import annotations

from collections.abc import Mapping
from io import BytesIO
import posixpath
import re
from urllib.parse import unquote, urlsplit
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree as DefusedElementTree
from defusedxml.common import DefusedXmlException

from ...capabilities import CapabilityState, capabilities_for_node
from ...ir.document import DocumentIR
from ...ir.nodes import Node
from ..xml.reader import read_xml_ir
from .limits import EpubPackageLimits
from .model import (
    EpubManifestItemEvidence,
    EpubMetadataOwnerEvidence,
    EpubParseError,
    EpubRootfileEvidence,
    EpubSpineItemEvidence,
    EpubXhtmlTextEvidence,
    ParsedEpubSource,
)
from .package import read_epub_member, snapshot_epub_package, validate_member_name


_CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
_OPF_NS = "http://www.idpf.org/2007/opf"
_DC_NS = "http://purl.org/dc/elements/1.1/"
_XHTML_NS = "http://www.w3.org/1999/xhtml"
_SVG_NS = "http://www.w3.org/2000/svg"
_MATHML_NS = "http://www.w3.org/1998/Math/MathML"
_PACKAGE_MIMETYPE = "application/oebps-package+xml"
_XHTML_MIMETYPE = "application/xhtml+xml"
_SELECTED_METADATA = frozenset(
    {
        "title",
        "creator",
        "language",
        "publisher",
        "date",
        "description",
        "subject",
    }
)
_EXCLUDED_XHTML_ANCESTORS = frozenset({"script", "style", "template"})
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def _fail(reason: str, message: str, **details: object) -> None:
    raise EpubParseError(message, reason=reason, details=details)


def _expanded(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


def _split_expanded(name: object) -> tuple[str, str] | None:
    if not isinstance(name, str) or not name:
        return None
    if name.startswith("{") and "}" in name:
        namespace, local = name[1:].split("}", 1)
        return namespace, local
    return "", name


def _xml_authority(
    data: bytes,
    *,
    member_name: str,
    mimetype: str,
) -> tuple[DocumentIR, object]:
    try:
        document = read_xml_ir(
            BytesIO(data),
            filename=member_name,
            mimetype=mimetype,
        )
        root = DefusedElementTree.fromstring(data)
    except (DefusedXmlException, ParseError, TypeError, ValueError) as exc:
        raise EpubParseError(
            "EPUB XML member is not safe strict XML.",
            reason="epub.xml.invalid",
            details={"member": member_name},
        ) from exc
    return document, root


def _normalize_rootfile_path(value: str) -> str:
    decoded = unquote(value)
    if (
        not decoded
        or "\\" in decoded
        or decoded.startswith("/")
        or _DRIVE_RE.match(decoded)
    ):
        _fail(
            "epub.container.unsafe_rootfile",
            "EPUB rootfile path is unsafe.",
            path=value,
        )
    parts = decoded.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        _fail(
            "epub.container.unsafe_rootfile",
            "EPUB rootfile path is unsafe.",
            path=value,
        )
    validate_member_name(decoded)
    return decoded


def _resolve_href(package_path: str, href: str) -> tuple[str | None, bool]:
    split = urlsplit(href)
    if split.scheme or split.netloc:
        return None, True
    if split.query:
        _fail(
            "epub.manifest.local_query",
            "Local EPUB manifest hrefs with query components are unsupported.",
            href=href,
        )
    decoded = unquote(split.path)
    if (
        not decoded
        or "\\" in decoded
        or decoded.startswith("/")
        or _DRIVE_RE.match(decoded)
    ):
        _fail(
            "epub.manifest.unsafe_href",
            "EPUB manifest href is unsafe.",
            href=href,
        )
    if any(part in {"", ".", ".."} for part in decoded.split("/")):
        _fail(
            "epub.manifest.unsafe_href",
            "EPUB manifest href is unsafe.",
            href=href,
        )
    resolved = posixpath.normpath(
        posixpath.join(posixpath.dirname(package_path), decoded)
    )
    validate_member_name(resolved)
    return resolved, False


def _direct_child(root: object, namespace: str, local: str) -> object | None:
    for child in list(root):
        if getattr(child, "tag", None) == _expanded(namespace, local):
            return child
    return None


def _node_text_value(node: Node) -> str | None:
    payload = node.payload
    if not isinstance(payload, Mapping):
        return None
    if payload.get("xml_type") != "text":
        return None
    value = payload.get("value")
    return value if isinstance(value, str) else None


def _writable_xml_text_nodes(document: DocumentIR) -> tuple[Node, ...]:
    result: list[Node] = []
    for node in document.nodes.values():
        if node.metadata.get("xml.kind") != "text":
            continue
        capability = capabilities_for_node(node).for_operation("replace_xml_text")
        if capability.state is CapabilityState.WRITABLE:
            result.append(node)
    result.sort(key=lambda item: item.order)
    return tuple(result)


def _ancestor_elements(document: DocumentIR, node: Node) -> tuple[Node, ...]:
    result: list[Node] = []
    current = node
    seen: set[str] = set()
    while current.parent_id is not None:
        if current.parent_id in seen:
            _fail(
                "epub.xml.parent_cycle",
                "EPUB XML ownership contains a parent cycle.",
                node_id=node.node_id,
            )
        seen.add(current.parent_id)
        parent = document.nodes.get(current.parent_id)
        if parent is None:
            _fail(
                "epub.xml.missing_parent",
                "EPUB XML ownership parent is missing.",
                node_id=node.node_id,
            )
        if parent.metadata.get("xml.kind") == "element":
            result.append(parent)
        current = parent
    return tuple(result)


def _metadata_owners(
    document: DocumentIR,
    *,
    member_path: str,
    member_sha256: str,
) -> tuple[EpubMetadataOwnerEvidence, ...]:
    owners: list[EpubMetadataOwnerEvidence] = []
    for node in _writable_xml_text_nodes(document):
        ancestors = _ancestor_elements(document, node)
        if not ancestors:
            continue
        direct = _split_expanded(ancestors[0].metadata.get("xml.expanded_name"))
        if direct is None or direct[0] != _DC_NS or direct[1] not in _SELECTED_METADATA:
            continue
        if not any(
            ancestor.metadata.get("xml.expanded_name") == _expanded(_OPF_NS, "metadata")
            for ancestor in ancestors[1:]
        ):
            continue
        value = _node_text_value(node)
        xml_path = node.metadata.get("xml.path")
        raw_digest = node.metadata.get("xml.raw_digest")
        if (
            value is None
            or not isinstance(xml_path, str)
            or not isinstance(raw_digest, str)
        ):
            continue
        owners.append(
            EpubMetadataOwnerEvidence(
                name=direct[1],
                value=value,
                member_path=member_path,
                member_sha256=member_sha256,
                xml_path=xml_path,
                raw_digest=raw_digest,
            )
        )
    return tuple(owners)


def _xhtml_owner_is_allowed(document: DocumentIR, node: Node) -> bool:
    in_body = False
    for ancestor in _ancestor_elements(document, node):
        expanded_name = _split_expanded(ancestor.metadata.get("xml.expanded_name"))
        if expanded_name is None:
            continue
        namespace, local = expanded_name
        if namespace in {_SVG_NS, _MATHML_NS}:
            return False
        if namespace == _XHTML_NS and local in _EXCLUDED_XHTML_ANCESTORS:
            return False
        if namespace == _XHTML_NS and local == "body":
            in_body = True
    return in_body


def _xhtml_owners(
    source: bytes,
    parsed_manifest: tuple[EpubManifestItemEvidence, ...],
    package_entries: Mapping[str, object],
) -> tuple[EpubXhtmlTextEvidence, ...]:
    owners: list[EpubXhtmlTextEvidence] = []
    for item in parsed_manifest:
        if (
            item.media_type != _XHTML_MIMETYPE
            or item.is_remote
            or item.resolved_path is None
            or item.is_navigation
        ):
            continue
        member_path = item.resolved_path
        member_entry = package_entries[member_path]
        try:
            member_bytes = read_epub_member(source, member_path)
            document, _ = _xml_authority(
                member_bytes,
                member_name=member_path,
                mimetype=_XHTML_MIMETYPE,
            )
        except EpubParseError:
            continue
        member_sha256 = getattr(member_entry, "uncompressed_sha256")
        for node in _writable_xml_text_nodes(document):
            if not _xhtml_owner_is_allowed(document, node):
                continue
            value = _node_text_value(node)
            xml_path = node.metadata.get("xml.path")
            raw_digest = node.metadata.get("xml.raw_digest")
            if (
                value is None
                or not isinstance(xml_path, str)
                or not isinstance(raw_digest, str)
            ):
                continue
            owners.append(
                EpubXhtmlTextEvidence(
                    value=value,
                    member_path=member_path,
                    member_sha256=member_sha256,
                    manifest_item_id=item.item_id,
                    xml_path=xml_path,
                    raw_digest=raw_digest,
                )
            )
    return tuple(owners)


def parse_epub_source(
    source: bytes,
    *,
    limits: EpubPackageLimits | None = None,
) -> ParsedEpubSource:
    package = snapshot_epub_package(source, limits=limits)
    entries = package.entry_by_name
    if "META-INF/container.xml" not in entries:
        _fail(
            "epub.container.missing",
            "EPUB package is missing META-INF/container.xml.",
        )

    container_bytes = read_epub_member(source, "META-INF/container.xml")
    _, container_root = _xml_authority(
        container_bytes,
        member_name="META-INF/container.xml",
        mimetype="application/xml",
    )
    if getattr(container_root, "tag", None) != _expanded(_CONTAINER_NS, "container"):
        _fail(
            "epub.container.root",
            "EPUB container.xml has an invalid document element.",
        )

    rootfiles: list[EpubRootfileEvidence] = []
    for element in container_root.iter():
        if getattr(element, "tag", None) != _expanded(_CONTAINER_NS, "rootfile"):
            continue
        full_path = element.attrib.get("full-path")
        if not isinstance(full_path, str) or not full_path:
            _fail(
                "epub.container.rootfile_path",
                "EPUB rootfile is missing full-path.",
            )
        rootfiles.append(
            EpubRootfileEvidence(
                path=_normalize_rootfile_path(full_path),
                media_type=element.attrib.get("media-type"),
            )
        )
    if not rootfiles:
        _fail(
            "epub.container.no_rootfiles",
            "EPUB container.xml declares no package document.",
        )

    package_path = rootfiles[0].path
    if package_path not in entries:
        _fail(
            "epub.container.package_missing",
            "EPUB package document is missing from the archive.",
            package_path=package_path,
        )
    package_bytes = read_epub_member(source, package_path)
    package_document, package_root = _xml_authority(
        package_bytes,
        member_name=package_path,
        mimetype=_PACKAGE_MIMETYPE,
    )
    if getattr(package_root, "tag", None) != _expanded(_OPF_NS, "package"):
        _fail(
            "epub.package.root",
            "EPUB package document has an invalid document element.",
        )

    package_version = package_root.attrib.get("version")
    metadata_element = _direct_child(package_root, _OPF_NS, "metadata")
    manifest_element = _direct_child(package_root, _OPF_NS, "manifest")
    spine_element = _direct_child(package_root, _OPF_NS, "spine")
    if metadata_element is None or manifest_element is None or spine_element is None:
        _fail(
            "epub.package.structure",
            "EPUB package document requires metadata, manifest, and spine.",
        )

    manifest: list[EpubManifestItemEvidence] = []
    by_id: dict[str, EpubManifestItemEvidence] = {}
    local_owners: dict[str, str] = {}
    for element in list(manifest_element):
        if getattr(element, "tag", None) != _expanded(_OPF_NS, "item"):
            continue
        item_id = element.attrib.get("id")
        href = element.attrib.get("href")
        media_type = element.attrib.get("media-type")
        if not item_id or not href or not media_type:
            _fail(
                "epub.manifest.item_fields",
                "EPUB manifest item is missing id, href, or media-type.",
            )
        if item_id in by_id:
            _fail(
                "epub.manifest.duplicate_id",
                "EPUB manifest contains a duplicate item ID.",
                item_id=item_id,
            )
        resolved_path, is_remote = _resolve_href(package_path, href)
        if resolved_path is not None:
            if resolved_path not in entries:
                _fail(
                    "epub.manifest.member_missing",
                    "EPUB manifest local resource is missing from the archive.",
                    item_id=item_id,
                    member=resolved_path,
                )
            previous = local_owners.get(resolved_path)
            if previous is not None:
                _fail(
                    "epub.manifest.ambiguous_local_owner",
                    "Multiple EPUB manifest items resolve to the same local member.",
                    member=resolved_path,
                    first_item_id=previous,
                    second_item_id=item_id,
                )
            local_owners[resolved_path] = item_id
        properties = tuple(
            token for token in element.attrib.get("properties", "").split() if token
        )
        item = EpubManifestItemEvidence(
            index=len(manifest),
            item_id=item_id,
            href=href,
            media_type=media_type,
            properties=properties,
            resolved_path=resolved_path,
            is_remote=is_remote,
            is_navigation="nav" in properties,
        )
        manifest.append(item)
        by_id[item_id] = item

    spine: list[EpubSpineItemEvidence] = []
    for element in list(spine_element):
        if getattr(element, "tag", None) != _expanded(_OPF_NS, "itemref"):
            continue
        idref = element.attrib.get("idref")
        if not idref or idref not in by_id:
            _fail(
                "epub.spine.broken_idref",
                "EPUB spine itemref does not resolve to one manifest item.",
                idref=idref,
            )
        if by_id[idref].is_remote:
            _fail(
                "epub.spine.remote_idref",
                "EPUB writable spine resources must be local archive members.",
                idref=idref,
            )
        spine.append(
            EpubSpineItemEvidence(
                index=len(spine),
                idref=idref,
                linear=element.attrib.get("linear"),
            )
        )

    unique_identifier_id = package_root.attrib.get("unique-identifier")
    unique_identifier_value: str | None = None
    if unique_identifier_id:
        for element in list(metadata_element):
            if element.attrib.get("id") == unique_identifier_id:
                unique_identifier_value = element.text
                break

    if len(rootfiles) != 1:
        writable_version = False
        read_only_reason = "epub.container.multiple_rootfiles"
    elif not isinstance(package_version, str) or not (
        package_version == "3" or package_version.startswith("3.")
    ):
        writable_version = False
        read_only_reason = "epub.package.unsupported_version"
    else:
        writable_version = True
        read_only_reason = None

    metadata_owners: tuple[EpubMetadataOwnerEvidence, ...] = ()
    xhtml_text_owners: tuple[EpubXhtmlTextEvidence, ...] = ()
    if writable_version:
        metadata_owners = _metadata_owners(
            package_document,
            member_path=package_path,
            member_sha256=entries[package_path].uncompressed_sha256,
        )
        xhtml_text_owners = _xhtml_owners(source, tuple(manifest), entries)

    return ParsedEpubSource(
        package=package,
        rootfiles=tuple(rootfiles),
        package_path=package_path,
        package_version=package_version,
        writable_version=writable_version,
        read_only_reason=read_only_reason,
        manifest=tuple(manifest),
        spine=tuple(spine),
        metadata_owners=metadata_owners,
        xhtml_text_owners=xhtml_text_owners,
        unique_identifier_id=unique_identifier_id,
        unique_identifier_value=unique_identifier_value,
    )
