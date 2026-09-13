from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways._errors import RoundTripVerificationError
from markitdown.twoways.formats.zip.package import build_zip_candidate
from markitdown.twoways.formats.zip.parser import parse_zip_source
from markitdown.twoways.formats.zip.reader import read_zip_ir
from markitdown.twoways.formats.zip.routing import resolve_zip_edit
from markitdown.twoways.formats.zip.verification import verify_zip_candidate
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.semantics import native_locator_digest, node_semantic_digest

from ._zip_fixtures import make_zip


def _target(document):
    return next(
        node
        for node in document.nodes.values()
        if node.metadata.get("zip.member_chain") == ("data.json",)
        and node.metadata.get("json.pointer") == "/name"
    )


def test_verifier_rejects_unauthorized_sibling_drift() -> None:
    source = make_zip(
        members={
            "data.json": b'{"name":"Ada"}\n',
            "note.txt": b"keep\n",
        }
    )
    document = read_zip_ir(BytesIO(source), filename="bundle.zip")
    target = _target(document)
    edit = EditOperation(
        operation_id="edit-name",
        type="replace_json_scalar",
        target_node_id=target.node_id,
        precondition=EditPrecondition(
            expected_semantic_digest=node_semantic_digest(target),
            expected_native_locator_digest=native_locator_digest(target),
        ),
        payload={"value": "Nolane"},
    )
    original = parse_zip_source(source, filename="bundle.zip")
    routed = resolve_zip_edit(document, original, edit)
    candidate = build_zip_candidate(
        original.snapshot,
        source,
        replacements={
            "data.json": b'{"name":"Nolane"}\n',
            "note.txt": b"DRIFT\n",
        },
    )

    with pytest.raises(RoundTripVerificationError):
        verify_zip_candidate(
            original,
            candidate,
            requested=(routed,),
            touched_chains={("data.json",)},
        )
