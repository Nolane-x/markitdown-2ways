import dataclasses
from hashlib import sha256
import json
import math
import pytest

from markitdown.twoways import (
    DocumentMetadata,
    UnsupportedSchemaVersionError,
    canonical_json_bytes,
    canonical_json_digest,
    decode_document,
    to_canonical_dict,
)
from ._fixtures import make_representative_document


def test_encode_decode_encode_is_byte_identical():
    first = canonical_json_bytes(make_representative_document())
    decoded = decode_document(first)
    second = canonical_json_bytes(decoded)
    assert second == first
    assert decoded == make_representative_document()


def test_canonical_json_preserves_unicode_without_ascii_escape():
    raw = canonical_json_bytes(make_representative_document(title="Tài liệu 日本語"))
    assert "Tài liệu 日本語".encode("utf-8") in raw


def test_digest_is_sha256_of_canonical_bytes():
    doc = make_representative_document()
    assert canonical_json_digest(doc) == sha256(canonical_json_bytes(doc)).hexdigest()


def test_unknown_major_version_is_rejected():
    payload = json.loads(canonical_json_bytes(make_representative_document()))
    payload["schema_version"] = "1.0.0"
    with pytest.raises(UnsupportedSchemaVersionError):
        decode_document(payload)


def test_unknown_field_rejected_in_strict_mode_and_ignored_in_forward_mode():
    payload = json.loads(canonical_json_bytes(make_representative_document()))
    payload["future_field"] = 1
    with pytest.raises(ValueError, match="future_field"):
        decode_document(payload, strict=True)
    decoded = decode_document(payload, strict=False)
    assert decoded.schema_version == "0.1.0"


def test_nested_unknown_field_is_rejected_in_strict_mode():
    payload = json.loads(canonical_json_bytes(make_representative_document()))
    payload["canvases"][0]["future_canvas_field"] = "x"
    with pytest.raises(ValueError, match="future_canvas_field"):
        decode_document(payload, strict=True)


def test_nan_and_infinity_are_rejected_even_inside_custom_metadata():
    doc = make_representative_document()
    for bad in (math.nan, math.inf, -math.inf):
        broken = dataclasses.replace(
            doc, metadata=DocumentMetadata(custom={"bad": bad})
        )
        with pytest.raises(ValueError):
            canonical_json_bytes(broken)


def test_binary_values_are_not_silently_stringified():
    doc = make_representative_document()
    broken = dataclasses.replace(
        doc, metadata=DocumentMetadata(custom={"blob": b"abc"})
    )
    with pytest.raises(TypeError, match="bytes"):
        canonical_json_bytes(broken)


def test_absent_optional_fields_use_omit_none_policy():
    data = to_canonical_dict(make_representative_document())
    assert "subject" not in data["metadata"]
    assert "source" not in data
