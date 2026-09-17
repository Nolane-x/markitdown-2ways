from __future__ import annotations

import struct
import zlib

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type)
    crc = zlib.crc32(data, crc) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def text_chunk(keyword: str, value: str) -> bytes:
    return png_chunk(
        b"tEXt",
        keyword.encode("latin-1") + b"\x00" + value.encode("latin-1"),
    )


def make_png(
    *,
    text: tuple[tuple[str, str], ...] = (("Title", "Alpha"),),
    ancillary: tuple[tuple[bytes, bytes], ...] = (),
    apng: bool = False,
) -> bytes:
    # 1x1 true-colour, 8-bit PNG. One scanline: filter byte + RGB pixel.
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    chunks = [png_chunk(b"IHDR", ihdr)]
    if apng:
        chunks.append(png_chunk(b"acTL", struct.pack(">II", 1, 0)))
    chunks.extend(text_chunk(keyword, value) for keyword, value in text)
    chunks.extend(png_chunk(chunk_type, data) for chunk_type, data in ancillary)
    chunks.append(png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00")))
    chunks.append(png_chunk(b"IEND", b""))
    return PNG_SIGNATURE + b"".join(chunks)


def corrupt_first_text_crc(source: bytes) -> bytes:
    marker = source.index(b"tEXt")
    length_offset = marker - 4
    length = struct.unpack(">I", source[length_offset:marker])[0]
    crc_offset = marker + 4 + length
    candidate = bytearray(source)
    candidate[crc_offset] ^= 0x01
    return bytes(candidate)
