from __future__ import annotations

from collections.abc import Mapping
import re


PdfInfoValue = str | bytes


def _pdf_literal(value: str) -> bytes:
    escaped = (
        value.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )
    return b"(" + escaped.encode("ascii") + b")"


def _info_dictionary(info: Mapping[str, PdfInfoValue]) -> bytes:
    parts = [b"<<"]
    for key in sorted(info):
        value = info[key]
        raw = value if isinstance(value, bytes) else _pdf_literal(value)
        parts.extend((b"/" + key.encode("ascii"), raw))
    parts.append(b">>")
    return b" ".join(parts)


def _xref_entry(offset: int, generation: int, status: str) -> bytes:
    return f"{offset:010d} {generation:05d} {status} \n".encode("ascii")


def _last_startxref(source: bytes) -> int:
    matches = tuple(re.finditer(rb"startxref\s+(\d+)\s+%%EOF\s*$", source))
    if not matches:
        raise ValueError("fixture source has no terminal startxref")
    return int(matches[-1].group(1))


def make_classic_pdf(
    *,
    info: Mapping[str, PdfInfoValue] | None = None,
    document_id_raw: bytes | None = None,
    catalog_extra: bytes = b"",
    trailer_extra: bytes = b"",
) -> bytes:
    """Build a tiny classic-xref PDF whose offsets are calculated from emitted bytes."""
    out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}

    def emit_object(number: int, body: bytes) -> None:
        offsets[number] = len(out)
        out.extend(f"{number} 0 obj\n".encode("ascii"))
        out.extend(body)
        out.extend(b"\nendobj\n")

    catalog_body = b"<< /Type /Catalog /Pages 2 0 R"
    if catalog_extra:
        catalog_body += b" " + catalog_extra.strip()
    catalog_body += b" >>"
    emit_object(1, catalog_body)
    emit_object(2, b"<< /Type /Pages /Kids [] /Count 0 >>")
    if info is not None:
        emit_object(3, _info_dictionary(info))

    size = 4 if info is not None else 3
    xref_offset = len(out)
    out.extend(f"xref\n0 {size}\n".encode("ascii"))
    out.extend(_xref_entry(0, 65535, "f"))
    for number in range(1, size):
        out.extend(_xref_entry(offsets[number], 0, "n"))

    trailer_parts = [f"/Size {size}".encode("ascii"), b"/Root 1 0 R"]
    if info is not None:
        trailer_parts.append(b"/Info 3 0 R")
    if document_id_raw is not None:
        trailer_parts.extend((b"/ID", document_id_raw))
    if trailer_extra:
        trailer_parts.append(trailer_extra.strip())
    out.extend(b"trailer\n<< " + b" ".join(trailer_parts) + b" >>\n")
    out.extend(f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    return bytes(out)


def append_classic_revision(
    source: bytes,
    *,
    info_updates: Mapping[str, PdfInfoValue],
    document_id_raw: bytes | None = None,
    trailer_extra: bytes = b"",
) -> bytes:
    """Append a valid revision replacing object 3 as the effective Info dictionary."""
    previous_xref = _last_startxref(source)
    out = bytearray(source)
    if out and out[-1] not in b"\x00\t\n\x0c\r ":
        out.extend(b"\n")

    info_offset = len(out)
    out.extend(b"3 0 obj\n")
    out.extend(_info_dictionary(info_updates))
    out.extend(b"\nendobj\n")

    xref_offset = len(out)
    out.extend(b"xref\n3 1\n")
    out.extend(_xref_entry(info_offset, 0, "n"))
    trailer_parts = [
        b"/Size 4",
        b"/Root 1 0 R",
        b"/Info 3 0 R",
        f"/Prev {previous_xref}".encode("ascii"),
    ]
    if document_id_raw is not None:
        trailer_parts.extend((b"/ID", document_id_raw))
    if trailer_extra:
        trailer_parts.append(trailer_extra.strip())
    out.extend(b"trailer\n<< " + b" ".join(trailer_parts) + b" >>\n")
    out.extend(f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    return bytes(out)


def append_free_info_revision(source: bytes) -> bytes:
    """Append a revision whose newest xref authority frees object 3."""
    previous_xref = _last_startxref(source)
    out = bytearray(source)
    if out and out[-1] not in b"\x00\t\n\x0c\r ":
        out.extend(b"\n")
    xref_offset = len(out)
    out.extend(b"xref\n3 1\n")
    out.extend(_xref_entry(0, 1, "f"))
    out.extend(
        b"trailer\n<< /Size 4 /Root 1 0 R /Info 3 0 R /Prev "
        + str(previous_xref).encode("ascii")
        + b" >>\n"
    )
    out.extend(f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    return bytes(out)
