from __future__ import annotations

from collections.abc import Mapping

from ..._errors import RoundTripVerificationError
from .model import ParsedIpynbSource
from .parser import IpynbParseError, parse_ipynb_source


def _fail(reason: str, *, expected: object = None, actual: object = None) -> None:
    details = {"reason": reason}
    if expected is not None:
        details["expected"] = expected
    if actual is not None:
        details["actual"] = actual
    raise RoundTripVerificationError(
        "IPYNB candidate failed notebook-semantic verification.",
        details=details,
    )


def verify_ipynb_candidate(
    original: ParsedIpynbSource,
    candidate: bytes,
    *,
    encoding: str,
    requested: Mapping[int, str],
) -> None:
    try:
        reread = parse_ipynb_source(candidate, encoding=encoding)
    except (IpynbParseError, TypeError, ValueError, UnicodeError) as exc:
        raise RoundTripVerificationError(
            "IPYNB candidate could not be re-read strictly.",
            details={"reason": "ipynb.candidate_reread_failed"},
        ) from exc

    original_representation = (
        original.representation.encoding,
        original.representation.bom,
        original.representation.byte_roundtrip,
    )
    candidate_representation = (
        reread.representation.encoding,
        reread.representation.bom,
        reread.representation.byte_roundtrip,
    )
    if candidate_representation != original_representation:
        _fail(
            "ipynb.candidate_representation",
            expected=original_representation,
            actual=candidate_representation,
        )

    if not reread.writable_version:
        _fail(
            "ipynb.candidate_nbformat_support",
            expected=True,
            actual=False,
        )
    if (reread.nbformat, reread.nbformat_minor) != (
        original.nbformat,
        original.nbformat_minor,
    ):
        _fail(
            "ipynb.candidate_nbformat",
            expected=(original.nbformat, original.nbformat_minor),
            actual=(reread.nbformat, reread.nbformat_minor),
        )
    if reread.top_level_non_cells_digest != original.top_level_non_cells_digest:
        _fail(
            "ipynb.candidate_top_level_non_cells",
            expected=original.top_level_non_cells_digest,
            actual=reread.top_level_non_cells_digest,
        )
    if len(reread.cells) != len(original.cells):
        _fail(
            "ipynb.candidate_cell_count",
            expected=len(original.cells),
            actual=len(reread.cells),
        )

    valid_indices = {cell.index for cell in original.cells}
    unknown_requested = sorted(set(requested) - valid_indices)
    if unknown_requested:
        _fail(
            "ipynb.candidate_unknown_requested_cell",
            expected=tuple(sorted(valid_indices)),
            actual=tuple(unknown_requested),
        )

    for original_cell, candidate_cell in zip(
        original.cells,
        reread.cells,
        strict=True,
    ):
        if candidate_cell.index != original_cell.index:
            _fail(
                "ipynb.candidate_cell_order",
                expected=original_cell.index,
                actual=candidate_cell.index,
            )
        if candidate_cell.cell_type != original_cell.cell_type:
            _fail(
                "ipynb.candidate_cell_type",
                expected=original_cell.cell_type,
                actual=candidate_cell.cell_type,
            )
        if candidate_cell.cell_id != original_cell.cell_id:
            _fail(
                "ipynb.candidate_cell_id",
                expected=original_cell.cell_id,
                actual=candidate_cell.cell_id,
            )
        if candidate_cell.non_source_digest != original_cell.non_source_digest:
            _fail(
                "ipynb.candidate_non_source_digest",
                expected=original_cell.non_source_digest,
                actual=candidate_cell.non_source_digest,
            )
        if candidate_cell.source_representation != original_cell.source_representation:
            _fail(
                "ipynb.candidate_source_representation",
                expected=original_cell.source_representation,
                actual=candidate_cell.source_representation,
            )
        if len(candidate_cell.source_segment_pointers) != len(
            original_cell.source_segment_pointers
        ):
            _fail(
                "ipynb.candidate_source_cardinality",
                expected=len(original_cell.source_segment_pointers),
                actual=len(candidate_cell.source_segment_pointers),
            )

        if original_cell.index in requested:
            expected_source = requested[original_cell.index]
            if candidate_cell.logical_source != expected_source:
                _fail(
                    "ipynb.candidate_requested_source",
                    expected=expected_source,
                    actual=candidate_cell.logical_source,
                )
            continue

        if candidate_cell.logical_source != original_cell.logical_source:
            _fail(
                "ipynb.candidate_unrequested_source",
                expected=original_cell.logical_source,
                actual=candidate_cell.logical_source,
            )
        if (
            candidate_cell.source_segment_raw_digests
            != original_cell.source_segment_raw_digests
        ):
            _fail(
                "ipynb.candidate_unrequested_source_raw",
                expected=original_cell.source_segment_raw_digests,
                actual=candidate_cell.source_segment_raw_digests,
            )
