from __future__ import annotations

from hashlib import sha256
import struct
import zlib

from .limits import PngLimits
from .model import ParsedPng, PngChunk, PngTextOwner

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_KNOWN_CRITICAL = frozenset({"IHDR", "PLTE", "IDAT", "IEND"})
_APNG_TYPES = frozenset({"acTL", "fcTL", "fdAT"})


class PngFormatError(ValueError):
    """Raised when strict PNG round-trip authority cannot be proven."""


def _valid_chunk_type(raw: bytes) -> bool:
    if len(raw) != 4:
        return False
    if not all(65 <= byte <= 90 or 97 <= byte <= 122 for byte in raw):
        return False
    # PNG reserves bit 5 of the third chunk-type byte; it must be uppercase/zero.
    return 65 <= raw[2] <= 90


def _valid_keyword(raw: bytes) -> bool:
    if not 1 <= len(raw) <= 79:
        return False
    if raw[0] == 32 or raw[-1] == 32 or b"  " in raw:
        return False
    return all(32 <= byte <= 126 or 161 <= byte <= 255 for byte in raw)


def _bounded_zlib_decompress(
    compressed: bytes,
    *,
    limit: int,
    label: str,
) -> bytes:
    try:
        decompressor = zlib.decompressobj()
        decoded = decompressor.decompress(compressed, limit + 1)
    except zlib.error as exc:
        raise PngFormatError(f"PNG {label} zlib stream is invalid") from exc

    if len(decoded) > limit or decompressor.unconsumed_tail:
        raise PngFormatError(f"PNG {label} text value exceeds decompression limit")
    if not decompressor.eof:
        raise PngFormatError(f"PNG {label} zlib stream is incomplete")
    if decompressor.unused_data:
        raise PngFormatError(f"PNG {label} zlib stream contains trailing bytes")
    return decoded


def _parse_text_owner(chunk: PngChunk) -> PngTextOwner:
    separator = chunk.data.find(b"\x00")
    if separator <= 0:
        raise PngFormatError("PNG tEXt chunk is missing a valid keyword separator")
    keyword_raw = chunk.data[:separator]
    value_raw = chunk.data[separator + 1 :]
    if not _valid_keyword(keyword_raw):
        raise PngFormatError("PNG tEXt keyword is invalid")
    if b"\x00" in value_raw:
        raise PngFormatError("PNG tEXt value contains an unsupported NUL byte")
    return PngTextOwner(
        chunk_index=chunk.index,
        chunk_type="tEXt",
        keyword=keyword_raw.decode("latin-1"),
        value=value_raw.decode("latin-1"),
        raw_sha256=chunk.raw_sha256,
        data_sha256=chunk.data_sha256,
    )


def _parse_ztxt_owner(chunk: PngChunk, *, limits: PngLimits) -> PngTextOwner:
    separator = chunk.data.find(b"\x00")
    if separator <= 0:
        raise PngFormatError("PNG zTXt chunk is missing a valid keyword separator")
    keyword_raw = chunk.data[:separator]
    remainder = chunk.data[separator + 1 :]
    if not _valid_keyword(keyword_raw):
        raise PngFormatError("PNG zTXt keyword is invalid")
    if len(remainder) < 1:
        raise PngFormatError("PNG zTXt chunk is missing compression method")

    compression_method = remainder[0]
    if compression_method != 0:
        raise PngFormatError("PNG zTXt compression method is unsupported")
    value_raw = _bounded_zlib_decompress(
        remainder[1:],
        limit=limits.max_text_value_bytes,
        label="zTXt",
    )
    if b"\x00" in value_raw:
        raise PngFormatError("PNG zTXt value contains an unsupported NUL byte")
    return PngTextOwner(
        chunk_index=chunk.index,
        chunk_type="zTXt",
        keyword=keyword_raw.decode("latin-1"),
        value=value_raw.decode("latin-1"),
        raw_sha256=chunk.raw_sha256,
        data_sha256=chunk.data_sha256,
        compression_method=compression_method,
    )


def _valid_language_tag(raw: bytes) -> bool:
    if not raw:
        return True
    try:
        language_tag = raw.decode("ascii")
    except UnicodeDecodeError:
        return False
    parts = language_tag.split("-")
    return all(
        1 <= len(part) <= 8
        and all(
            "A" <= character <= "Z"
            or "a" <= character <= "z"
            or "0" <= character <= "9"
            for character in part
        )
        for part in parts
    )


def _decode_itxt_utf8(raw: bytes, *, field: str) -> str:
    if b"\x00" in raw:
        raise PngFormatError(f"PNG iTXt {field} contains an unsupported NUL byte")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PngFormatError(f"PNG iTXt {field} is not valid UTF-8") from exc


def _parse_itxt_owner(chunk: PngChunk, *, limits: PngLimits) -> PngTextOwner:
    keyword_end = chunk.data.find(b"\x00")
    if keyword_end <= 0:
        raise PngFormatError("PNG iTXt chunk is missing a valid keyword separator")
    keyword_raw = chunk.data[:keyword_end]
    if not _valid_keyword(keyword_raw):
        raise PngFormatError("PNG iTXt keyword is invalid")

    remainder = chunk.data[keyword_end + 1 :]
    if len(remainder) < 2:
        raise PngFormatError("PNG iTXt chunk is missing compression fields")
    compression_flag = remainder[0]
    compression_method = remainder[1]
    if compression_flag not in (0, 1):
        raise PngFormatError("PNG iTXt compression flag is invalid")
    if compression_method != 0:
        raise PngFormatError("PNG iTXt compression method is unsupported")

    remainder = remainder[2:]
    language_end = remainder.find(b"\x00")
    if language_end < 0:
        raise PngFormatError("PNG iTXt chunk is missing language tag separator")
    language_raw = remainder[:language_end]
    if not _valid_language_tag(language_raw):
        raise PngFormatError("PNG iTXt language tag is invalid")

    remainder = remainder[language_end + 1 :]
    translated_end = remainder.find(b"\x00")
    if translated_end < 0:
        raise PngFormatError("PNG iTXt chunk is missing translated keyword separator")
    translated_raw = remainder[:translated_end]
    translated_keyword = _decode_itxt_utf8(
        translated_raw,
        field="translated keyword",
    )
    text_raw = remainder[translated_end + 1 :]
    if compression_flag == 1:
        text_raw = _bounded_zlib_decompress(
            text_raw,
            limit=limits.max_text_value_bytes,
            label="iTXt",
        )
    elif len(text_raw) > limits.max_text_value_bytes:
        raise PngFormatError(
            "PNG iTXt text value exceeds the configured text value limit"
        )
    value = _decode_itxt_utf8(text_raw, field="text")

    language_tag = language_raw.decode("ascii")
    return PngTextOwner(
        chunk_index=chunk.index,
        chunk_type="iTXt",
        keyword=keyword_raw.decode("latin-1"),
        value=value,
        raw_sha256=chunk.raw_sha256,
        data_sha256=chunk.data_sha256,
        compression_method=compression_method,
        compression_flag=compression_flag,
        language_tag=language_tag,
        translated_keyword=translated_keyword,
        language_tag_sha256=sha256(language_raw).hexdigest(),
        translated_keyword_sha256=sha256(translated_raw).hexdigest(),
    )


def parse_png(data: bytes, *, limits: PngLimits | None = None) -> ParsedPng:
    limits = limits or PngLimits()
    if not isinstance(data, bytes):
        data = bytes(data)
    if len(data) > limits.max_source_bytes:
        raise PngFormatError("PNG source exceeds the configured source limit")
    if not data.startswith(PNG_SIGNATURE):
        raise PngFormatError("PNG signature is invalid")

    chunks: list[PngChunk] = []
    text_owners: list[PngTextOwner] = []
    offset = len(PNG_SIGNATURE)
    saw_ihdr = False
    saw_iend = False
    saw_idat = False
    idat_closed = False
    saw_plte = False
    is_apng = False

    while offset < len(data):
        if len(chunks) >= limits.max_chunks:
            raise PngFormatError("PNG chunk count exceeds the configured limit")
        if len(data) - offset < 12:
            raise PngFormatError("PNG chunk framing is truncated")

        length = struct.unpack(">I", data[offset : offset + 4])[0]
        if length > limits.max_chunk_data_bytes:
            raise PngFormatError("PNG chunk data exceeds the configured chunk limit")
        chunk_type_raw = data[offset + 4 : offset + 8]
        if not _valid_chunk_type(chunk_type_raw):
            raise PngFormatError("PNG chunk type or reserved bit is invalid")
        chunk_type = chunk_type_raw.decode("ascii")
        data_start = offset + 8
        data_end = data_start + length
        end = data_end + 4
        if data_end < data_start or end < data_end or end > len(data):
            raise PngFormatError("PNG chunk declared length exceeds source boundaries")

        chunk_data = data[data_start:data_end]
        stored_crc = struct.unpack(">I", data[data_end:end])[0]
        computed_crc = zlib.crc32(chunk_type_raw)
        computed_crc = zlib.crc32(chunk_data, computed_crc) & 0xFFFFFFFF
        if stored_crc != computed_crc:
            raise PngFormatError(
                f"PNG chunk CRC mismatch at index {len(chunks)} ({chunk_type})"
            )

        raw = data[offset:end]
        chunk = PngChunk(
            index=len(chunks),
            chunk_type=chunk_type,
            length=length,
            start=offset,
            end=end,
            data_start=data_start,
            data_end=data_end,
            stored_crc=stored_crc,
            computed_crc=computed_crc,
            raw_sha256=sha256(raw).hexdigest(),
            data_sha256=sha256(chunk_data).hexdigest(),
            raw=raw,
            data=chunk_data,
        )

        is_critical = 65 <= chunk_type_raw[0] <= 90
        if is_critical and chunk_type not in _KNOWN_CRITICAL:
            raise PngFormatError(
                f"PNG contains unsupported critical chunk {chunk_type}"
            )

        if not saw_ihdr:
            if chunk_type != "IHDR" or length != 13:
                raise PngFormatError("PNG IHDR must be the first chunk with length 13")
            saw_ihdr = True
        elif chunk_type == "IHDR":
            raise PngFormatError("PNG contains more than one IHDR chunk")

        if chunk_type == "PLTE":
            if saw_plte:
                raise PngFormatError("PNG contains more than one PLTE chunk")
            if saw_idat:
                raise PngFormatError("PNG PLTE appears after IDAT")
            saw_plte = True
        elif chunk_type == "IDAT":
            if idat_closed:
                raise PngFormatError("PNG IDAT chunks are not consecutive")
            saw_idat = True
        elif saw_idat and chunk_type != "IEND":
            idat_closed = True

        if chunk_type in _APNG_TYPES:
            is_apng = True

        chunks.append(chunk)
        if chunk_type == "tEXt":
            text_owners.append(_parse_text_owner(chunk))
        elif chunk_type == "zTXt":
            text_owners.append(_parse_ztxt_owner(chunk, limits=limits))
        elif chunk_type == "iTXt":
            text_owners.append(_parse_itxt_owner(chunk, limits=limits))

        offset = end
        if chunk_type == "IEND":
            if length != 0:
                raise PngFormatError("PNG IEND must have zero data length")
            saw_iend = True
            if offset != len(data):
                raise PngFormatError("PNG contains trailing bytes after IEND")
            break

    if not saw_ihdr:
        raise PngFormatError("PNG is missing IHDR")
    if not saw_idat:
        raise PngFormatError("PNG is missing IDAT")
    if not saw_iend:
        raise PngFormatError("PNG is missing IEND")

    return ParsedPng(
        source_size=len(data),
        chunks=tuple(chunks),
        text_owners=tuple(text_owners),
        is_apng=is_apng,
    )
