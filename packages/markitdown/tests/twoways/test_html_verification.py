from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways._errors import RoundTripVerificationError
from markitdown.twoways.formats.html.reader import read_html_ir
from markitdown.twoways.formats.html.verification import verify_html_candidate
from markitdown.twoways.formats.text.model import TextRepresentation


def _representation(document) -> TextRepresentation:
    root = document.nodes[document.root_node_ids[0]]
    return TextRepresentation(
        encoding=root.metadata["html.encoding"],
        bom=root.metadata["html.bom"],
        newline="mixed",
        byte_roundtrip=root.metadata["html.byte_roundtrip"],
    )


def _verify(source: bytes, candidate: bytes, requested: dict[str, str]) -> None:
    document = read_html_ir(
        BytesIO(source),
        filename="page.html",
        mimetype="text/html",
    )
    verify_html_candidate(
        document,
        candidate,
        _representation(document),
        requested,
    )


def test_candidate_verifier_accepts_only_requested_scalar_changes() -> None:
    source = b'<html><body><p class="x">old</p><div>A&amp;B</div></body></html>'
    candidate = (
        b'<html><body><p class="new">changed</p><div>A&amp;B</div></body></html>'
    )

    _verify(
        source,
        candidate,
        {
            "/html[1]/body[1]/p[1]/@class": "new",
            "/html[1]/body[1]/p[1]/#text[1]": "changed",
        },
    )


def test_candidate_added_or_removed_lexical_path_is_rejected() -> None:
    source = b"<html><body><p>old</p><div>stay</div></body></html>"
    candidate = b"<html><body><p>new</p><div>stay</div><em>x</em></body></html>"

    with pytest.raises(RoundTripVerificationError):
        _verify(
            source,
            candidate,
            {"/html[1]/body[1]/p[1]/#text[1]": "new"},
        )


def test_candidate_tag_name_drift_is_rejected() -> None:
    source = b"<html><body><p>old</p></body></html>"
    candidate = b"<html><body><section>new</section></body></html>"

    with pytest.raises(RoundTripVerificationError):
        _verify(
            source,
            candidate,
            {"/html[1]/body[1]/p[1]/#text[1]": "new"},
        )


def test_candidate_parent_child_reorder_is_rejected() -> None:
    source = b"<html><body><p>old</p><div>stay</div></body></html>"
    candidate = b"<html><body><div>stay</div><p>new</p></body></html>"

    with pytest.raises(RoundTripVerificationError):
        _verify(
            source,
            candidate,
            {"/html[1]/body[1]/p[1]/#text[1]": "new"},
        )


def test_candidate_quote_style_drift_is_rejected() -> None:
    source = b'<html><body><p class="x">old</p></body></html>'
    candidate = b"<html><body><p class='x'>new</p></body></html>"

    with pytest.raises(RoundTripVerificationError):
        _verify(
            source,
            candidate,
            {"/html[1]/body[1]/p[1]/#text[1]": "new"},
        )


def test_candidate_recovery_signature_drift_is_rejected() -> None:
    source = b"<html><body><div><p>old</p></div></body></html>"
    candidate = b"<html><body><div><p>new<div>x</div></div></body></html>"

    with pytest.raises(RoundTripVerificationError):
        _verify(
            source,
            candidate,
            {"/html[1]/body[1]/div[1]/p[1]/#text[1]": "new"},
        )


def test_candidate_requested_semantic_mismatch_is_rejected() -> None:
    source = b"<html><body><p>old</p></body></html>"
    candidate = b"<html><body><p>wrong</p></body></html>"

    with pytest.raises(RoundTripVerificationError):
        _verify(
            source,
            candidate,
            {"/html[1]/body[1]/p[1]/#text[1]": "expected"},
        )


def test_candidate_unrequested_reference_spelling_drift_is_rejected() -> None:
    source = b"<html><body><p>old</p><div>A&amp;B</div></body></html>"
    candidate = b"<html><body><p>new</p><div>A&#38;B</div></body></html>"

    with pytest.raises(RoundTripVerificationError):
        _verify(
            source,
            candidate,
            {"/html[1]/body[1]/p[1]/#text[1]": "new"},
        )


def test_candidate_encoding_declaration_raw_drift_is_rejected() -> None:
    source = (
        b'<html><head><meta charset="utf-8"></head>' b"<body><p>old</p></body></html>"
    )
    candidate = (
        b'<html><head><meta charset="UTF-8"></head>' b"<body><p>new</p></body></html>"
    )

    with pytest.raises(RoundTripVerificationError):
        _verify(
            source,
            candidate,
            {"/html[1]/body[1]/p[1]/#text[1]": "new"},
        )
