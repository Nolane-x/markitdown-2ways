# Phase H20 — Remote RSS/Atom snapshot parity with local/native XML separation

## Goal

H20 adds deterministic read-only parity for already-materialized remote RSS/Atom
snapshots while preserving the existing H4 native XML authority for local XML/feed files.

Public API:

```python
read_remote_feed_snapshot_ir(source_stream, *, stream_info, limits=None)
```

Base:

```text
main@a8e65158c7d56974a1a28a9894236f93cbb3a19b
tree 7b5c58d5f8c9a8250fa75f4bec607b811b7527d8
```

One-way baseline:

```text
packages/markitdown/src/markitdown/converters/_rss_converter.py
blob 6b7b1201062208f7e24695b388bc4c3baabbb229
```

H20 must leave that converter unchanged.

## Central authority rule

H20 requires two independent authorities:

1. **remote origin:** `StreamInfo.url` is a valid HTTP/HTTPS URL with non-empty host
   and no user-info credentials;
2. **feed semantics:** the existing `RssConverter` accepts and successfully converts
   the supplied materialized snapshot under the supplied `StreamInfo`.

Neither authority alone is sufficient.

A local `.xml`, `.rss`, or `.atom` file without URL is rejected by H20 even if it
contains a valid feed. Such bytes remain eligible for H4 XML native semantics. H20 never
auto-routes local input and never downgrades H4 native ownership to derived ownership.

## In scope

- materialized RSS and Atom snapshots;
- explicit HTTP/HTTPS source URL;
- reuse of `RemoteDerivedLimits`;
- bounded snapshot capture;
- lazy `RssConverter` use on private `BytesIO`;
- exact public `MarkItDown.convert_stream` Markdown/title parity;
- source URI/SHA-256/size evidence;
- derived Markdown SHA-256/UTF-8-size evidence;
- one deterministic `Canvas(kind="remote-derived")`;
- one deterministic root text node with semantic role `derived_document`;
- `CapabilityState.DERIVED` for `replace_text`;
- reason `remote.source.not_native_writable`;
- no native locator;
- no writer;
- deterministic canonical serialization;
- explicit local/native-vs-remote/derived authority tests;
- network/process firewall;
- one-way RSS converter invariance.

## Out of scope

H20 does not fetch URLs, follow redirects, poll feeds, use ETag/Last-Modified, resolve
DNS, open sockets, authenticate, call browser/subprocess/network libraries, mutate remote
feeds, create/update/delete entries, edit embedded item HTML, alter H4 XML, expose a
generic public remote-adapter factory, add a writer, change converter registry order, or
bump the IR schema.

## Input contract

`read_remote_feed_snapshot_ir` accepts a binary source stream plus keyword-only
`stream_info` and optional `RemoteDerivedLimits`.

### URL

`stream_info.url` is mandatory and must:

- be a non-empty string after trim;
- parse via `urlsplit`;
- use exactly `http` or `https`;
- have non-empty hostname;
- contain no username/password.

Any valid host is allowed because feeds may be hosted on arbitrary domains. The URL is
provenance only and is never dereferenced.

### Feed ownership

After bounded capture:

```python
converter = RssConverter()
if not converter.accepts(BytesIO(snapshot), stream_info):
    reject
result = converter.convert(BytesIO(snapshot), stream_info)
```

Conversion/parser failure rejects the input and no IR is created. H20 does not broaden
one-way feed acceptance.

## Local/native XML separation

For the same RSS bytes:

- `read_xml_ir(BytesIO(source), ...)` retains H4 XML native locators and lexical
  mutation authority where H4 permits it;
- H20 without URL rejects;
- H20 with valid remote URL creates a derived root with no native locator.

Filename/extension/MIME alone never grants H20 remote authority.

## Limits

Reuse H18/H19 `RemoteDerivedLimits` unchanged:

- `max_source_bytes = 32 MiB`;
- `max_markdown_utf8_bytes = 16 MiB`.

Exact source/Markdown boundary succeeds; one byte beyond source or one byte below needed
Markdown budget fails closed.

## One-way parity

For identical snapshot + `StreamInfo`, root text equals exactly:

```python
MarkItDown().convert_stream(BytesIO(snapshot), stream_info=stream_info).markdown
```

Production may call `RssConverter` directly and use the existing remote Markdown
normalization helper. Tests use the public path as oracle. Both RSS and Atom are covered.

## Evidence model

Document custom metadata key remains:

```text
twoways.remote_snapshot.v1
```

Required H20 values:

```json
{
  "kind": "feed",
  "uri": "https://example.com/feed.xml",
  "source_sha256": "...",
  "source_size_bytes": 123,
  "converter": "RssConverter",
  "converter_blob_sha": "6b7b1201062208f7e24695b388bc4c3baabbb229",
  "markdown_sha256": "...",
  "markdown_utf8_size_bytes": 456,
  "network_performed_by_twoways": false
}
```

Optional deterministic hints: filename, MIME, charset.

`SourceDescriptor.format = "remote-feed-snapshot"`.

## IR mapping

One document, one remote-derived canvas and one root text node:

- `kind="text"`;
- `semantic_role="derived_document"`;
- `TextPayload(text=<one-way markdown>)`;
- no native locator;
- title from one-way result.

Provenance:

```python
Provenance(
    source_format="remote-feed-snapshot",
    extraction_method="RssConverter",
    metadata={
        "uri": uri,
        "source_sha256": source_sha,
        "markdown_sha256": markdown_sha,
        "remote_writeback": False,
    },
)
```

## Capability

Exactly:

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

Unknown operations remain read-only. No writer is registered.

## Diagnostic

One deterministic info diagnostic with code
`remote.source.not_native_writable`, describing derived remote feed content and absence
of H20 remote writeback authority.

## Deterministic identity

Seed includes:

```text
remote-feed-snapshot
+ exact source URI
+ source SHA-256
+ Markdown SHA-256
+ RssConverter
```

No time/randomness/response headers.

## Security

No H20 path imports/calls `requests`, `httpx`, `urllib.request`, `socket`,
`subprocess` or browser automation.

Feed parsing remains delegated to the existing hardened `RssConverter`; H20 does not add
a permissive XML parser. URLs in feed content are rendered as text/Markdown only and are
never opened.

## Invariance

H20 must not change:

- `_rss_converter.py` (blob must remain
  `6b7b1201062208f7e24695b388bc4c3baabbb229`);
- H4 XML reader/writer;
- network layer;
- writer registry;
- core IR/schema.

H4 XML files must be absent from PR diff.

## Required tests

Reader/parity:
- checked-in RSS fixture + HTTPS origin;
- synthetic Atom + HTTPS origin;
- exact public Markdown/title parity;
- source/result digests;
- deterministic canonical serialization;
- derived capability/no locator.

Authority:
- same RSS bytes via H4 XML are native;
- H20 without URL rejects;
- filename/MIME alone insufficient;
- H20 with URL is derived;
- file/data/ftp/credentials/malformed-host reject;
- arbitrary HTTP/HTTPS host may accept a valid feed;
- generic non-feed XML rejects;
- malformed feed rejects;
- precise feed MIME/extension with invalid bytes still fails conversion.

Budgets/firewall:
- exact and over/under boundaries;
- bounded-read probe;
- forbidden import/source inspection.

Public:
- export from remote/readers/top-level;
- no feed writer symbol.

Regression:
- direct/public RSS semantics unchanged;
- direct/public Atom semantics unchanged;
- H18/H19 tests remain green;
- H4 XML tests remain green.

## Expected production delta

Only:

```text
packages/markitdown/src/markitdown/twoways/readers/remote.py
packages/markitdown/src/markitdown/twoways/readers/__init__.py
packages/markitdown/src/markitdown/twoways/__init__.py
```

plus H20 tests/docs/spec/plan.

## Completion gate

H20 is complete only when:

- design contract satisfied;
- RSS converter blob unchanged;
- H4 XML files absent from diff;
- no network/process I/O;
- no writer;
- RSS + Atom exact public parity;
- local/native-vs-remote/derived separation proven;
- adversarial and serialization tests green;
- scope audit clean;
- pre-commit + package/OCR Python 3.10-3.13 = exact 9/9 GREEN;
- final head/tree frozen;
- synthetic merge parents = current main + exact H20 head;
- synthetic merge tree = final H20 tree;
- guarded merge uses exact expected head;
- post-merge main parents/tree/converter blob verified.

## Follow-on

H21: YouTube multi-input provenance.
H22: Azure Document Intelligence.
H23: Azure Content Understanding.
