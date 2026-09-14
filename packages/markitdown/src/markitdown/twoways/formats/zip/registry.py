from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
import json
from pathlib import PurePath
from zipfile import BadZipFile, ZIP_STORED, ZipFile, is_zipfile


ZipProbe = Callable[[bytes, str], bool]
ZipRead = Callable[..., object]
ZipPatch = Callable[..., object]

_EPUB_MIMETYPE = b"application/epub+zip"
_TEXT_EXTENSIONS = frozenset({".txt", ".text", ".md", ".markdown"})


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


def _suffix(filename: str) -> str:
    return PurePath(filename).suffix.lower()


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


def _probe_text(payload: bytes, filename: str) -> bool:
    if _suffix(filename) not in _TEXT_EXTENSIONS:
        return False
    from ..text import read_text_ir

    read_text_ir(BytesIO(payload), filename=filename)
    return True


def _probe_csv(payload: bytes, filename: str) -> bool:
    if _suffix(filename) != ".csv":
        return False
    from ..csv import read_csv_ir

    read_csv_ir(BytesIO(payload), filename=filename)
    return True


def _probe_json(payload: bytes, filename: str) -> bool:
    if _suffix(filename) != ".json":
        return False
    try:
        json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return True


def _probe_xml(payload: bytes, filename: str) -> bool:
    if _suffix(filename) != ".xml":
        return False
    from ..xml import read_xml_ir

    read_xml_ir(BytesIO(payload), filename=filename)
    return True


def _probe_html(payload: bytes, filename: str) -> bool:
    if _suffix(filename) not in {".html", ".htm"}:
        return False
    from ..html import read_html_ir

    read_html_ir(BytesIO(payload), filename=filename)
    return True


def _probe_ipynb(payload: bytes, filename: str) -> bool:
    if _suffix(filename) != ".ipynb":
        return False
    from ..ipynb import read_ipynb_ir

    read_ipynb_ir(BytesIO(payload), filename=filename)
    return True


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
            key="ipynb",
            extensions=frozenset({".ipynb"}),
            probe=_probe_ipynb,
            read=None,
            patch=None,
            strong_package=False,
        ),
        ZipMemberAdapter(
            key="csv",
            extensions=frozenset({".csv"}),
            probe=_probe_csv,
            read=None,
            patch=None,
            strong_package=False,
        ),
        ZipMemberAdapter(
            key="json",
            extensions=frozenset({".json"}),
            probe=_probe_json,
            read=None,
            patch=None,
            strong_package=False,
        ),
        ZipMemberAdapter(
            key="xml",
            extensions=frozenset({".xml"}),
            probe=_probe_xml,
            read=None,
            patch=None,
            strong_package=False,
        ),
        ZipMemberAdapter(
            key="html",
            extensions=frozenset({".html", ".htm"}),
            probe=_probe_html,
            read=None,
            patch=None,
            strong_package=False,
        ),
        ZipMemberAdapter(
            key="text",
            extensions=_TEXT_EXTENSIONS,
            probe=_probe_text,
            read=None,
            patch=None,
            strong_package=False,
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
