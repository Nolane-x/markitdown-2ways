from __future__ import annotations

from hashlib import sha256
from typing import Any

from ...ir.nodes import ImagePayload
from ...ir.resources import Resource


def extract_picture(shape: Any) -> tuple[ImagePayload, Resource]:
    image = shape.image
    blob = image.blob
    digest = sha256(blob).hexdigest()
    resource_id = f"pptx-resource-{digest[:24]}"
    try:
        alt_text = shape._element._nvXxPr.cNvPr.get("descr")
    except (AttributeError, TypeError):
        alt_text = None
    payload = ImagePayload(
        resource_id=resource_id,
        alt_text=alt_text,
        crop={
            "left": float(getattr(shape, "crop_left", 0.0) or 0.0),
            "top": float(getattr(shape, "crop_top", 0.0) or 0.0),
            "right": float(getattr(shape, "crop_right", 0.0) or 0.0),
            "bottom": float(getattr(shape, "crop_bottom", 0.0) or 0.0),
        },
    )
    resource = Resource(
        resource_id=resource_id,
        sha256=digest,
        content_type=image.content_type,
        filename=image.filename,
        size_bytes=len(blob),
        storage_ref=f"pptx:embedded:{digest}",
    )
    return payload, resource
