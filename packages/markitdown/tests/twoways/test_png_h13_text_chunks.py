from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways.capabilities import CapabilityState, capabilities_for_node
from markitdown.twoways.formats.png import PngLimits, patch_png, read_png_ir
from markitdown.twoways.formats.png.parser import PngFormatError, parse_png
from markitdown.twoways.ir.edits import EditOperation

from ._png_fixtures import itxt_chunk, make_png, ztxt_chunk


def _insert_before_idat(source: bytes, *chunks: bytes) -> bytes:
    idat_offset = source.index(b"IDAT") - 4
    return source[:idat_offset] + b"".join(chunks) + source[idat_offset:]


def _node(document, keyword: str):
    return next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "png-text-metadata"
        and node.metadata.get("png.keyword") == keyword
    )


def _edit(document, keyword: str, value: str) -> EditOperation:
    node = _node(document, keyword)
    return EditOperation(
        operation_id=f"edit-{keyword}",
        type="update_png_text_metadata",
        target_node_id=node.node_id,
        payload={
            "keyword": keyword,
            "old_value": node.payload.text,
            "value": value,
        },
    )


def test_parser_discovers_ztxt_and_itxt_native_owners() -> None:
    source = make_png(
        text=(),
        ztext=(("Comment", "Caf\xe9"),),
        itext=(("Description", "Xin ch\xe0o \U0001f30d"),),
    )

    parsed = parse_png(source)
    owners = {owner.keyword: owner for owner in parsed.text_owners}

    assert owners["Comment"].chunk_type == "zTXt"
    assert owners["Comment"].value == "Caf\xe9"
    assert owners["Comment"].compression_method == 0
    assert owners["Description"].chunk_type == "iTXt"
    assert owners["Description"].value == "Xin ch\xe0o \U0001f30d"
    assert owners["Description"].compression_flag == 0
    assert owners["Description"].compression_method == 0


def test_itxt_parser_preserves_language_and_translated_keyword() -> None:
    source = _insert_before_idat(
        make_png(text=()),
        itxt_chunk(
            "Description",
            "N\u1ed9i dung",
            language_tag="vi-VN",
            translated_keyword="M\xf4 t\u1ea3",
        ),
    )

    owner = parse_png(source).text_owners[0]

    assert owner.chunk_type == "iTXt"
    assert owner.language_tag == "vi-VN"
    assert owner.translated_keyword == "M\xf4 t\u1ea3"
    assert owner.value == "N\u1ed9i dung"


def test_reader_projects_cross_type_text_owners() -> None:
    source = make_png(
        text=(("Title", "Alpha"),),
        ztext=(("Comment", "Compressed"),),
        itext=(("Description", "Qu\u1ed1c t\u1ebf"),),
    )

    document = read_png_ir(BytesIO(source), filename="mixed.png")
    nodes = {
        node.metadata["png.keyword"]: node
        for node in document.nodes.values()
        if node.semantic_role == "png-text-metadata"
    }

    assert set(nodes) == {"Title", "Comment", "Description"}
    assert nodes["Title"].metadata["png.chunk_type"] == "tEXt"
    assert nodes["Comment"].metadata["png.chunk_type"] == "zTXt"
    assert nodes["Description"].metadata["png.chunk_type"] == "iTXt"
    assert nodes["Description"].payload.text == "Qu\u1ed1c t\u1ebf"


def test_duplicate_keyword_across_text_chunk_types_is_read_only() -> None:
    source = make_png(
        text=(("Title", "Alpha"),),
        ztext=(("Title", "Beta"),),
    )

    document = read_png_ir(BytesIO(source), filename="duplicate.png")
    title_nodes = [
        node
        for node in document.nodes.values()
        if node.metadata.get("png.keyword") == "Title"
    ]

    assert len(title_nodes) == 2
    for node in title_nodes:
        decision = capabilities_for_node(node).for_operation("update_png_text_metadata")
        assert decision.state is CapabilityState.READ_ONLY
        assert decision.reason_code == "png.text.duplicate_keyword"


def test_ztxt_value_mutation_preserves_native_chunk_type() -> None:
    source = make_png(text=(), ztext=(("Comment", "Alpha"),))
    document = read_png_ir(BytesIO(source), filename="compressed.png")
    output = BytesIO()

    patch_png(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, "Comment", "Beta"),),
    )

    parsed = parse_png(output.getvalue())
    owner = parsed.text_owners[0]
    assert owner.chunk_type == "zTXt"
    assert owner.value == "Beta"
    assert owner.compression_method == 0


def test_itxt_unicode_mutation_preserves_language_and_compression_mode() -> None:
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
    output = BytesIO()

    patch_png(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, "Description", "Xin ch\xe0o \U0001f30d"),),
    )

    owner = parse_png(output.getvalue()).text_owners[0]
    assert owner.chunk_type == "iTXt"
    assert owner.compression_flag == 1
    assert owner.compression_method == 0
    assert owner.language_tag == "vi"
    assert owner.translated_keyword == "M\xf4 t\u1ea3"
    assert owner.value == "Xin ch\xe0o \U0001f30d"


def test_ztxt_invalid_zlib_stream_fails_closed() -> None:
    source = _insert_before_idat(
        make_png(text=()),
        ztxt_chunk("Comment", "unused", compressed_data=b"not-a-zlib-stream"),
    )

    with pytest.raises(PngFormatError, match="zlib"):
        parse_png(source)


def test_ztxt_trailing_compressed_bytes_fail_closed() -> None:
    source = _insert_before_idat(
        make_png(text=()),
        ztxt_chunk("Comment", "Alpha", trailing_data=b"trailing"),
    )

    with pytest.raises(PngFormatError, match="trailing"):
        parse_png(source)


def test_compressed_text_decompression_limit_fails_closed() -> None:
    source = make_png(text=(), ztext=(("Comment", "A" * 4096),))

    with pytest.raises(PngFormatError, match="decompression|text value"):
        parse_png(source, limits=PngLimits(max_text_value_bytes=64))


def test_itxt_invalid_language_tag_fails_closed() -> None:
    source = _insert_before_idat(
        make_png(text=()),
        itxt_chunk("Description", "Alpha", language_tag="en--US"),
    )

    with pytest.raises(PngFormatError, match="language tag"):
        parse_png(source)


def test_itxt_invalid_utf8_fails_closed() -> None:
    source = _insert_before_idat(
        make_png(text=()),
        itxt_chunk("Description", "", text_bytes=b"\xff"),
    )

    with pytest.raises(PngFormatError, match="UTF-8"):
        parse_png(source)
