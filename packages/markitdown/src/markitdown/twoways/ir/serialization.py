from __future__ import annotations

from collections.abc import Mapping as ABCMapping
from dataclasses import fields, is_dataclass
from hashlib import sha256
import json
import math
import re
import types
from typing import Any, Mapping, Union, get_args, get_origin, get_type_hints

from .._errors import UnsupportedSchemaVersionError
from ._validation import ValidationViolation, validate_document
from .document import DocumentIR
from .nodes import (
    ChartPayload,
    ImagePayload,
    Node,
    TablePayload,
    TextPayload,
    UnknownNativePayload,
)

_SCHEMA_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def _json_value(value: Any, *, path: str = "$") -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        result: dict[str, Any] = {}
        for field_info in fields(value):
            field_value = getattr(value, field_info.name)
            if field_value is None:
                continue
            result[field_info.name] = _json_value(field_value, path=f"{path}.{field_info.name}")
        return result
    if isinstance(value, ABCMapping):
        result: dict[str, Any] = {}
        for key in sorted(value, key=str):
            if not isinstance(key, str):
                raise TypeError(f"mapping key at {path} must be str, got {type(key).__name__}")
            result[key] = _json_value(value[key], path=f"{path}.{key}")
        return result
    if isinstance(value, (tuple, list)):
        return [_json_value(item, path=f"{path}[{i}]") for i, item in enumerate(value)]
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise TypeError(f"bytes are not allowed in canonical JSON at {path}")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite float is not allowed in canonical JSON at {path}")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported canonical JSON value at {path}: {type(value).__name__}")


def to_canonical_dict(document: DocumentIR) -> dict[str, Any]:
    validate_document(document)
    result = _json_value(document)
    if not isinstance(result, dict):
        raise TypeError("DocumentIR did not serialize to a mapping")
    return result


def canonical_json_bytes(document: DocumentIR) -> bytes:
    return json.dumps(
        to_canonical_dict(document),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_json_digest(document: DocumentIR) -> str:
    return sha256(canonical_json_bytes(document)).hexdigest()


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, ABCMapping):
        raise ValueError(f"{path} must be an object")
    return dict(value)


def _array(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be an array")
    return value


def _decode_any(value: Any, path: str) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise TypeError(f"bytes are not valid JSON at {path}")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite float is not valid JSON at {path}")
    if isinstance(value, ABCMapping):
        return {str(k): _decode_any(v, f"{path}.{k}") for k, v in value.items()}
    if isinstance(value, list):
        return [_decode_any(v, f"{path}[{i}]") for i, v in enumerate(value)]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported JSON value at {path}: {type(value).__name__}")


def _decode_type(annotation: Any, value: Any, strict: bool, path: str) -> Any:
    if annotation is Any:
        return _decode_any(value, path)

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin in (Union, types.UnionType):
        if value is None and type(None) in args:
            return None
        last_error: Exception | None = None
        for candidate in args:
            if candidate is type(None):
                continue
            try:
                return _decode_type(candidate, value, strict, path)
            except (TypeError, ValueError) as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        return value

    if origin is tuple:
        values = _array(value, path)
        item_type = args[0] if args else Any
        return tuple(_decode_type(item_type, item, strict, f"{path}[{i}]") for i, item in enumerate(values))

    if origin in (dict, ABCMapping, Mapping):
        raw = _mapping(value, path)
        key_type = args[0] if args else str
        value_type = args[1] if len(args) > 1 else Any
        if key_type not in (str, Any):
            raise TypeError(f"unsupported mapping key type at {path}: {key_type}")
        return {key: _decode_type(value_type, item, strict, f"{path}.{key}") for key, item in raw.items()}

    if isinstance(annotation, type) and is_dataclass(annotation):
        return _decode_dataclass(annotation, value, strict, path)

    if annotation in (str, int, float, bool):
        if annotation is float and isinstance(value, (int, float)) and not isinstance(value, bool):
            # Preserve the JSON numeric representation (e.g. 10 vs 10.0) so
            # encode/decode/encode remains byte-identical. Dataclasses do not
            # coerce runtime numeric types, and both forms satisfy the portable
            # numeric contract.
            return value
        if not isinstance(value, annotation):
            raise ValueError(f"{path} must be {annotation.__name__}")
        return value

    return _decode_any(value, path)


def _decode_node_payload(kind: str, value: Any, strict: bool, path: str) -> Any:
    payload_type = {
        "text": TextPayload,
        "image": ImagePayload,
        "table": TablePayload,
        "chart": ChartPayload,
        "unknown_native": UnknownNativePayload,
    }.get(kind)
    if payload_type is None:
        return _mapping(value, path)
    return _decode_dataclass(payload_type, value, strict, path)


def _decode_dataclass(cls: type[Any], value: Any, strict: bool, path: str) -> Any:
    raw = _mapping(value, path)
    model_fields = {field_info.name: field_info for field_info in fields(cls)}
    unknown = sorted(set(raw) - set(model_fields))
    if strict and unknown:
        raise ValueError(f"{path} contains unexpected field(s): {', '.join(unknown)}")

    hints = get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    for name, field_info in model_fields.items():
        if name not in raw:
            continue
        child_path = f"{path}.{name}"
        if cls is Node and name == "payload":
            kwargs[name] = _decode_node_payload(str(raw.get("kind", "")), raw[name], strict, child_path)
            continue
        kwargs[name] = _decode_type(hints.get(name, Any), raw[name], strict, child_path)
    return cls(**kwargs)


def decode_document(
    data: bytes | str | ABCMapping[str, Any], *, strict: bool = True
) -> DocumentIR:
    if isinstance(data, bytes):
        raw: Any = json.loads(data.decode("utf-8"))
    elif isinstance(data, str):
        raw = json.loads(data)
    elif isinstance(data, ABCMapping):
        raw = dict(data)
    else:
        raise TypeError("data must be bytes, str, or a mapping")

    obj = _mapping(raw, "$")
    version = obj.get("schema_version", "")
    match = _SCHEMA_RE.fullmatch(version) if isinstance(version, str) else None
    if match is not None and int(match.group(1)) != 0:
        raise UnsupportedSchemaVersionError(
            f"Unsupported MarkItDown 2Ways schema version: {version}",
            details={"schema_version": version, "supported_major": 0},
        )

    document = _decode_dataclass(DocumentIR, obj, strict, "$")
    validate_document(document)
    return document


__all__ = [
    "ValidationViolation",
    "validate_document",
    "to_canonical_dict",
    "canonical_json_bytes",
    "canonical_json_digest",
    "decode_document",
]
