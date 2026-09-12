from __future__ import annotations

from hashlib import sha256
from typing import Any

from ...capabilities import CapabilityDecision, CapabilityState, encode_capabilities
from ...ir.geometry import Geometry
from ...ir.nodes import (
    ChartPayload,
    Node,
    TableCell,
    TablePayload,
    UnknownNativePayload,
)
from ...ir.provenance import BoundingBox, Provenance
from ...ir.resources import NativePayload
from .geometry import geometry_patchability
from .locators import shape_locator, stable_node_id
from .resources import extract_picture
from .style import style_patchability
from .table import pptx_table_patch_compatible
from .text import extract_text_payload, text_patch_compatible

_CAPABILITY_KEY = "twoways.capabilities.v1"


def _geometry(shape: Any) -> Geometry:
    left = int(getattr(shape, "left", 0) or 0)
    top = int(getattr(shape, "top", 0) or 0)
    width = int(getattr(shape, "width", 0) or 0)
    height = int(getattr(shape, "height", 0) or 0)
    rotation = float(getattr(shape, "rotation", 0.0) or 0.0)
    return Geometry(
        x=float(left),
        y=float(top),
        width=float(width),
        height=float(height),
        rotation=rotation,
        unit="emu",
        source_values={
            "x": left,
            "y": top,
            "width": width,
            "height": height,
        },
    )


def _provenance(
    shape: Any, *, slide_index: int, part_uri: str
) -> tuple[Provenance, ...]:
    geometry = _geometry(shape)
    return (
        Provenance(
            source_format="pptx",
            canvas_index=slide_index,
            part_uri=part_uri,
            bbox=BoundingBox(
                x=geometry.x,
                y=geometry.y,
                width=geometry.width,
                height=geometry.height,
                unit="emu",
            ),
            extraction_method="python-pptx+ooxml",
        ),
    )


def _writable(operation: str, **constraints: object) -> CapabilityDecision:
    return CapabilityDecision(
        operation=operation,
        state=CapabilityState.WRITABLE,
        constraints=constraints,
    )


def _read_only(operation: str, reason_code: str) -> CapabilityDecision:
    return CapabilityDecision(
        operation=operation,
        state=CapabilityState.READ_ONLY,
        reason_code=reason_code,
    )


def _geometry_capability(
    shape: Any,
    geometry: Geometry,
    *,
    part_uri: str,
    parent_id: str | None,
) -> CapabilityDecision:
    if parent_id is not None:
        return _read_only("move_resize", "pptx.geometry.group_coordinate_space")
    if not part_uri.startswith("/ppt/slides/"):
        return _read_only("move_resize", "pptx.geometry.unsupported_part")
    compatible, reason = geometry_patchability(shape._element, geometry)
    if not compatible:
        return _read_only(
            "move_resize",
            reason or "pptx.geometry.unsupported_native_transform",
        )
    return _writable(
        "move_resize",
        group_coordinate_space=False,
        rotation=False,
        unit="emu",
    )


def build_shape_node(
    shape: Any,
    *,
    slide_index: int,
    canvas_id: str,
    part_uri: str,
    z_order: int,
    is_title: bool,
    picture_shape_type: Any,
    parent_id: str | None = None,
) -> tuple[Node, dict[str, Any], NativePayload | None]:
    locator = shape_locator(shape, part_uri=part_uri, z_order=z_order)
    geometry = _geometry(shape)
    geometry_capability = _geometry_capability(
        shape,
        geometry,
        part_uri=part_uri,
        parent_id=parent_id,
    )
    common = {
        "canvas_id": canvas_id,
        "parent_id": parent_id,
        "geometry": geometry,
        "native_locator": locator,
        "provenance": _provenance(shape, slide_index=slide_index, part_uri=part_uri),
        "order": z_order,
        "metadata": {"pptx:z_order": z_order},
    }

    if shape.shape_type == picture_shape_type:
        payload, resource = extract_picture(shape)
        node_id = stable_node_id(locator, "image")
        metadata = dict(common["metadata"])
        metadata[_CAPABILITY_KEY] = encode_capabilities(
            (
                _writable("set_alt_text", preserve_relationships=True),
                geometry_capability,
            )
        )
        return (
            Node(
                node_id=node_id,
                kind="image",
                payload=payload,
                semantic_role="image",
                **{**common, "metadata": metadata},
            ),
            {resource.resource_id: resource},
            None,
        )

    if getattr(shape, "has_table", False):
        table = shape.table
        cells = []
        for row_index, row in enumerate(table.rows):
            for column_index, cell in enumerate(row.cells):
                cells.append(
                    TableCell(
                        row=row_index,
                        column=column_index,
                        text=cell.text or "",
                    )
                )
        node_id = stable_node_id(locator, "table")
        metadata = dict(common["metadata"])
        table_compatible = pptx_table_patch_compatible(table)
        metadata["pptx:patch_capabilities"] = (
            ("update_table_cells",) if table_compatible else ()
        )
        table_capability = (
            _writable("update_table_cells", preserve_cell_wrappers=True)
            if table_compatible
            else _read_only(
                "update_table_cells", "pptx.table.unsupported_native_structure"
            )
        )
        metadata[_CAPABILITY_KEY] = encode_capabilities(
            (table_capability, geometry_capability)
        )
        return (
            Node(
                node_id=node_id,
                kind="table",
                payload=TablePayload(
                    rows=len(table.rows),
                    columns=len(table.columns),
                    cells=tuple(cells),
                ),
                semantic_role="table",
                **{**common, "metadata": metadata},
            ),
            {},
            None,
        )

    if getattr(shape, "has_chart", False):
        chart = shape.chart
        try:
            categories = tuple(category.label for category in chart.plots[0].categories)
        except Exception:
            categories = ()
        series = tuple(
            {"name": item.name, "values": tuple(float(value) for value in item.values)}
            for item in chart.series
        )
        title = None
        try:
            if chart.has_title and chart.chart_title.has_text_frame:
                title = chart.chart_title.text_frame.text or None
        except Exception:
            title = None
        native_bytes = chart.part.blob
        native_digest = sha256(native_bytes).hexdigest()
        payload_id = f"pptx-chart-{native_digest[:24]}"
        native_payload = NativePayload(
            payload_id=payload_id,
            backend="pptx-ooxml",
            content_type="application/vnd.openxmlformats-officedocument.drawingml.chart+xml",
            sha256=native_digest,
            storage_ref=str(chart.part.partname),
            scope="chart",
        )
        node_id = stable_node_id(locator, "chart")
        metadata = dict(common["metadata"])
        metadata["pptx:patch_capabilities"] = ()
        metadata[_CAPABILITY_KEY] = encode_capabilities((geometry_capability,))
        return (
            Node(
                node_id=node_id,
                kind="chart",
                payload=ChartPayload(
                    chart_type=str(chart.chart_type),
                    title=title,
                    categories=categories,
                    series=series,
                    native_payload_ref=payload_id,
                ),
                semantic_role="chart",
                **{**common, "metadata": metadata},
            ),
            {},
            native_payload,
        )

    if getattr(shape, "has_text_frame", False):
        payload = extract_text_payload(shape, locator)
        node_id = stable_node_id(locator, "text")
        metadata = dict(common["metadata"])
        text_compatible = text_patch_compatible(shape)
        style_compatible, style_reason = style_patchability(shape._element)
        metadata["pptx:patch_text_compatible"] = text_compatible
        replace_capability = (
            _writable("replace_text", preserve_run_structure=True)
            if text_compatible
            else _read_only("replace_text", "pptx.text.unsupported_native_structure")
        )
        style_capability = (
            _writable(
                "set_text_style",
                direct_run_style=True,
                run_indexed=True,
                font_size_unit="hundredth-point",
            )
            if style_compatible
            else _read_only(
                "set_text_style",
                style_reason or "pptx.style.ambiguous_direct_style",
            )
        )
        metadata[_CAPABILITY_KEY] = encode_capabilities(
            (replace_capability, style_capability, geometry_capability)
        )
        return (
            Node(
                node_id=node_id,
                kind="text",
                payload=payload,
                semantic_role="title" if is_title else None,
                **{**common, "metadata": metadata},
            ),
            {},
            None,
        )

    native_bytes = bytes(shape._element.xml, "utf-8")
    native_digest = sha256(native_bytes).hexdigest()
    node_id = stable_node_id(locator, "unknown_native")
    payload_id = f"pptx-native-{native_digest[:24]}"
    native_payload = NativePayload(
        payload_id=payload_id,
        backend="pptx-ooxml",
        content_type="application/xml",
        sha256=native_digest,
        storage_ref=f"{part_uri}#shape={locator.object_id}",
        scope="shape",
    )
    metadata = dict(common["metadata"])
    metadata[_CAPABILITY_KEY] = encode_capabilities(
        (_read_only("move_resize", "pptx.geometry.unknown_native_shape_read_only"),)
    )
    return (
        Node(
            node_id=node_id,
            kind="unknown_native",
            payload=UnknownNativePayload(
                native_payload_ref=payload_id,
                summary=f"Unsupported PPTX shape {shape.name}",
            ),
            **{**common, "metadata": metadata},
        ),
        {},
        native_payload,
    )


def build_note_node(
    shape: Any,
    *,
    slide_index: int,
    canvas_id: str,
    part_uri: str,
    order: int,
) -> Node:
    locator = shape_locator(shape, part_uri=part_uri, z_order=order)
    payload = extract_text_payload(shape, locator)
    text_compatible = text_patch_compatible(shape)
    style_compatible, style_reason = style_patchability(shape._element)
    replace_capability = (
        _writable("replace_text", preserve_run_structure=True)
        if text_compatible
        else _read_only("replace_text", "pptx.text.unsupported_native_structure")
    )
    style_capability = (
        _writable(
            "set_text_style",
            direct_run_style=True,
            run_indexed=True,
            font_size_unit="hundredth-point",
        )
        if style_compatible
        else _read_only(
            "set_text_style",
            style_reason or "pptx.style.ambiguous_direct_style",
        )
    )
    return Node(
        node_id=stable_node_id(locator, "note"),
        kind="note",
        semantic_role="notes",
        canvas_id=canvas_id,
        geometry=_geometry(shape),
        native_locator=locator,
        provenance=_provenance(shape, slide_index=slide_index, part_uri=part_uri),
        payload=payload,
        order=order,
        metadata={
            "pptx:z_order": order,
            "pptx:patch_text_compatible": text_compatible,
            _CAPABILITY_KEY: encode_capabilities(
                (
                    replace_capability,
                    style_capability,
                    _read_only("move_resize", "pptx.geometry.unsupported_part"),
                )
            ),
        },
    )


def build_shape_tree(
    shape: Any,
    *,
    slide_index: int,
    canvas_id: str,
    part_uri: str,
    z_order: int,
    is_title: bool,
    picture_shape_type: Any,
    group_shape_type: Any,
    parent_id: str | None = None,
) -> tuple[Node, dict[str, Node], dict[str, Any], dict[str, NativePayload]]:
    if shape.shape_type != group_shape_type:
        node, resources, native_payload = build_shape_node(
            shape,
            slide_index=slide_index,
            canvas_id=canvas_id,
            part_uri=part_uri,
            z_order=z_order,
            is_title=is_title,
            picture_shape_type=picture_shape_type,
            parent_id=parent_id,
        )
        native_payloads = (
            {}
            if native_payload is None
            else {native_payload.payload_id: native_payload}
        )
        return node, {node.node_id: node}, resources, native_payloads

    locator = shape_locator(shape, part_uri=part_uri, z_order=z_order)
    group_id = stable_node_id(locator, "group")
    child_ids: list[str] = []
    nodes: dict[str, Node] = {}
    resources: dict[str, Any] = {}
    native_payloads: dict[str, NativePayload] = {}

    for child_z_order, child_shape in enumerate(shape.shapes):
        child_root, child_nodes, child_resources, child_payloads = build_shape_tree(
            child_shape,
            slide_index=slide_index,
            canvas_id=canvas_id,
            part_uri=part_uri,
            z_order=child_z_order,
            is_title=False,
            picture_shape_type=picture_shape_type,
            group_shape_type=group_shape_type,
            parent_id=group_id,
        )
        child_ids.append(child_root.node_id)
        nodes.update(child_nodes)
        resources.update(child_resources)
        native_payloads.update(child_payloads)

    group = Node(
        node_id=group_id,
        kind="group",
        parent_id=parent_id,
        children=tuple(child_ids),
        order=z_order,
        canvas_id=canvas_id,
        geometry=_geometry(shape),
        provenance=_provenance(shape, slide_index=slide_index, part_uri=part_uri),
        native_locator=locator,
        metadata={
            "pptx:z_order": z_order,
            "pptx:patch_capabilities": (),
            _CAPABILITY_KEY: encode_capabilities(
                (_read_only("move_resize", "pptx.geometry.group_coordinate_space"),)
            ),
        },
    )
    nodes[group.node_id] = group
    return group, nodes, resources, native_payloads
