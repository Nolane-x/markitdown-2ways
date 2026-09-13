from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from zipfile import BadZipFile, ZIP_STORED, ZipFile, is_zipfile


ZipProbe = Callable[[bytes, str], bool]
ZipRead = Callable[..., object]
ZipPatch = Callable[..., object]

_EPUB_MIMETYPE = b"application/epub+zip"


@dataclass(frozen=True)
class ZipMemberAdapter:
    key: str
    extensions: frozenset[str]
    probe: ZipProbe
    read: ZipRead | None
    patch: ZipPatch | None
    strong_package: bool = False

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("ZIP member adapter key must be non-empty")
        object.__setattr__(
            self,
            "extensions",
            frozenset(extension.lower() for extension in self.extensions),
        )


def _member_names(payload: bytes) -> set[str] | None:
    try:
        with ZipFile(BytesIO(payload), "r") as archive:
            return {info.filename for info in archive.infolist()}
    except (BadZipFile, ValueError):
        return None


def _probe_epub(payload: bytes, filename: str) -> bool:
    del filename
    if not is_zipfile(BytesIO(payload)):
        return False
    try:
        with ZipFile(BytesIO(payload), "r") as archive:
            infos = archive.infolist()
            if not infos:
                return False
            first = infos[0]
            if first.filename != "mimetype":
                return False
            if first.compress_type != ZIP_STORED or first.extra:
                return False
            if first.file_size != len(_EPUB_MIMETYPE):
                return False
            if first.flag_bits & 0x1:
                return False
            if "META-INF/container.xml" not in {info.filename for info in infos}:
                return False
            return archive.read(first) == _EPUB_MIMETYPE
    except (BadZipFile, RuntimeError, ValueError):
        return False


def _probe_ooxml(payload: bytes, marker: str) -> bool:
    names = _member_names(payload)
    if names is None:
        return False
    return {
        "[Content_Types].xml",
        "_rels/.rels",
        marker,
    }.issubset(names)


def _probe_docx(payload: bytes, filename: str) -> bool:
    del filename
    return _probe_ooxml(payload, "word/document.xml")


def _probe_pptx(payload: bytes, filename: str) -> bool:
    del filename
    return _probe_ooxml(payload, "ppt/presentation.xml")


def _probe_xlsx(payload: bytes, filename: str) -> bool:
    del filename
    return _probe_ooxml(payload, "xl/workbook.xml")


def _probe_zip(payload: bytes, filename: str) -> bool:
    del filename
    return is_zipfile(BytesIO(payload))


def default_zip_member_adapters() -> tuple[ZipMemberAdapter, ...]:
    return (
        ZipMemberAdapter(
            key="epub",
            extensions=frozenset({".epub"}),
            probe=_probe_epub,
            read=None,
            patch=None,
            strong_package=True,
        ),
        ZipMemberAdapter(
            key="docx",
            extensions=frozenset({".docx"}),
            probe=_probe_docx,
            read=None,
            patch=None,
            strong_package=True,
        ),
        ZipMemberAdapter(
            key="pptx",
            extensions=frozenset({".pptx"}),
            probe=_probe_pptx,
            read=None,
            patch=None,
            strong_package=True,
        ),
        ZipMemberAdapter(
            key="xlsx",
            extensions=frozenset({".xlsx"}),
            probe=_probe_xlsx,
            read=None,
            patch=None,
            strong_package=True,
        ),
        ZipMemberAdapter(
            key="zip",
            extensions=frozenset({".zip"}),
            probe=_probe_zip,
            read=None,
            patch=None,
            strong_package=False,
        ),
    )
