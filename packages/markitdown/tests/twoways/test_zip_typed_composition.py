from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest

from markitdown.twoways.formats.zip.reader import read_zip_ir
from markitdown.twoways.formats.zip.writer import patch_zip
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.semantics import native_locator_digest, node_semantic_digest

from ._zip_fixtures import make_zip


def _edit(node, *, operation_id: str, edit_type: str, payload: dict) -> EditOperation:
    return EditOperation(
        operation_id=operation_id,
        type=edit_type,
        target_node_id=node.node_id,
        precondition=EditPrecondition(
            expected_semantic_digest=node_semantic_digest(node),
            expected_native_locator_digest=native_locator_digest(node),
        ),
        payload=payload,
    )


def _patched_member(
    filename: str,
    payload: bytes,
    node_predicate,
    *,
    edit_type: str,
    edit_payload: dict,
) -> bytes:
    source = make_zip(members={filename: payload, "keep.bin": b"keep"})
    document = read_zip_ir(BytesIO(source), filename="bundle.zip")
    target = next(node for node in document.nodes.values() if node_predicate(node))
    assert target.metadata["zip.member_chain"] == (filename,)
    assert target.metadata["zip.adapter_key"]

    output = BytesIO()
    patch_zip(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(
                target,
                operation_id=f"edit-{filename}",
                edit_type=edit_type,
                payload=edit_payload,
            ),
        ),
    )

    with ZipFile(BytesIO(output.getvalue()), "r") as archive:
        assert archive.read("keep.bin") == b"keep"
        return archive.read(filename)


def test_nested_text_and_markdown_compose_through_h1_writer() -> None:
    patched = _patched_member(
        "notes.txt",
        b"alpha\n",
        lambda node: node.metadata.get("text.native_source") is True,
        edit_type="replace_text",
        edit_payload={"text": "beta\n"},
    )
    assert patched == b"beta\n"


@pytest.mark.parametrize("filename", ["README.md", "README.markdown"])
def test_nested_markdown_extensions_route_to_h1_writer(filename: str) -> None:
    patched = _patched_member(
        filename,
        b"# Alpha\n",
        lambda node: node.metadata.get("text.native_source") is True,
        edit_type="replace_text",
        edit_payload={"text": "# Beta\n"},
    )
    assert patched == b"# Beta\n"


def test_nested_csv_composes_through_h2_writer() -> None:
    patched = _patched_member(
        "people.csv",
        b"name,city\nAda,North\n",
        lambda node: node.metadata.get("csv.delimiter") == ",",
        edit_type="update_csv_cells",
        edit_payload={
            "cells": [
                {"row": 1, "column": 1, "old_text": "North", "text": "South"},
            ]
        },
    )
    assert patched == b"name,city\nAda,South\n"


def test_nested_xml_composes_through_h4_writer() -> None:
    patched = _patched_member(
        "data.xml",
        b"<root><name>Ada</name></root>",
        lambda node: node.metadata.get("xml.kind") == "text"
        and getattr(node.payload, "text", None) == "Ada",
        edit_type="replace_xml_text",
        edit_payload={"value": "Nolane"},
    )
    assert patched == b"<root><name>Nolane</name></root>"


def test_nested_html_composes_through_h5_writer() -> None:
    patched = _patched_member(
        "page.html",
        b"<html><body><p>Ada</p></body></html>",
        lambda node: node.metadata.get("html.kind") == "text"
        and getattr(node.payload, "text", None) == "Ada",
        edit_type="replace_html_text",
        edit_payload={"value": "Nolane"},
    )
    assert patched == b"<html><body><p>Nolane</p></body></html>"


def test_nested_ipynb_composes_through_h6_writer() -> None:
    notebook = (
        b'{"cells":[{"cell_type":"markdown","id":"m1","metadata":{},'
        b'"source":["hello\\n","world"]}],"metadata":{},'
        b'"nbformat":4,"nbformat_minor":5}'
    )
    patched = _patched_member(
        "book.ipynb",
        notebook,
        lambda node: node.metadata.get("ipynb.source_pointer") is not None,
        edit_type="replace_ipynb_cell_source",
        edit_payload={"value": "HELLO\nWORLD"},
    )
    assert b"HELLO" in patched
    assert b"WORLD" in patched
