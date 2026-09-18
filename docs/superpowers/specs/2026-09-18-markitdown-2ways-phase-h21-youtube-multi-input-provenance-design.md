# Phase H21 — YouTube multi-input remote-derived provenance

## Goal

H21 extends v0.9 with deterministic, read-only `DocumentIR` parity for already-
materialized YouTube page snapshots plus an optional already-materialized transcript
snapshot.

The central rule is that page HTML and transcript are **different authorities**. A
YouTube transcript is not assumed to be present in, derivable from, or fresh relative
to the HTML bytes.

Base:

```text
main@667bb3edd6bc90fa4bd99d1d0e957c0f45671f83
tree a3c43e8d52385a3a5b9a76d5ca0f9105baf82e42
```

One-way baseline:

```text
packages/markitdown/src/markitdown/converters/_youtube_converter.py
```

The exact baseline blob is captured by tests before implementation and must remain
unchanged throughout H21.

## Public API

```python
YouTubeTranscriptSnapshot(
    video_id=...,
    language_code=...,
    parts=(...),
    provider=...,
)

read_youtube_snapshot_ir(
    html_stream,
    *,
    stream_info,
    transcript=None,
    limits=None,
)
```

## Authority model

H21 requires page authority from all of:

1. explicit HTTP/HTTPS YouTube URL;
2. exact already-materialized HTML bytes;
3. current `YouTubeConverter.accepts` ownership.

H21 never fetches the page.

Transcript authority is optional and independent. When supplied it consists only of
caller-materialized values:

- `video_id`;
- `language_code`;
- ordered text `parts`;
- non-empty descriptive `provider`.

The transcript video ID must equal the video ID derived from the accepted page URL.
H21 never calls `YouTubeTranscriptApi`.

## Multi-input provenance

HTML evidence records:

- source URI;
- source SHA-256;
- source byte size;
- YouTube video ID;
- converter identity/blob;
- network performed by 2Ways = false.

Optional transcript evidence records:

- video ID;
- language code;
- provider;
- ordered part count;
- transcript UTF-8 SHA-256;
- transcript UTF-8 size;
- network performed by 2Ways = false.

Absence of transcript is represented explicitly as `transcript_provided=false`.
It must not be interpreted as “YouTube has no transcript”.

## Markdown semantics

H21 reconstructs the pure local portion of the existing `YouTubeConverter` semantics
from the materialized HTML snapshot:

- `# YouTube`;
- title;
- views/keywords/runtime metadata;
- description.

If an explicit transcript snapshot is supplied, H21 joins the ordered transcript parts
with one ASCII space, exactly matching the current one-way transcript rendering rule,
then appends:

```text
### Transcript
<joined transcript>
```

Production H21 performs no service lookup.

Tests prove exact parity in two deterministic offline courts:

1. transcript-disabled one-way converter vs H21 HTML-only projection;
2. one-way converter using a fake in-memory `YouTubeTranscriptApi` vs H21 with the
   equivalent explicit transcript snapshot.

## URL/video identity

Accepted schemes: `http`, `https`.

Accepted current YouTube host forms follow the existing converter:

- `youtube.com`;
- `www.youtube.com`;
- `m.youtube.com`;
- `youtu.be`;
- `www.youtu.be`.

Credentials and malformed ports reject. The accepted URL must yield a non-empty video ID
using the existing converter's URL semantics.

## Limits

`YouTubeDerivedLimits`:

- `max_html_bytes = 32 MiB`;
- `max_transcript_utf8_bytes = 16 MiB`;
- `max_markdown_utf8_bytes = 16 MiB`.

All values are positive integers, not bool.

HTML capture must use bounded reads. Transcript and final Markdown enforce exact
UTF-8-size boundaries.

## IR mapping

One document, one `Canvas(kind="remote-derived")`, one root text node:

- `kind="text"`;
- `semantic_role="derived_document"`;
- no native locator;
- `TextPayload` containing deterministic Markdown.

`SourceDescriptor.format = "remote-youtube-snapshot"`.

The source SHA/size bind only the HTML materialization. Transcript evidence lives in the
versioned custom evidence envelope and must never be conflated with source bytes.

## Capability

Root `replace_text`:

```python
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
)
```

No writer, transcript edit operation, remote mutation or identity-Markdown writeback.

## Security

Production H21 must not import/call:

- `youtube_transcript_api`;
- `requests`;
- `httpx`;
- `urllib.request`;
- `socket`;
- `subprocess`;
- browser automation;
- `time.sleep`.

The existing one-way converter remains unchanged, including its current optional network
behavior when callers use that API directly. H21 simply does not invoke that path.

## Invariance

H21 must not change:

- `_youtube_converter.py`;
- H18-H20 remote readers' observable canonical behavior;
- converter registry;
- writer registry;
- HTTP layer;
- IR schema.

## Required tests

Reader:
- supported watch/youtu.be/shorts/embed URLs;
- HTML-only deterministic mapping;
- exact source/evidence digests;
- derived capability/no locator;
- canonical serialization.

Transcript:
- explicit transcript exact rendering;
- independent transcript digest/size;
- missing transcript represented distinctly;
- video-ID mismatch rejects;
- malformed language/provider/parts reject;
- transcript exact/over budget.

Offline one-way differential:
- converter with transcript capability forced off equals H21 HTML-only Markdown/title;
- converter with fake transcript API equals H21 explicit transcript Markdown/title;
- no real network/sleep.

Security/hardening:
- malformed/non-HTTP/credential/lookalike URLs reject;
- HTML source exact/over budget;
- final Markdown exact/over budget;
- bounded source reads;
- forbidden production imports;
- no writer/public mutation symbols.

Regression:
- H18/H19/H20 remain green;
- one-way YouTube converter blob unchanged.

## Completion gate

H21 completes only after:

- spec/plan satisfied;
- strict RED -> GREEN evidence;
- one-way converter blob unchanged;
- no network/process service call in H21;
- no writer;
- exact final pre-commit + package/OCR Python 3.10-3.13 = 9/9 GREEN;
- final head/tree frozen;
- synthetic parents = current main + exact H21 head;
- synthetic tree = final H21 tree;
- guarded merge with exact expected head;
- post-merge main parents/tree/converter blob verified.

## Follow-on

H22: Azure Document Intelligence derived-analysis provenance.
H23: Azure Content Understanding multimodal derived-analysis provenance.
