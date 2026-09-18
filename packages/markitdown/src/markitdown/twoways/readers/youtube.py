from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
import re
from typing import BinaryIO
from urllib.parse import parse_qs, unquote, urlparse, urlsplit

import bs4

from ..._stream_info import StreamInfo
from ..capabilities import (
    CAPABILITY_METADATA_KEY,
    CapabilityDecision,
    CapabilityState,
    encode_capabilities,
)
from ..ir.document import (
    Canvas,
    Diagnostic,
    DocumentIdFactory,
    DocumentIR,
    DocumentMetadata,
    SourceDescriptor,
)
from ..ir.nodes import Node, TextPayload
from ..ir.provenance import Provenance
from ..ir.serialization import validate_document


_YOUTUBE_EVIDENCE_KEY = "twoways.youtube_snapshot.v1"
_YOUTUBE_CONVERTER_BLOB_SHA = "c3779743c6fe55c4716d8816b9a5a52b929c5e32"
_ACCEPTED_HOSTS = frozenset(
    {
        "youtu.be",
        "www.youtu.be",
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
    }
)
_ACCEPTED_MIME_TYPE_PREFIXES = ("text/html", "application/xhtml")
_ACCEPTED_FILE_EXTENSIONS = (".html", ".htm")


@dataclass(frozen=True)
class YouTubeTranscriptSnapshot:
    video_id: str
    language_code: str
    parts: tuple[str, ...]
    provider: str

    def __post_init__(self) -> None:
        for name in ("video_id", "language_code", "provider"):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise TypeError(f"{name} must be a string")
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if not isinstance(self.parts, tuple):
            raise TypeError("parts must be a tuple of strings")
        if not self.parts:
            raise ValueError("parts must be non-empty")
        for index, part in enumerate(self.parts):
            if not isinstance(part, str):
                raise TypeError(f"parts[{index}] must be a string")
            if not part.strip():
                raise ValueError(f"parts[{index}] must be non-empty")


@dataclass(frozen=True)
class YouTubeDerivedLimits:
    max_html_bytes: int = 32 * 1024 * 1024
    max_transcript_utf8_bytes: int = 16 * 1024 * 1024
    max_markdown_utf8_bytes: int = 16 * 1024 * 1024

    def __post_init__(self) -> None:
        for name in (
            "max_html_bytes",
            "max_transcript_utf8_bytes",
            "max_markdown_utf8_bytes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")


def _capture_html(source_stream: BinaryIO, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total <= max_bytes:
        remaining = max_bytes + 1 - total
        if remaining <= 0:
            break
        chunk = source_stream.read(min(64 * 1024, remaining))
        if isinstance(chunk, str):
            raise TypeError("YouTube snapshot source stream must return bytes")
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError("YouTube snapshot source stream returned a non-bytes value")
        data = bytes(chunk)
        if not data:
            break
        chunks.append(data)
        total += len(data)
        if total > max_bytes:
            raise ValueError("YouTube snapshot exceeds max_html_bytes")
    return b"".join(chunks)


def _normalized_converter_url(uri: str) -> str:
    return unquote(uri).replace(r"\?", "?").replace(r"\=", "=")


def _video_id_from_converter_url(uri: str) -> str | None:
    parsed_url = urlparse(_normalized_converter_url(uri))
    hostname = parsed_url.netloc.lower()
    path_parts = [part for part in parsed_url.path.split("/") if part]

    if hostname in {"youtu.be", "www.youtu.be"}:
        return path_parts[0] if path_parts else None

    if hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if path_parts[:1] == ["watch"]:
            params = parse_qs(parsed_url.query)
            return params.get("v", [None])[0]
        if path_parts[:1] in (["shorts"], ["embed"]):
            return path_parts[1] if len(path_parts) > 1 else None

    return None


def _validate_url_and_video_id(stream_info: StreamInfo) -> tuple[str, str]:
    uri = stream_info.url
    if not isinstance(uri, str) or not uri.strip():
        raise ValueError("YouTube snapshot requires stream_info.url")
    uri = uri.strip()
    normalized = _normalized_converter_url(uri)

    try:
        parsed = urlsplit(normalized)
        hostname = parsed.hostname
        username = parsed.username
        password = parsed.password
        port = parsed.port
    except ValueError as exc:
        raise ValueError("YouTube snapshot URL is malformed") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("YouTube snapshot URL must use http or https")
    if not hostname:
        raise ValueError("YouTube snapshot URL must contain a host")
    if username is not None or password is not None:
        raise ValueError("YouTube snapshot URL must not contain credentials")
    if hostname.lower() not in _ACCEPTED_HOSTS:
        raise ValueError("YouTube snapshot URL host is not owned by YouTubeConverter")
    if port is not None:
        raise ValueError("YouTube snapshot URL port is not owned by YouTubeConverter")

    video_id = _video_id_from_converter_url(normalized)
    if not isinstance(video_id, str) or not video_id:
        raise ValueError("YouTube snapshot URL does not contain a supported video ID")

    mimetype = (stream_info.mimetype or "").lower()
    extension = (stream_info.extension or "").lower()
    if extension not in _ACCEPTED_FILE_EXTENSIONS and not any(
        mimetype.startswith(prefix) for prefix in _ACCEPTED_MIME_TYPE_PREFIXES
    ):
        raise ValueError(
            "snapshot is not owned by the existing YouTubeConverter "
            "under the supplied StreamInfo"
        )

    return uri, video_id


def _find_key(value: object, key: str) -> object | None:
    if isinstance(value, list):
        for element in value:
            result = _find_key(element, key)
            if result is not None:
                return result
    elif isinstance(value, dict):
        for item_key, item_value in value.items():
            if item_key == key:
                return item_value
            if result := _find_key(item_value, key):
                return result
    return None


def _first(metadata: dict[str, str], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        if key in metadata:
            return metadata[key]
    return None


def _local_projection(
    source_bytes: bytes,
    *,
    stream_info: StreamInfo,
    transcript_text: str | None,
) -> tuple[str, str]:
    encoding = "utf-8" if stream_info.charset is None else stream_info.charset
    soup = bs4.BeautifulSoup(
        BytesIO(source_bytes),
        "html.parser",
        from_encoding=encoding,
    )

    metadata: dict[str, str] = {}
    if soup.title and soup.title.string:
        metadata["title"] = soup.title.string

    for meta in soup(["meta"]):
        if not isinstance(meta, bs4.Tag):
            continue
        for attribute in meta.attrs:
            if attribute in {"itemprop", "property", "name"}:
                key = str(meta.get(attribute, ""))
                content = str(meta.get("content", ""))
                if key and content:
                    metadata[key] = content
                break

    try:
        for script in soup(["script"]):
            if not isinstance(script, bs4.Tag) or not script.string:
                continue
            content = script.string
            if "ytInitialData" not in content:
                continue
            match = re.search(r"var ytInitialData = ({.*?});", content)
            if match:
                data = json.loads(match.group(1))
                description = _find_key(data, "attributedDescriptionBodyText")
                if description and isinstance(description, dict):
                    metadata["description"] = str(description.get("content", ""))
            break
    except Exception:
        pass

    webpage_text = "# YouTube\n"
    title = _first(metadata, ("title", "og:title", "name")) or ""
    if title:
        webpage_text += f"\n## {title}\n"

    stats = ""
    views = _first(metadata, ("interactionCount",))
    if views:
        stats += f"- **Views:** {views}\n"
    keywords = _first(metadata, ("keywords",))
    if keywords:
        stats += f"- **Keywords:** {keywords}\n"
    runtime = _first(metadata, ("duration",))
    if runtime:
        stats += f"- **Runtime:** {runtime}\n"
    if stats:
        webpage_text += f"\n### Video Metadata\n{stats}\n"

    description = _first(metadata, ("description", "og:description"))
    if description:
        webpage_text += f"\n### Description\n{description}\n"

    if transcript_text:
        webpage_text += f"\n### Transcript\n{transcript_text}\n"

    return title, webpage_text


def _derived_capability() -> tuple[dict[str, object], ...]:
    return encode_capabilities(
        (
            CapabilityDecision(
                operation="replace_text",
                state=CapabilityState.DERIVED,
                reason_code="remote.source.not_native_writable",
                constraints={
                    "identity_markdown": False,
                    "remote_writeback": False,
                    "native_owner": False,
                    "materialization": "explicit-local-only",
                },
            ),
        )
    )


def read_youtube_snapshot_ir(
    source_stream: BinaryIO,
    *,
    stream_info: StreamInfo,
    transcript: YouTubeTranscriptSnapshot | None = None,
    limits: YouTubeDerivedLimits | None = None,
) -> DocumentIR:
    active_limits = limits or YouTubeDerivedLimits()
    uri, video_id = _validate_url_and_video_id(stream_info)
    html_bytes = _capture_html(
        source_stream,
        max_bytes=active_limits.max_html_bytes,
    )

    transcript_text: str | None = None
    transcript_digest: str | None = None
    transcript_size = 0
    if transcript is not None:
        if not isinstance(transcript, YouTubeTranscriptSnapshot):
            raise TypeError("transcript must be a YouTubeTranscriptSnapshot")
        if transcript.video_id != video_id:
            raise ValueError("transcript video ID does not match YouTube page authority")
        transcript_text = " ".join(transcript.parts)
        transcript_bytes = transcript_text.encode("utf-8")
        transcript_size = len(transcript_bytes)
        if transcript_size > active_limits.max_transcript_utf8_bytes:
            raise ValueError("transcript exceeds max_transcript_utf8_bytes")
        transcript_digest = sha256(transcript_bytes).hexdigest()

    title, markdown = _local_projection(
        html_bytes,
        stream_info=stream_info,
        transcript_text=transcript_text,
    )
    markdown_bytes = markdown.encode("utf-8")
    if len(markdown_bytes) > active_limits.max_markdown_utf8_bytes:
        raise ValueError("derived Markdown exceeds max_markdown_utf8_bytes")

    html_digest = sha256(html_bytes).hexdigest()
    markdown_digest = sha256(markdown_bytes).hexdigest()
    identity_seed = "\0".join(
        (
            "remote-youtube-snapshot",
            uri,
            video_id,
            html_digest,
            transcript_digest or "no-transcript",
            markdown_digest,
            "YouTubeConverter",
        )
    )
    ids = DocumentIdFactory(seed=identity_seed)
    document_id = ids.new("document")
    canvas_id = ids.new("canvas")
    node_id = ids.new("root")

    evidence: dict[str, object] = {
        "kind": "youtube",
        "uri": uri,
        "html_sha256": html_digest,
        "html_size_bytes": len(html_bytes),
        "video_id": video_id,
        "converter": "YouTubeConverter",
        "converter_blob_sha": _YOUTUBE_CONVERTER_BLOB_SHA,
        "markdown_sha256": markdown_digest,
        "markdown_utf8_size_bytes": len(markdown_bytes),
        "transcript_provided": transcript is not None,
        "network_performed_by_twoways": False,
    }
    if transcript is not None and transcript_digest is not None:
        evidence["transcript_video_id"] = transcript.video_id
        evidence["transcript_language_code"] = transcript.language_code
        evidence["transcript_provider"] = transcript.provider
        evidence["transcript_part_count"] = len(transcript.parts)
        evidence["transcript_sha256"] = transcript_digest
        evidence["transcript_utf8_size_bytes"] = transcript_size
    if stream_info.filename is not None:
        evidence["filename"] = stream_info.filename
    if stream_info.mimetype is not None:
        evidence["mimetype"] = stream_info.mimetype
    if stream_info.charset is not None:
        evidence["charset"] = stream_info.charset

    node = Node(
        node_id=node_id,
        kind="text",
        semantic_role="derived_document",
        order=0,
        canvas_id=canvas_id,
        provenance=(
            Provenance(
                source_format="remote-youtube-snapshot",
                canvas_index=0,
                extraction_method="YouTubeConverter-local-projection",
                metadata={
                    "uri": uri,
                    "html_sha256": html_digest,
                    "video_id": video_id,
                    "markdown_sha256": markdown_digest,
                    "transcript_provided": transcript is not None,
                    "transcript_sha256": transcript_digest,
                    "remote_writeback": False,
                },
            ),
        ),
        native_locator=None,
        payload=TextPayload(text=markdown),
        metadata={
            CAPABILITY_METADATA_KEY: _derived_capability(),
            "twoways.youtube_snapshot.video_id": video_id,
            "twoways.youtube_snapshot.markdown_sha256": markdown_digest,
        },
    )

    document = DocumentIR(
        document_id=document_id,
        source=SourceDescriptor(
            format="remote-youtube-snapshot",
            filename=stream_info.filename,
            mimetype=stream_info.mimetype,
            uri=uri,
            sha256=html_digest,
            size_bytes=len(html_bytes),
        ),
        metadata=DocumentMetadata(
            title=title,
            custom={_YOUTUBE_EVIDENCE_KEY: evidence},
        ),
        canvases=(
            Canvas(
                canvas_id=canvas_id,
                index=0,
                kind="remote-derived",
                name=title or stream_info.filename,
                root_node_ids=(node_id,),
                native_locator=None,
            ),
        ),
        nodes={node_id: node},
        root_node_ids=(node_id,),
        diagnostics=(
            Diagnostic(
                code="remote.source.not_native_writable",
                severity="info",
                message=(
                    "Visible Markdown is derived from explicit local YouTube "
                    "materializations and has no H21 remote writeback authority."
                ),
                node_id=node_id,
                canvas_id=canvas_id,
                details={
                    "uri": uri,
                    "video_id": video_id,
                    "transcript_provided": transcript is not None,
                    "remote_writeback": False,
                },
            ),
        ),
    )
    validate_document(document)
    return document
