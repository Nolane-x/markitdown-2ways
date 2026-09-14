from __future__ import annotations

from io import BytesIO

from pypdf import PdfWriter


def make_metadata_pdf(
    *,
    title: str = "Alpha",
    author: str = "Ada",
    subject: str = "Spec",
    keywords: str = "one,two",
) -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_metadata(
        {
            "/Title": title,
            "/Author": author,
            "/Subject": subject,
            "/Keywords": keywords,
        }
    )
    writer.write(output)
    return output.getvalue()
