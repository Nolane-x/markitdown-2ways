from __future__ import annotations

from hashlib import sha256
from typing import Any

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
from .locators import shape_locator, stable_node_id
from .resources import extract_picture
from .text import extract_text_payload, text_patch_compatible


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


def _provenance(shape: Any, *, slide_index: int, part_uri: str) -> tuple[Provenance, ...]:
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


def build_shape_node(
    shape: Any,
    *,
    slide_index: int,
    canvas_id: str,
    part_uri: str,
    z_order: int,
    is_title: bool,
    picture_shape_type: Any,
) -> tuple[Node, dict[str, Any], NativePayload | None]:
    locator = shape_locator(shape, part_uri=part_uri, z_order=z_order)
    geometry = _geometry(shape)
    common = {
        "canvas_id": canvas_id,
        "geometry": geometry,
        "native_locator": locator,
        "provenance": _provenance(shape, slide_index=slide_index, part_uri=part_uri),
        "order": z_order,
        "metadata": {"pptx:z_order": z_order},
    }

    if shape.shape_type == picture_shape_type:
        payload, resource = extract_picture(shape)
        node_id = stable_node_id(locator, "image")
        return (
            Node(
                node_id=node_id,
                kind="image",
                payload=payload,
                semantic_role="image",
                **common,
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
        metadata["pptx:patch_capabilities"] = ()
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
        metadata["pptx:patch_text_compatible"] = text_patch_compatible(shape)
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
    return (
        Node(
            node_id=node_id,
            kind="unknown_native",
            payload=UnknownNativePayload(
                native_payload_ref=payload_id,
                summary=f"Unsupported PPTX shape {shape.name}",
            ),
            **common,
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
    return Node(
        node_id=stable_node_id(locator, "note"),
        kind="note",
        semantic_role="notes",
        canvas_id=canvas_id,
        geometry=_geometry(shape),
        native_locator=locator,
        provenance=_provenance(shape, slide_index=slide_index, part_uri=part_uri),
        payload=extract_text_payload(shape, locator),
        order=order,
        metadata={
            "pptx:z_order": order,
            "pptx:patch_text_compatible": text_patch_compatible(shape),
        },
    )
