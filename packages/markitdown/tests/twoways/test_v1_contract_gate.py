from __future__ import annotations

import json
from pathlib import Path

import markitdown.twoways as tw
from markitdown.twoways.capabilities import CAPABILITY_METADATA_KEY, CapabilityState
from markitdown.twoways.ir.document import SCHEMA_NAME, SCHEMA_VERSION


_REPO_ROOT = Path(__file__).resolve().parents[4]
_CONTRACT_PATH = _REPO_ROOT / "docs" / "twoways-v1-contract.json"
_TWOWAYS_PATH = _REPO_ROOT / "TWOWAYS.md"

_EXPECTED_NATIVE_FORMATS = {
    "text-markdown",
    "csv",
    "json",
    "xml",
    "html",
    "ipynb",
    "epub",
    "zip",
    "pdf",
    "png",
    "jpeg",
    "mp3",
    "msg",
    "xls",
    "xlsx",
    "pptx",
    "docx",
}

_EXPECTED_DERIVED_SURFACES = {
    "wikipedia",
    "bing-serp",
    "remote-feed",
    "youtube",
    "document-intelligence",
    "content-understanding",
    "audio-converter",
    "image-converter",
    "outlook-msg-converter",
    "pdf-converter",
    "xls-converter",
    "xlsx-converter",
}


def _contract() -> dict[str, object]:
    return json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


def test_v1_contract_freezes_wire_and_public_root() -> None:
    contract = _contract()

    assert contract["contract_name"] == "MarkItDown 2Ways"
    assert contract["contract_version"] == "1.0.0"
    assert contract["ir_schema"] == {
        "name": SCHEMA_NAME,
        "version": SCHEMA_VERSION,
        "supported_major": 0,
    }
    assert contract["capability_wire"] == {
        "metadata_key": CAPABILITY_METADATA_KEY,
        "states": sorted(state.value for state in CapabilityState),
    }

    public_symbols = contract["public_root_symbols"]
    assert isinstance(public_symbols, list)
    assert public_symbols == sorted(public_symbols)
    assert len(public_symbols) == len(set(public_symbols))
    assert public_symbols == sorted(tw.__all__)
    assert all(hasattr(tw, symbol) for symbol in public_symbols)


def test_v1_native_support_matrix_is_complete_and_unique() -> None:
    contract = _contract()
    rows = contract["native_support"]
    assert isinstance(rows, list)

    names = [row["format"] for row in rows]
    assert set(names) == _EXPECTED_NATIVE_FORMATS
    assert len(names) == len(set(names))

    for row in rows:
        assert isinstance(row["read"], bool)
        assert isinstance(row["native_write"], bool)
        assert isinstance(row["preservation"], str) and row["preservation"]
        operations = row["direct_operations"]
        assert isinstance(operations, list)
        assert operations == sorted(set(operations))
        if row["native_write"]:
            assert operations or row.get("routed_inner_operations") is True


def test_v1_derived_support_matrix_denies_native_writeback() -> None:
    contract = _contract()
    rows = contract["derived_support"]
    assert isinstance(rows, list)

    names = [row["surface"] for row in rows]
    assert set(names) == _EXPECTED_DERIVED_SURFACES
    assert len(names) == len(set(names))

    for row in rows:
        assert row["state"] == "derived"
        assert row["native_writeback"] is False
        assert isinstance(row["authority"], str) and row["authority"]


def test_v1_gate_records_explicit_out_of_scope_and_docs_authority() -> None:
    contract = _contract()
    out_of_scope = contract["out_of_scope"]
    assert isinstance(out_of_scope, list)
    assert len(out_of_scope) >= 8
    assert all(isinstance(item, str) and item for item in out_of_scope)

    twoways = _TWOWAYS_PATH.read_text(encoding="utf-8")
    assert "## v1.0 contract freeze" in twoways
    assert "docs/twoways-v1-contract.json" in twoways
    assert "phase-h30-v1-contract-support-matrix-closure-design.md" in twoways
