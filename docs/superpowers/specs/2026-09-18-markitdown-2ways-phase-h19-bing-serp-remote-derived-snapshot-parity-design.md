# Phase H19 — Bing SERP remote-derived snapshot parity

## Goal

H19 extends the v0.9 Class-D remote/derived program from Wikipedia to already-materialized
Bing search-result HTML snapshots while preserving the H18 no-network/no-writeback
contract.

The public reader is:

```python
read_bing_serp_snapshot_ir(
    source_stream,
    *,
    stream_info,
    limits=None,
)
```

H19 does not fetch Bing, submit searches, follow result links, call an API, or expose
remote mutation. The caller supplies the exact HTML snapshot bytes plus `StreamInfo`.
The existing one-way `BingSerpConverter` remains the semantic extraction authority.

Base authority:

```text
main@6bdfa3cebe1060b5c5a8bced4206f20a8dab3a19
tree bfec722b853ebec3983326dab99086bca1b0feff
```

One-way converter baseline:

```text
packages/markitdown/src/markitdown/converters/_bing_serp_converter.py
blob fd00a70ab76ff01fcdc2e3bfb47aaf20708408c8
```

The H18 Wikipedia reader and its canonical serialization are compatibility authority and
must not drift as a side effect of the H19 private-kernel refactor.

## Why Bing is H19

Bing SERP is the closest follow-on to H18 because its one-way semantics are entirely
derived from two already-materialized inputs:

1. Bing HTML snapshot bytes;
2. the supplied Bing search URL.

Unlike YouTube, no transcript or second service is required. Unlike RSS/Atom, Bing does
not create ambiguity between a local native XML source and a remote-derived feed origin.
This makes H19 a safe place to prove private kernel reuse before H20 handles RSS/local
versus remote semantics.

## Authority model

H19 is Class-D derived parity:

- semantic text is `CapabilityState.DERIVED`;
- reason code is `remote.source.not_native_writable`;
- no native locator is emitted;
- no writer is registered;
- no remote writeback API exists;
- unknown operations remain read-only;
- URL provenance never grants mutation authority.

The URL is provenance and converter-ownership input, not a fetch instruction.

## In scope

H19 adds:

1. a Bing SERP snapshot reader;
2. private reusable remote-derived helpers shared with H18 where this can be done without
   changing H18 output;
3. exact one-way Markdown parity for the same snapshot and `StreamInfo`;
4. source URI/SHA-256/size evidence;
5. derived Markdown SHA-256/UTF-8 size evidence;
6. converter identity and converter blob evidence;
7. deterministic document/canvas/node identity;
8. one derived root text node;
9. deterministic no-writeback diagnostic;
10. public exports for the Bing reader only;
11. adversarial URL/budget/network-firewall tests;
12. H18 regression tests proving Wikipedia canonical output remains identical;
13. one-way Bing converter invariance and full exact final-head court.

## Explicitly out of scope

H19 does not:

- issue a Bing search;
- perform HTTP, DNS, socket, browser or subprocess I/O;
- use the Bing API;
- follow or resolve result URLs;
- rewrite redirect URLs outside the existing converter semantics;
- mutate a Bing result page or search index;
- expose search-query mutation as remote writeback;
- create a local editable HTML artifact;
- add RSS/Atom, YouTube or Azure adapters;
- modify the one-way Bing converter;
- modify the one-way converter registry;
- modify `MarkItDown.convert_uri()` or HTTP fetching behavior;
- add a writer;
- change the `DocumentIR` schema.

## Reuse of H18 kernel

`RemoteDerivedLimits`, bounded source capture, Markdown normalization, derived capability
construction and deterministic document construction are candidates for private reuse.

Any refactor must satisfy both conditions:

1. the public H18 API and canonical serialized H18 `DocumentIR` remain byte-for-byte
   identical for the frozen Wikipedia fixture/input used by H18 tests;
2. no public generic `read_remote_snapshot_ir` API is introduced.

The production module remains:

```text
packages/markitdown/src/markitdown/twoways/readers/remote.py
```

Source-specific public functions are preferred over caller-supplied converter labels.

## Input contract

`read_bing_serp_snapshot_ir()` accepts:

- `source_stream: BinaryIO`;
- keyword-only `stream_info: StreamInfo`;
- optional `limits: RemoteDerivedLimits`.

### URL authority

`stream_info.url` is mandatory and must be accepted by the existing
`BingSerpConverter.accepts()`.

Structural preflight also requires:

- scheme `https`;
- non-empty host;
- no username/password;
- no malformed URL.

The converter itself is final ownership authority. H19 must not broaden the current
accepted shape, which is currently rooted at:

```text
https://www.bing.com/search?q=
```

Examples that must fail closed include:

- `http://www.bing.com/search?q=x`;
- `https://bing.com/search?q=x`;
- `https://www.bing.com.example.com/search?q=x`;
- `https://user:secret@www.bing.com/search?q=x`;
- non-search Bing paths;
- missing `q=` ownership required by the converter;
- non-HTML stream information rejected by the converter.

H19 records the supplied accepted URL. It does not execute or canonicalize the search.

### Snapshot authority

The complete supplied snapshot is captured under
`RemoteDerivedLimits.max_source_bytes` using bounded reads only.

Evidence includes:

- source SHA-256;
- source byte length;
- source URI;
- filename/MIME/charset hints when supplied;
- converter identity;
- converter blob SHA;
- derived Markdown SHA-256 and UTF-8 byte length;
- `network_performed_by_twoways=False`.

Snapshot evidence proves analyzed bytes only. It does not prove current Bing freshness.

## One-way semantic parity

The H19 text payload must equal:

```python
MarkItDown().convert_stream(
    BytesIO(snapshot),
    stream_info=stream_info,
).markdown
```

for the same materialized bytes and accepted `StreamInfo`.

Production code may call `BingSerpConverter` directly on a private `BytesIO`, then
apply the same public one-way Markdown normalization already used by H18.

The reader rejects input if `BingSerpConverter.accepts()` is false instead of allowing
generic HTML fallback.

## Evidence model

H19 reuses the versioned metadata envelope:

```text
twoways.remote_snapshot.v1
```

The Bing record contains at minimum:

```json
{
  "kind": "bing-serp",
  "uri": "https://www.bing.com/search?q=example",
  "source_sha256": "...",
  "source_size_bytes": 1234,
  "converter": "BingSerpConverter",
  "converter_blob_sha": "fd00a70ab76ff01fcdc2e3bfb47aaf20708408c8",
  "markdown_sha256": "...",
  "markdown_utf8_size_bytes": 456,
  "network_performed_by_twoways": false
}
```

The record is provenance only and never grants mutation authority.

## IR mapping

H19 creates:

- `SourceDescriptor(format="remote-bing-serp-snapshot", ...)`;
- one `Canvas(kind="remote-derived")`;
- one root `Node(kind="text", semantic_role="derived_document")`;
- `TextPayload(text=<one-way normalized Markdown>)`;
- no canvas or node native locator.

Document title uses the one-way result title when present.

### Provenance

The root provenance uses:

- `source_format="remote-bing-serp-snapshot"`;
- `extraction_method="BingSerpConverter"`;
- metadata with URI, source digest, Markdown digest and
  `remote_writeback=False`.

## Capability contract

The root node carries the same stable remote-derived decision as H18:

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

No writer and no writable operation are introduced.

## Diagnostics

The document contains one info diagnostic:

```text
code: remote.source.not_native_writable
severity: info
```

The message describes H19's lack of Bing remote-write authority, not an assertion that
Bing itself is immutable.

## Deterministic identity

The identity seed includes exactly stable source-specific evidence:

```text
remote-bing-serp-snapshot
+ accepted source URI
+ source SHA-256
+ derived Markdown SHA-256
+ BingSerpConverter
```

No timestamps, randomness or response dates participate.

## Resource limits

H19 reuses `RemoteDerivedLimits` exactly. It does not add new fields.

- source exact-limit succeeds;
- source one byte above fails;
- Markdown exact-limit succeeds;
- Markdown one byte above fails;
- invalid zero/negative/bool limits remain rejected;
- capture never calls unrestricted `.read()`.

## Security boundaries

### Network firewall

The 2Ways remote reader must not import or call:

- `requests`;
- `httpx`;
- `urllib.request`;
- `socket`;
- browser automation;
- `subprocess`.

### Host confusion

Bing-like attacker domains must fail. Converter ownership remains authoritative after
structural URL preflight.

### Derived text is untrusted

Result Markdown is stored as text only. Links are not followed and HTML/Markdown is not
executed.

### No credential propagation

URLs with user-info credentials are rejected.

## One-way invariance

H19 must leave unchanged:

```text
packages/markitdown/src/markitdown/converters/_bing_serp_converter.py
blob fd00a70ab76ff01fcdc2e3bfb47aaf20708408c8
```

It also must not alter registry ordering or generic HTML converter behavior.

## Required tests

At minimum:

### Happy path / parity

- synthetic materialized Bing SERP HTML accepted;
- result text equals public `MarkItDown().convert_stream()` exactly;
- source URI/digest/size exact;
- result digest/UTF-8 size exact;
- title parity;
- deterministic repeated reads;
- canonical JSON round trip.

### H18 regression

- frozen Wikipedia H18 input produces identical canonical JSON before/after private
  kernel refactor;
- H18 capability/evidence fields remain unchanged;
- Wikipedia public imports remain lazy/stable.

### Capability / provenance

- root `replace_text` is `DERIVED`;
- exact reason code `remote.source.not_native_writable`;
- zero writable nodes;
- no native locators;
- deterministic diagnostic;
- no writer/public writeback symbol.

### URL hardening

Reject wrong scheme, wrong host, lookalike host, credentials, missing/invalid host,
non-search path, converter-rejected stream information and malformed query ownership.

### Resource hardening

- exact/over source limit;
- exact/over Markdown limit;
- bounded-read probe;
- invalid limits remain rejected.

### Network firewall

Production module contains no network/process import path and tests perform no live
network activity.

### One-way regression

- direct `BingSerpConverter` and public `MarkItDown.convert_stream` remain green;
- final converter blob is unchanged.

## Expected implementation surface

Approved scope:

```text
TWOWAYS.md
docs/superpowers/specs/2026-09-18-markitdown-2ways-phase-h19-bing-serp-remote-derived-snapshot-parity-design.md
docs/superpowers/plans/2026-09-18-markitdown-2ways-phase-h19-bing-serp-remote-derived-snapshot-parity-implementation.md
packages/markitdown/src/markitdown/twoways/readers/remote.py
packages/markitdown/src/markitdown/twoways/readers/__init__.py
packages/markitdown/src/markitdown/twoways/__init__.py
packages/markitdown/tests/twoways/test_remote_bing_serp_reader.py
packages/markitdown/tests/twoways/test_remote_bing_serp_hardening.py
packages/markitdown/tests/twoways/test_remote_bing_serp_oneway_regression.py
packages/markitdown/tests/twoways/test_remote_bing_serp_public_imports.py
```

No schema, writer, HTTP layer or one-way converter file should change.

## Completion gate

H19 is complete only when one frozen final head satisfies all of:

1. implementation matches this spec;
2. H18 Wikipedia canonical regression remains exact;
3. Bing one-way converter blob remains
   `fd00a70ab76ff01fcdc2e3bfb47aaf20708408c8`;
4. no network/process I/O path is introduced;
5. no H19 writer or remote writeback exists;
6. Bing one-way Markdown parity passes;
7. URL/budget/capability/provenance hardening passes;
8. public import and canonical serialization tests pass;
9. changed-file scope stays inside approved H19 surface;
10. pre-commit succeeds;
11. package tests succeed Python 3.10–3.13;
12. OCR tests succeed Python 3.10–3.13;
13. exact final-head court is 9/9 GREEN;
14. synthetic merge parents are current main + exact final H19 head;
15. synthetic merge tree equals final H19 branch tree;
16. guarded merge uses exact expected head;
17. post-merge main parents/tree and one-way converter blob are revalidated.

## Follow-on

H20 should handle RSS/Atom with an explicit distinction between local/native XML source
authority and remote-derived feed snapshots. H21 then handles YouTube multi-input
HTML/transcript provenance.
