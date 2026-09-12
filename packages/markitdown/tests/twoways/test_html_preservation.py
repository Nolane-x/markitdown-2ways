from __future__ import annotations

import codecs
from io import BytesIO

import pytest

from markitdown.twoways._errors import RoundTripVerificationError, UnsupportedEditError
from markitdown.twoways.formats.html.preservation import verify_untouched_bytes
from markitdown.twoways.formats.html.reader import read_html_ir
from markitdown.twoways.formats.html.writer import patch_html
from markitdown.twoways.formats.text.model import TextRepresentation
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.semantics import native_locator_digest, node_semantic_digest


def _node(document, path):
    return next(
        node
        for node in document.nodes.values()
        if node.metadata.get("html.path") == path
    )


def _edit(document, path, value):
    node = _node(document, path)
    return EditOperation(
        operation_id="edit",
        type="replace_html_text",
        target_node_id=node.node_id,
        precondition=EditPrecondition(
            expected_semantic_digest=node_semantic_digest(node),
            expected_native_locator_digest=native_locator_digest(node),
            expected_old_value=node.payload["value"],
        ),
        payload={"value": value},
    )


def test_utf8_bom_is_preserved_while_text_value_changes() -> None:
    text = "<html><body><p>old</p><div>stay</div></body></html>"
    source = codecs.BOM_UTF8 + text.encode("utf-8")
    document = read_html_ir(BytesIO(source), filename="page.html")
    output = BytesIO()

    patch_html(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, "/html[1]/body[1]/p[1]/#text[1]", "new Ω"),),
    )

    assert output.getvalue() == codecs.BOM_UTF8 + (
        "<html><body><p>new Ω</p><div>stay</div></body></html>"
    ).encode("utf-8")


@pytest.mark.parametrize(
    ("bom", "encoding"),
    [
        (codecs.BOM_UTF16_LE, "utf-16-le"),
        (codecs.BOM_UTF16_BE, "utf-16-be"),
    ],
)
def test_utf16_bom_and_unrelated_bytes_are_preserved(bom, encoding) -> None:
    text = "<html><body><p>old</p><div>stay</div></body></html>"
    source = bom + text.encode(encoding)
    document = read_html_ir(BytesIO(source), filename="page.html")
    output = BytesIO()

    patch_html(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, "/html[1]/body[1]/p[1]/#text[1]", "changed"),),
    )

    assert output.getvalue() == bom + (
        "<html><body><p>changed</p><div>stay</div></body></html>"
    ).encode(encoding)


def test_reversible_cp1252_source_is_patched_without_reencoding_unrelated_bytes() -> (
    None
):
    text = (
        '<html><head><meta charset="cp1252"></head>'
        "<body><p>café</p><div>£ stay</div></body></html>"
    )
    source = text.encode("cp1252")
    document = read_html_ir(BytesIO(source), filename="page.html")
    output = BytesIO()

    patch_html(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, "/html[1]/body[1]/p[1]/#text[1]", "naïve"),),
    )

    assert output.getvalue() == (
        '<html><head><meta charset="cp1252"></head>'
        "<body><p>naïve</p><div>£ stay</div></body></html>"
    ).encode("cp1252")


def test_unencodable_replacement_fails_before_output() -> None:
    text = (
        '<html><head><meta charset="cp1252"></head>' "<body><p>café</p></body></html>"
    )
    source = text.encode("cp1252")
    document = read_html_ir(BytesIO(source), filename="page.html")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="represented"):
        patch_html(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "/html[1]/body[1]/p[1]/#text[1]", "Ω"),),
        )

    assert output.getvalue() == b""


def test_untouched_byte_verifier_rejects_fault_injected_candidate_bytes() -> None:
    representation = TextRepresentation(
        encoding="utf-8",
        bom="none",
        newline="none",
        byte_roundtrip=True,
    )
    source_text = "abcXYZdef"
    candidate_text = "abcQdef"
    source = source_text.encode("utf-8")
    candidate = b"zbcQdef"
    untouched = ((0, 3, 0, 3), (6, 9, 4, 7))

    with pytest.raises(RoundTripVerificationError):
        verify_untouched_bytes(
            source,
            candidate,
            source_text,
            candidate_text,
            representation,
            untouched,
        )
