from __future__ import annotations

from collections.abc import Mapping, Sequence
from io import BytesIO
import stat
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def make_zip_entries(
    entries: Sequence[tuple[str, bytes]],
    *,
    compression: int = ZIP_DEFLATED,
    archive_comment: bytes = b"",
    per_member_compression: Mapping[str, int] | None = None,
    symlink_name: str | None = None,
) -> bytes:
    per_member_compression = per_member_compression or {}
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.comment = archive_comment
        for name, payload in entries:
            info = ZipInfo(name, date_time=(2026, 1, 2, 3, 4, 6))
            # ZipInfo normalizes backslashes to "/" on Windows. Restore the\n            # caller-supplied member spelling so unsafe-path fixtures exercise\n            # the same raw archive name on every platform.\n            info.filename = name\n            info.orig_filename = name\n            info.compress_type = per_member_compression.get(name, compression)
            info.create_system = 3
            if name == symlink_name:
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            elif name.endswith("/"):
                info.external_attr = (stat.S_IFDIR | 0o755) << 16
            else:
                info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, payload)
    return output.getvalue()


def make_zip(
    *,
    members: Mapping[str, bytes] | None = None,
    compression: int = ZIP_DEFLATED,
    archive_comment: bytes = b"",
    per_member_compression: Mapping[str, int] | None = None,
    symlink_name: str | None = None,
) -> bytes:
    members = members or {
        "docs/readme.txt": b"hello\n",
        "data/config.json": b'{"name":"Ada"}\n',
    }
    return make_zip_entries(
        tuple(members.items()),
        compression=compression,
        archive_comment=archive_comment,
        per_member_compression=per_member_compression,
        symlink_name=symlink_name,
    )


def mark_single_member_encrypted(source: bytes) -> bytes:
    """Set the ZIP general-purpose encryption bit in one-member test archives."""

    data = bytearray(source)
    local = data.find(b"PK\x03\x04")
    central = data.find(b"PK\x01\x02")
    if local < 0 or central < 0:
        raise ValueError("test archive is missing ZIP headers")

    for offset in (local + 6, central + 8):
        flags = int.from_bytes(data[offset : offset + 2], "little") | 0x1
        data[offset : offset + 2] = flags.to_bytes(2, "little")
    return bytes(data)
