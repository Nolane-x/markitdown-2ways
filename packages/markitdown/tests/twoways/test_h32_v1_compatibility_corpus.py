from __future__ import annotations

import json
from pathlib import Path

import pytest

from markitdown.twoways import (
    DocumentIR,
    UnsupportedSchemaVersionError,
    canonical_json_bytes,
    canonical_json_digest,
    decode_document,
)
from markitdown.twoways.ir.document import SCHEMA_NAME, SCHEMA_VERSION

from ._fixtures import make_representative_document


_REPO_ROOT = Path(__file__).resolve().parents[4]
_CORPUS_PATH = _REPO_ROOT / "docs" / "twoways-v1-compatibility-corpus.json"


def _corpus() -> dict[str, object]:
    return json.loads(_CORPUS_PATH.read_text(encoding="utf-8"))


def _goldens() -> dict[str, dict[str, object]]:
    corpus = _corpus()
    rows = corpus["goldens"]
    assert isinstance(rows, list)
    return {row["name"]: row for row in rows}


@pytest.mark.parametrize(
    ("name", "document"),
    [
        ("minimal-defaults", DocumentIR(document_id="minimal")),
        ("representative-document", make_representative_document()),
    ],
)
def test_v1_golden_canonical_ir_is_frozen(name: str, document: DocumentIR) -> None:
    golden = _goldens()[name]
    payload = canonical_json_bytes(document)

    assert len(payload) == golden["canonical_size_bytes"]
    assert canonical_json_digest(document) == golden["sha256"]
    assert canonical_json_bytes(decode_document(payload)) == payload


def test_v1_compatibility_manifest_matches_ir_schema() -> None:
    corpus = _corpus()

    assert corpus["corpus_name"] == "MarkItDown 2Ways v1 compatibility corpus"
    assert corpus["corpus_version"] == "1.0.0"
    assert corpus["ir_schema"] == {
        "name": SCHEMA_NAME,
        "version": SCHEMA_VERSION,
        "supported_major": 0,
    }


def test_v1_decoder_strict_and_forward_modes_are_frozen() -> None:
    payload = json.loads(canonical_json_bytes(make_representative_document()))
    payload["future_root"] = {"enabled": True}
    payload["canvases"][0]["future_canvas"] = "future"

    with pytest.raises(ValueError, match="future_root|future_canvas"):
        decode_document(payload, strict=True)

    decoded = decode_document(payload, strict=False)
    assert decoded == make_representative_document()


def test_v1_decoder_rejects_unknown_schema_major() -> None:
    payload = json.loads(canonical_json_bytes(DocumentIR(document_id="minimal")))
    payload["schema_version"] = "1.0.0"

    with pytest.raises(UnsupportedSchemaVersionError):
        decode_document(payload)


def test_v1_decoder_contract_manifest_is_explicit() -> None:
    corpus = _corpus()

    assert corpus["decoder_contract"] == {
        "strict_unknown_fields": "reject",
        "forward_unknown_fields": "ignore",
        "unknown_major": "reject",
        "encode_decode_encode": "byte-identical",
    }
