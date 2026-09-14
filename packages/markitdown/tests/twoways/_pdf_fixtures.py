from __future__ import annotations


def _pdf_literal(value: str) -> bytes:
    escaped = value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return f"({escaped})".encode("latin-1")


def make_metadata_pdf(
    *,
    title: str = "Alpha",
    author: str = "Ada",
    subject: str = "Spec",
    keywords: str = "one,two",
) -> bytes:
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>",
        4: b"<< /Title "
        + _pdf_literal(title)
        + b" /Author "
        + _pdf_literal(author)
        + b" /Subject "
        + _pdf_literal(subject)
        + b" /Keywords "
        + _pdf_literal(keywords)
        + b" >>",
    }

    output = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(output)
        output.extend(f"{number} 0 obj\n".encode("ascii"))
        output.extend(objects[number])
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(b"xref\n0 5\n")
    output.extend(b"0000000000 65535 f \n")
    for number in range(1, 5):
        output.extend(f"{offsets[number]:010d} 00000 n \n".encode("ascii"))
    output.extend(b"trailer\n<< /Size 5 /Root 1 0 R /Info 4 0 R >>\n")
    output.extend(f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    return bytes(output)
