from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo


CONTAINER_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""

XHTML = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:svg="http://www.w3.org/2000/svg" xmlns:m="http://www.w3.org/1998/Math/MathML">
  <head><title>Chapter</title><style>.x { color: red; }</style></head>
  <body><p>Hello <span>world</span></p><script>blocked()</script><svg:svg><svg:text>vector</svg:text></svg:svg><m:math><m:mi>x</m:mi></m:math></body>
</html>"""

NAV_XHTML = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Nav</title></head><body><nav epub:type="toc"><ol><li><a href="chapter.xhtml">Chapter One</a></li></ol></nav></body></html>"""


def _opf(
    *,
    version: str = "3.0",
    duplicate_manifest_id: bool = False,
    broken_spine: bool = False,
) -> bytes:
    second_id = "chapter" if duplicate_manifest_id else "nav"
    spine_id = "missing" if broken_spine else "chapter"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/" version="{version}" unique-identifier="book-id">
  <metadata>
    <dc:identifier id="book-id">urn:uuid:book-1</dc:identifier>
    <dc:title>Demo Book</dc:title>
    <dc:creator>Author One</dc:creator>
    <dc:language>en</dc:language>
    <meta property="dcterms:modified">2026-09-13T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
    <item id="{second_id}" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="style" href="style.css" media-type="text/css"/>
    <item id="cover" href="cover.png" media-type="image/png"/>
  </manifest>
  <spine><itemref idref="{spine_id}"/></spine>
</package>""".encode(
        "utf-8"
    )


def _zip_info(name: str, *, compression: int, extra: bytes = b"") -> ZipInfo:
    info = ZipInfo(name, date_time=(2026, 9, 13, 0, 0, 0))
    # ZipInfo normalizes backslashes to "/" on Windows. Restore the raw
    # fixture spelling so unsafe member-path tests stay cross-platform.
    info.filename = name
    info.orig_filename = name
    info.compress_type = compression
    info.extra = extra
    return info


def make_epub(
    *,
    version: str = "3.0",
    multiple_rootfiles: bool = False,
    duplicate_manifest_id: bool = False,
    broken_spine: bool = False,
    mimetype_first: bool = True,
    mimetype_compression: int = ZIP_STORED,
    mimetype_extra: bytes = b"",
    mimetype_payload: bytes = b"application/epub+zip",
    extra_members: dict[str, bytes] | None = None,
) -> bytes:
    container = CONTAINER_XML
    if multiple_rootfiles:
        container = container.replace(
            b"</rootfiles>",
            b'<rootfile full-path="OEBPS/alternate.opf" media-type="application/oebps-package+xml"/></rootfiles>',
        )

    members: list[tuple[ZipInfo, bytes]] = [
        (_zip_info("META-INF/container.xml", compression=ZIP_DEFLATED), container),
        (
            _zip_info("OEBPS/content.opf", compression=ZIP_DEFLATED),
            _opf(
                version=version,
                duplicate_manifest_id=duplicate_manifest_id,
                broken_spine=broken_spine,
            ),
        ),
        (_zip_info("OEBPS/chapter.xhtml", compression=ZIP_DEFLATED), XHTML),
        (_zip_info("OEBPS/nav.xhtml", compression=ZIP_DEFLATED), NAV_XHTML),
        (
            _zip_info("OEBPS/style.css", compression=ZIP_DEFLATED),
            b"body { margin: 1em; }",
        ),
        (_zip_info("OEBPS/cover.png", compression=ZIP_STORED), b"\x89PNG\r\nfixture"),
    ]
    for name, payload in (extra_members or {}).items():
        members.append((_zip_info(name, compression=ZIP_DEFLATED), payload))

    mimetype = (
        _zip_info(
            "mimetype",
            compression=mimetype_compression,
            extra=mimetype_extra,
        ),
        mimetype_payload,
    )
    ordered = (
        [mimetype, *members] if mimetype_first else [members[0], mimetype, *members[1:]]
    )

    output = BytesIO()
    with ZipFile(output, "w") as archive:
        for info, payload in ordered:
            archive.writestr(info, payload)
    return output.getvalue()


def replace_member(source: bytes, member_name: str, replacement: bytes) -> bytes:
    output = BytesIO()
    with ZipFile(BytesIO(source), "r") as before, ZipFile(output, "w") as after:
        after.comment = before.comment
        for info in before.infolist():
            payload = replacement if info.filename == member_name else before.read(info)
            after.writestr(info, payload)
    return output.getvalue()


def read_member(source: bytes, member_name: str) -> bytes:
    with ZipFile(BytesIO(source), "r") as archive:
        return archive.read(member_name)
