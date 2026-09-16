from __future__ import annotations

import pytest

from markitdown.twoways._errors import RoundTripVerificationError
from markitdown.twoways.formats.png.verification import verify_png_candidate

from ._png_fixtures import make_png


def test_verifier_accepts_only_requested_text_value_change() -> None:
    source = make_png(text=(("Title", "Alpha"), ("Author", "Ada")))
    candidate = make_png(text=(("Title", "Beta title"), ("Author", "Ada")))

    verify_png_candidate(
        source,
        candidate,
        requested_values={1: ("Title", "Beta title")},
    )


def test_verifier_rejects_unrequested_text_chunk_drift() -> None:
    source = make_png(text=(("Title", "Alpha"), ("Author", "Ada")))
    candidate = make_png(text=(("Title", "Beta"), ("Author", "Mallory")))

    with pytest.raises(RoundTripVerificationError, match="unrequested"):
        verify_png_candidate(
            source,
            candidate,
            requested_values={1: ("Title", "Beta")},
        )


def test_verifier_rejects_chunk_type_or_order_drift() -> None:
    source = make_png(text=(("Title", "Alpha"),))
    candidate = make_png(
        text=(("Title", "Beta"),),
        ancillary=((b"pHYs", b"\x00" * 9),),
    )

    with pytest.raises(RoundTripVerificationError, match="topology"):
        verify_png_candidate(
            source,
            candidate,
            requested_values={1: ("Title", "Beta")},
        )
