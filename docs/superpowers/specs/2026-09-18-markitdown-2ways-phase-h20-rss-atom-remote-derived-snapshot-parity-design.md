# Phase H20 — RSS/Atom local-vs-remote authority and remote-derived parity

## Goal

H20 extends v0.9 to RSS/Atom while explicitly preserving the distinction between native
local XML authority and remote-derived feed semantics.

The same feed bytes may participate in two different contracts:

- **local/native XML mode**: the caller uses the existing H4 `read_xml_ir()`; lexical XML
  ownership, native locators and bounded native XML mutation remain authoritative;
- **remote-derived feed mode**: the caller uses the new
  `read_rss_atom_snapshot_ir()` with an HTTP/HTTPS `StreamInfo.url`; the visible
  Markdown is derived from an already-materialized remote snapshot and has no remote
  writeback authority.

H20 never silently converts a local XML document into a derived remote document merely
because `RssConverter` can read it.

Base authority:

```text
main@a8e65158c7d56974a1a28a9894236f93cbb3a19b
tree 7b5c58d5f8c9a8250fa75f4bec607b811b7527d8
```

One-way RSS converter baseline:

```text
packages/markitdown/src/markitdown/converters/_rss_converter.py
blob 6b7b1201062208f7e24695b388bc4c3baabbb229
```

## Public API

H20 adds:

```python
read_rss_atom_snapshot_ir(
    source_stream,
    *,
    stream_info,
    limits=None,
)
```

The API is intentionally remote-only. Missing `stream_info.url` is rejected.

## Authority split

### Local/native XML

H20 does not modify H4.

A local RSS/Atom XML source remains eligible for:

- `SourceDescriptor(format="xml")`;
- native XML locators;
- lexical-source-span ownership;
- `replace_xml_text` and `replace_xml_attribute` where H4 already proves writability;
- source-preserving XML patching.

H20 must add regression tests showing these capabilities remain intact on the same RSS
fixture used by remote-derived tests.

### Remote-derived RSS/Atom

The remote reader requires:

- materialized snapshot bytes supplied by caller;
- `stream_info.url` using HTTP or HTTPS;
- non-empty host;
- no URL credentials;
- successful ownership by the existing `RssConverter.accepts()`;
- successful one-way conversion from the private snapshot bytes.

The URL is provenance only and is never fetched.

## In scope

H20 adds:

1. remote RSS/Atom snapshot parity;
2. exact public one-way Markdown/title parity;
3. source URI/SHA-256/size evidence;
4. converter/blob identity;
5. derived Markdown SHA-256/UTF-8 size evidence;
6. one deterministic remote-derived canvas/root node;
7. explicit `DERIVED` `replace_text` capability with
   `remote.source.not_native_writable`;
8. no native locator in remote mode;
9. no writer or remote writeback API;
10. local-vs-remote authority regression using identical RSS bytes;
11. URL/resource/network-firewall hardening;
12. public import and one-way invariance tests;
13. exact 9/9 final-head court and guarded merge.

## Out of scope

H20 does not:

- fetch feed URLs;
- follow redirects;
- poll feeds;
- send conditional HTTP requests;
- model ETag/Last-Modified freshness;
- write back to RSS/Atom origins;
- mutate remote feed entries;
- replace H4 XML routing;
- make local XML derived-only;
- add YouTube or Azure source adapters;
- modify `RssConverter`;
- modify one-way registry ordering;
- modify the `DocumentIR` schema.

## Resource limits

H20 reuses `RemoteDerivedLimits` exactly:

- bounded source capture;
- bounded Markdown UTF-8 result;
- positive non-bool integer validation;
- no unrestricted `.read()`.

## One-way semantic authority

The remote reader must match:

```python
MarkItDown().convert_stream(
    BytesIO(snapshot),
    stream_info=stream_info,
).markdown
```

for the same materialized snapshot and stream information.

Production may invoke `RssConverter` directly on a private `BytesIO` and apply the
same one-way Markdown normalization used by H18/H19.

`RssConverter.accepts()` remains final feed-ownership authority. H20 must not claim that
arbitrary XML is a feed merely because a remote URL is present.

## Evidence model

H20 reuses:

```text
twoways.remote_snapshot.v1
```

with at minimum:

```json
{
  "kind": "rss-atom",
  "uri": "https://example.com/feed.xml",
  "source_sha256": "...",
  "source_size_bytes": 1234,
  "converter": "RssConverter",
  "converter_blob_sha": "6b7b1201062208f7e24695b388bc4c3baabbb229",
  "markdown_sha256": "...",
  "markdown_utf8_size_bytes": 456,
  "network_performed_by_twoways": false
}
```

The evidence is descriptive provenance, not mutation authority.

## IR mapping

Remote mode creates:

- `SourceDescriptor(format="remote-rss-atom-snapshot", ...)`;
- one `Canvas(kind="remote-derived")`;
- one root text node with semantic role `derived_document`;
- no native locator;
- one provenance record using `extraction_method="RssConverter"`;
- one info diagnostic `remote.source.not_native_writable`.

The deterministic identity seed includes:

```text
remote-rss-atom-snapshot
+ URI
+ source SHA-256
+ Markdown SHA-256
+ RssConverter
```

## Capability contract

Remote mode uses the existing remote-derived decision exactly:

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

Local H4 capabilities remain unchanged.

## Security boundaries

Remote H20 reader may not import/call network/process clients.

Reject:

- missing URL;
- file/data/ftp schemes;
- malformed or empty host;
- credential-bearing URL;
- converter ownership failure;
- source/Markdown budget violation.

Unlike Wikipedia/Bing, H20 does not restrict hostnames. RSS/Atom feeds may live on any
HTTP(S) host; feed ownership comes from `RssConverter.accepts()`.

## Required tests

### Remote parity

- checked-in `test_rss.xml` materialized snapshot;
- HTTP(S) URL + RSS MIME information;
- public one-way title/Markdown parity;
- exact source/result digests;
- deterministic canonical serialization;
- derived capability and no native locator.

### Authority split

Using the exact same fixture bytes:

- `read_xml_ir(...)` yields `format="xml"`, native locators and at least one writable
  lexical XML text/attribute owner;
- `read_rss_atom_snapshot_ir(..., url=http[s]://...)` yields
  `format="remote-rss-atom-snapshot"`, one derived root and no native locator;
- H20 does not modify H4 XML implementation.

### Hardening

- URL validation;
- ownership rejection on non-feed XML;
- exact/over source budget;
- exact/over Markdown budget;
- bounded-read probe;
- network/process import firewall;
- invalid shared limits remain rejected by existing H18 tests.

### Public/one-way

- public export from remote/readers/top-level twoways;
- no feed writer/writeback export;
- direct `RssConverter` + public `MarkItDown.convert_stream` regression;
- converter blob remains exact.

## Approved implementation surface

```text
TWOWAYS.md
docs/superpowers/specs/2026-09-18-markitdown-2ways-phase-h20-rss-atom-remote-derived-snapshot-parity-design.md
docs/superpowers/plans/2026-09-18-markitdown-2ways-phase-h20-rss-atom-remote-derived-snapshot-parity-implementation.md
packages/markitdown/src/markitdown/twoways/readers/remote.py
packages/markitdown/src/markitdown/twoways/readers/__init__.py
packages/markitdown/src/markitdown/twoways/__init__.py
packages/markitdown/tests/twoways/test_remote_rss_atom_reader.py
packages/markitdown/tests/twoways/test_remote_rss_atom_hardening.py
packages/markitdown/tests/twoways/test_remote_rss_atom_public_imports.py
packages/markitdown/tests/twoways/test_remote_rss_atom_oneway_regression.py
```

H4 XML production files must not change.

## Completion gate

H20 completes only when:

1. local H4 XML authority remains green on RSS fixture;
2. remote RSS/Atom is derived-only;
3. `RssConverter` blob remains
   `6b7b1201062208f7e24695b388bc4c3baabbb229`;
4. no network/writeback path exists;
5. exact one-way parity passes;
6. hardening/public/serialization tests pass;
7. scope stays inside approved files;
8. pre-commit + package/OCR Python 3.10–3.13 = exact 9/9 GREEN;
9. synthetic merge tree equals frozen branch tree;
10. guarded merge uses exact expected head;
11. post-merge main parents/tree/blob are revalidated.

## Follow-on

H21 should address YouTube as a multi-input derived source because transcript service
content is not fully determined by the materialized HTML snapshot.
