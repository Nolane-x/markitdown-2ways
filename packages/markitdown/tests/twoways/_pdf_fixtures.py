from __future__ import annotations


def _pdf_literal(value: str) -> bytes:
    escaped = value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return f"({escaped})".encode("latin-1")


def _build_pdf(
    objects: dict[int, bytes],
    *,
    root: int = 1,
    info: int | None = 4,
) -> bytes:
    output = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(output)
        output.extend(f"{number} 0 obj\n".encode("ascii"))
        output.extend(objects[number])
        output.extend(b"\nendobj\n")

    size = max(objects) + 1
    xref_offset = len(output)
    output.extend(f"xref\n0 {size}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for number in range(1, size):
        if number in offsets:
            output.extend(f"{offsets[number]:010d} 00000 n \n".encode("ascii"))
        else:
            output.extend(b"0000000000 00000 f \n")
    info_entry = f" /Info {info} 0 R".encode("ascii") if info is not None else b""
    output.extend(
        b"trailer\n<< /Size "
        + str(size).encode("ascii")
        + b" /Root "
        + str(root).encode("ascii")
        + b" 0 R"
        + info_entry
        + b" >>\n"
    )
    output.extend(f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    return bytes(output)


def make_metadata_pdf(
    *,
    title: str = "Alpha",
    author: str = "Ada",
    subject: str = "Spec",
    keywords: str = "one,two",
    include_info: bool = True,
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
    return _build_pdf(objects, info=4 if include_info else None)


def _text_field_dictionary(
    *,
    field_name: str,
    value: str,
    field_flags: int,
    max_len: int | None,
    non_text_value: bool,
    with_ap: bool,
    with_aa: bool,
    with_action: bool,
    parent_ref: int | None = None,
    kids_ref: int | None = None,
    left: int = 72,
    uri_action_owner: bool = False,
) -> bytes:
    value_token = b"42" if non_text_value else _pdf_literal(value)
    pieces = [
        b"<< /FT /Tx /Subtype /Widget /T ",
        _pdf_literal(field_name),
        b" /V ",
        value_token,
        b" /Rect [",
        str(left).encode("ascii"),
        b" 700 ",
        str(left + 168).encode("ascii"),
        b" 724] /Ff ",
        str(field_flags).encode("ascii"),
    ]
    if max_len is not None:
        pieces.extend((b" /MaxLen ", str(max_len).encode("ascii")))
    if with_ap:
        pieces.append(b" /AP << /N 8 0 R >>")
    if with_aa:
        pieces.append(b" /AA << /K << /S /JavaScript /JS (blocked) >> >>")
    if with_action:
        pieces.append(b" /A << /S /JavaScript /JS (blocked) >>")
    if parent_ref is not None:
        pieces.extend((b" /Parent ", f"{parent_ref} 0 R".encode("ascii")))
    if kids_ref is not None:
        pieces.extend((b" /Kids [", f"{kids_ref} 0 R".encode("ascii"), b"]"))
    if uri_action_owner:
        pieces.append(b" /S /URI /URI (https://example.test/old)")
    pieces.append(b" >>")
    return b"".join(pieces)


def make_text_form_pdf(
    *,
    need_appearances: bool | None = True,
    value: str = "Alice",
    field_name: str = "customer.name",
    field_flags: int = 0,
    max_len: int | None = None,
    with_ap: bool = False,
    with_xfa: bool = False,
    with_co: bool = False,
    with_aa: bool = False,
    with_action: bool = False,
    with_parent: bool = False,
    with_kids: bool = False,
    direct_field: bool = False,
    duplicate_field_name: bool = False,
    duplicate_page_binding: bool = False,
    non_text_value: bool = False,
    second_field: bool = False,
    with_uri_link: bool = False,
    shared_link_owner: bool = False,
) -> bytes:
    """Build a deterministic classic-xref AcroForm fixture with explicit ownership."""

    field6 = _text_field_dictionary(
        field_name=field_name,
        value=value,
        field_flags=field_flags,
        max_len=max_len,
        non_text_value=non_text_value,
        with_ap=with_ap,
        with_aa=with_aa,
        with_action=with_action,
        parent_ref=10 if with_parent else None,
        kids_ref=10 if with_kids else None,
        uri_action_owner=shared_link_owner,
    )
    field7_name = field_name if duplicate_field_name else "customer.email"
    field7 = _text_field_dictionary(
        field_name=field7_name,
        value="a@example.test",
        field_flags=0,
        max_len=None,
        non_text_value=False,
        with_ap=False,
        with_aa=False,
        with_action=False,
        left=300,
    )

    annots = [b"6 0 R"]
    include_second = second_field or duplicate_field_name
    if include_second:
        annots.append(b"7 0 R")
    if duplicate_page_binding:
        annots.append(b"6 0 R")
    if with_uri_link or shared_link_owner:
        annots.append(b"11 0 R")

    if direct_field:
        fields_token = b"[" + field6 + b"]"
    elif with_parent:
        fields_token = b"[10 0 R]"
    else:
        roots = [b"6 0 R"]
        if include_second:
            roots.append(b"7 0 R")
        fields_token = b"[" + b" ".join(roots) + b"]"

    need_token = b""
    if need_appearances is not None:
        need_token = b" /NeedAppearances " + (b"true" if need_appearances else b"false")
    xfa_token = b" /XFA [(template) 9 0 R]" if with_xfa else b""
    co_token = b" /CO [6 0 R]" if with_co else b""
    acroform = (
        b"<< /Fields "
        + fields_token
        + need_token
        + b" /DA (/Helv 0 Tf 0 g)"
        + b" /DR << /Font << /Helv << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >>"
        + xfa_token
        + co_token
        + b" >>"
    )

    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R /AcroForm 5 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Annots ["
        + b" ".join(annots)
        + b"] >>",
        4: b"<< /Title (H11 fixture) /Author (Nolane) /Subject (AcroForm) /Keywords (h11) >>",
        5: acroform,
        6: field6,
    }
    if include_second:
        objects[7] = field7
    if with_ap:
        objects[8] = b"<< /Length 0 >>\nstream\n\nendstream"
    if with_xfa:
        objects[9] = b"<< /Length 0 >>\nstream\n\nendstream"
    if with_parent:
        objects[10] = b"<< /FT /Tx /T (parent) /Kids [6 0 R] >>"
    elif with_kids:
        objects[10] = b"<< /Subtype /Widget /Parent 6 0 R /Rect [72 700 240 724] >>"
    if with_uri_link or shared_link_owner:
        action = b"6 0 R" if shared_link_owner else b"<< /S /URI /URI (https://example.test/old) >>"
        objects[11] = (
            b"<< /Type /Annot /Subtype /Link /Rect [72 650 240 674] /A "
            + action
            + b" >>"
        )

    return _build_pdf(objects)
