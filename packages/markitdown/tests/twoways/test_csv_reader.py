from __future__ import annotations

import codecs
from io import BytesIO
from types import SimpleNamespace

from markitdown.twoways.capabilities import CapabilityState, capabilities_for_node
from markitdown.twoways.formats.csv.reader import CsvIRReader, read_csv_ir
from markitdown.twoways.ir.nodes import TablePayload
from markitdown.twoways.ir.serialization import canonical_json_digest, validate_document


def _table(document):
    return document.nodes[document.canvases[0].root_node_ids[0]]


def test_csv_reader_builds_deterministic_table_ir_with_lexical_metadata() -> None:
    source = codecs.BOM_UTF8 + 'name,city\r\nAda,"Hà Nội"\r\n'.encode("utf-8")

    first = read_csv_ir(
        BytesIO(source), filename="people.csv", mimetype="text/csv"
    )
    second = read_csv_ir(
        BytesIO(source), filename="people.csv", mimetype="text/csv"
    )

    validate_document(first)
    assert canonical_json_digest(first) == canonical_json_digest(second)
    assert first.source is not None
    assert first.source.format == "csv"
    assert first.source.filename == "people.csv"
    assert first.source.mimetype == "text/csv"
    assert first.source.size_bytes == len(source)
    assert first.source.sha256 is not None
    assert first.source.preserved_source_ref == f"csv:sha256:{first.source.sha256}"

    assert len(first.canvases) == 1
    assert first.canvases[0].kind == "table"
    node = _table(first)
    assert node.kind == "table"
    assert node.semantic_role == "csv-grid"
    assert node.native_locator is not None
    assert node.native_locator.backend == "csv"
    assert node.native_locator.part_uri == "/"
    assert node.native_locator.object_id == "table"
    assert isinstance(node.payload, TablePayload)
    assert node.payload.rows == 2
    assert node.payload.columns == 2
    assert [(cell.row, cell.column, cell.text) for cell in node.payload.cells] == [
        (0, 0, "name"),
        (0, 1, "city"),
        (1, 0, "Ada"),
        (1, 1, "Hà Nội"),
    ]

    city = node.payload.cells[3]
    assert city.metadata["csv.char_start"] == 19
    assert city.metadata["csv.char_end"] == 26
    assert city.metadata["csv.quoted"] is True
    assert city.metadata["csv.multiline"] is False
    assert city.metadata["csv.present"] is True
    assert city.metadata["csv.writable"] is True
    assert isinstance(city.metadata["csv.raw_digest"], str)

    assert node.metadata["csv.delimiter"] == ","
    assert node.metadata["csv.quotechar"] == '"'
    assert node.metadata["csv.doublequote"] is True
    assert node.metadata["csv.escapechar"] is None
    assert node.metadata["csv.skipinitialspace"] is False
    assert node.metadata["csv.encoding"] == "utf-8"
    assert node.metadata["csv.bom"] == "utf-8"
    assert node.metadata["csv.byte_roundtrip"] is True
    assert node.metadata["csv.identity_markdown"] is False
    assert node.metadata["csv.row_terminators"] == ("crlf",)


def test_proven_csv_advertises_direct_update_csv_cells() -> None:
    document = read_csv_ir(BytesIO(b"a,b\nc,d\n"), filename="data.csv")
    decision = capabilities_for_node(_table(document)).for_operation("update_csv_cells")

    assert decision.state is CapabilityState.WRITABLE
    assert decision.reason_code is None
    assert decision.constraints == {
        "identity_markdown": False,
        "source_preservation": "lexical-field-spans",
        "structural_edits": False,
        "target_only": True,
    }


def test_unproven_single_column_csv_is_readable_but_read_only() -> None:
    document = read_csv_ir(BytesIO(b"alpha\nbeta\n"), filename="single.csv")
    node = _table(document)
    decision = capabilities_for_node(node).for_operation("update_csv_cells")

    assert isinstance(node.payload, TablePayload)
    assert [cell.text for cell in node.payload.cells] == ["alpha", "beta"]
    assert node.metadata["csv.delimiter"] == ","
    assert node.metadata["csv.dialect_proven"] is False
    assert decision.state is CapabilityState.READ_ONLY
    assert decision.reason_code == "csv.dialect.unproven_single_column"
    assert all(cell.metadata["csv.writable"] is False for cell in node.payload.cells)


def test_explicit_delimiter_makes_single_column_source_authoritative() -> None:
    document = read_csv_ir(
        BytesIO(b"alpha\nbeta\n"), filename="single.csv", delimiter=";"
    )
    node = _table(document)
    decision = capabilities_for_node(node).for_operation("update_csv_cells")

    assert node.metadata["csv.delimiter"] == ";"
    assert node.metadata["csv.dialect_proven"] is True
    assert decision.state is CapabilityState.WRITABLE


def test_non_roundtrippable_encoding_is_read_only_even_with_proven_dialect() -> None:
    document = read_csv_ir(
        BytesIO(b"a,b\nc,d\n"), filename="data.csv", encoding="utf-8-sig"
    )
    node = _table(document)
    decision = capabilities_for_node(node).for_operation("update_csv_cells")

    assert node.metadata["csv.byte_roundtrip"] is False
    assert decision.state is CapabilityState.READ_ONLY
    assert decision.reason_code == "csv.encoding.not_roundtrippable"


def test_ragged_rows_materialize_only_native_fields() -> None:
    document = read_csv_ir(BytesIO(b"a,b,c\n\nx,y\n"), filename="ragged.csv")
    payload = _table(document).payload

    assert isinstance(payload, TablePayload)
    assert payload.rows == 3
    assert payload.columns == 3
    assert [(cell.row, cell.column) for cell in payload.cells] == [
        (0, 0),
        (0, 1),
        (0, 2),
        (2, 0),
        (2, 1),
    ]


def test_csv_ir_reader_accepts_only_csv_extension_or_mimetype() -> None:
    reader = CsvIRReader()

    assert reader.accepts(
        BytesIO(b""), SimpleNamespace(extension=".csv", mimetype=None)
    )
    assert reader.accepts(
        BytesIO(b""), SimpleNamespace(extension=".txt", mimetype="text/csv")
    )
    assert reader.accepts(
        BytesIO(b""), SimpleNamespace(extension=None, mimetype="application/csv; charset=utf-8")
    )
    assert not reader.accepts(
        BytesIO(b""), SimpleNamespace(extension=".txt", mimetype="text/plain")
    )
