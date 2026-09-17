from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import zlib

import pytest

from markitdown.twoways._errors import PatchPreconditionError, UnsupportedEditError
from markitdown.twoways.capabilities import (
    CAPABILITY_METADATA_KEY,
    CapabilityDecision,
    CapabilityState,
    encode_capabilities,
)
from markitdown.twoways.formats.png import patch_png, read_png_ir
from markitdown.twoways.formats.png.parser import PngFormatError, parse_png
from markitdown.twoways.ir.edits import EditOperation

from ._png_fixtures import itxt_chunk, make_png, png_chunk, ztxt_chunk


def _insert_before_idat(source: bytes, chunk: bytes) -> bytes:
    idat_offset = source.index(b"IDAT") - 4
    return source[:idat_offset] + chunk + source[idat_offset:]


def _node(document, keyword: str, *, chunk_type: str | None = None):
    return next(
        node
        for node in document.nodes.values()
        if node.metadata.get("png.keyword") == keyword
        and (chunk_type is None or node.metadata.get("png.chunk_type") == chunk_type)
    )


def _edit(node, value: str) -> EditOperation:
    return EditOperation(
        operation_id="edit",
        type="update_png_text_metadata",
        target_node_id=node.node_id,
        payload={
            "keyword": node.metadata["png.keyword"],
            "old_value": node.payload.text,
            "value": value,
        },
    )


def _force_writable(document, node):
    writable = encode_capabilities(
        (
            CapabilityDecision(
                operation="update_png_text_metadata",
                state=CapabilityState.WRITABLE,
            ),
        )
    )
    forged_node = replace(
        node,
        metadata={**node.metadata, CAPABILITY_METADATA_KEY: writable},
    )
    return replace(document, nodes={**document.nodes, node.node_id: forged_node})


def test_ztxt_unsupported_compression_method_fails_closed() -> None:
    source = _insert_before_idat(
        make_png(text=()),
        ztxt_chunk("Comment", "Alpha", compression_method=1),
    )

    with pytest.raises(PngFormatError, match="compression method"):
        parse_png(source)


def test_ztxt_incomplete_zlib_stream_fails_closed() -> None:
    compressed = zlib.compress(b"Alpha")[:-1]
    source = _insert_before_idat(
        make_png(text=()),
        ztxt_chunk("Comment", "unused", compressed_data=compressed),
    )

    with pytest.raises(PngFormatError, match="incomplete"):
        parse_png(source)


def test_itxt_invalid_compression_flag_fails_closed() -> None:
    data = b"Description\x00" + bytes((2, 0)) + b"en\x00Description\x00Alpha"
    source = _insert_before_idat(make_png(text=()), png_chunk(b"iTXt", data))

    with pytest.raises(PngFormatError, match="compression flag"):
        parse_png(source)


def test_itxt_unsupported_compression_method_fails_closed() -> None:
    data = b"Description\x00" + bytes((0, 1)) + b"en\x00Description\x00Alpha"
    source = _insert_before_idat(make_png(text=()), png_chunk(b"iTXt", data))

    with pytest.raises(PngFormatError, match="compression method"):
        parse_png(source)


def test_itxt_invalid_translated_keyword_utf8_fails_closed() -> None:
    data = b"Description\x00\x00\x00en\x00\xff\x00Alpha"
    source = _insert_before_idat(make_png(text=()), png_chunk(b"iTXt", data))

    with pytest.raises(PngFormatError, match="translated keyword.*UTF-8"):
        parse_png(source)


def test_compressed_itxt_trailing_zlib_bytes_fail_closed() -> None:
    compressed = zlib.compress("Alpha".encode("utf-8")) + b"trailing"
    source = _insert_before_idat(
        make_png(text=()),
        itxt_chunk(
            "Description",
            "unused",
            compressed=True,
            text_bytes=compressed,
        ),
    )

    with pytest.raises(PngFormatError, match="trailing"):
        parse_png(source)


def test_forged_writable_cannot_bypass_cross_type_duplicate_policy() -> None:
    source = make_png(
        text=(("Title", "Alpha"),),
        ztext=(("Title", "Beta"),),
    )
    document = read_png_ir(BytesIO(source), filename="duplicate.png")
    node = _node(document, "Title", chunk_type="tEXt")
    document = _force_writable(document, node)
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="duplicate keyword"):
        patch_png(
            document,
            BytesIO(source),
            output,
            edits=(_edit(node, "Gamma"),),
        )

    assert output.getvalue() == b""


def test_forged_itxt_immutable_metadata_fails_without_output() -> None:
    source = _insert_before_idat(
        make_png(text=()),
        itxt_chunk(
            "Description",
            "Alpha",
            compressed=True,
            language_tag="vi",
            translated_keyword="M\xf4 t\u1ea3",
        ),
    )
    document = read_png_ir(BytesIO(source), filename="international.png")
    node = _node(document, "Description")
    forged_node = replace(
        node,
        metadata={**node.metadata, "png.language_tag": "en"},
    )
    forged_document = replace(
        document,
        nodes={**document.nodes, node.node_id: forged_node},
    )
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="immutable native evidence"):
        patch_png(
            forged_document,
            BytesIO(source),
            output,
            edits=(_edit(forged_node, "Beta"),),
        )

    assert output.getvalue() == b""


def test_mixed_text_edit_preserves_every_unrequested_raw_chunk() -> None:
    source = make_png(
        text=(("Title", "Alpha"),),
        ztext=(("Comment", "Compressed"),),
        itext=(("Description", "Qu\u1ed1c t\u1ebf"),),
        ancillary=((b"pHYs", b"\x00" * 9),),
    )
    document = read_png_ir(BytesIO(source), filename="mixed.png")
    node = _node(document, "Comment")
    target_index = node.metadata["png.chunk_index"]
    output = BytesIO()

    patch_png(
        document,
        BytesIO(source),
        output,
        edits=(_edit(node, "Short"),),
    )

    before = parse_png(source)
    after = parse_png(output.getvalue())
    for source_chunk, candidate_chunk in zip(before.chunks, after.chunks):
        if source_chunk.index != target_index:
            assert candidate_chunk.raw == source_chunk.raw
