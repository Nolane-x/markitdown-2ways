# Phase H18 — Wikipedia remote-derived snapshot parity

## Goal

H18 opens the v0.9 one-way-input-parity program with the smallest remote-source tranche
that can be proven end to end without introducing network I/O into the 2Ways layer.

The tranche adds a deterministic reader for an already-materialized Wikipedia HTML
snapshot:

- the caller supplies snapshot bytes through a binary stream;
- `StreamInfo.url` identifies the Wikipedia HTTP/HTTPS origin;
- the existing one-way `WikipediaConverter` remains the semantic extraction reference;
- H18 projects the one-way Markdown result into `DocumentIR`;
- every semantic node is explicitly `derived`;
- H18 never claims or exposes native writeback to Wikipedia;
- H18 performs no HTTP request, API call, subprocess invocation or browser action;
- there is no H18 writer.

The public reader is:

```python
read_wikipedia_snapshot_ir(
    source_stream,
    *,
    stream_info,
    limits=None,
)
```

H18 is not a general web editor. It is a provenance/capability firewall between
one-way remote extraction and the 2Ways mutation model.

The branch starts from merged H17:

```text
main@98d22412fdf99b87eaea33aa6413a5f0e408d4f8
tree 187e72197f072b49752d380d415a3353e00c5215
```

The existing one-way Wikipedia converter baseline is:

```text
packages/markitdown/src/markitdown/converters/_wikipedia_converter.py
blob ba0c751092fa9e37fcf982f1fae9c4dcd774e049
```

H18 must leave that one-way converter unchanged.

## Why Wikipedia is first

The broader v0.9 program includes RSS URLs, Wikipedia, YouTube, Bing SERP, Azure
Document Intelligence and Azure Content Understanding. These sources do not share the
same derivation topology.

Wikipedia is selected first because its current converter derives Markdown from exactly
two authoritative inputs already available to H18:

1. the materialized HTML response bytes; and
2. the associated Wikipedia URL carried in `StreamInfo`.

The converter does not need a second remote service to obtain its semantic result.

This differs from later sources:

- YouTube may issue transcript API calls in addition to reading the materialized HTML;
- Azure Document Intelligence derives content through a configured cloud analyzer;
- Azure Content Understanding adds service/analyzer/model provenance and modality
  routing;
- Bing SERP and RSS can reuse the H18 remote-derived kernel after the first contract is
  proven, but are not included in H18.

H18 therefore establishes the shared remote-derived semantics without pretending that
all future adapters have identical provenance.

## Normative 2Ways authority

H18 follows the already-approved parity-program rules:

- remote extraction results are `derived`;
- derived semantic text never implicitly edits the remote page;
- unknown or absent native mutation authority defaults to read-only;
- the machine-readable reason code for this tranche is
  `remote.source.not_native_writable`;
- Class-D source adapters may expose readable IR without exposing a native writer;
- network I/O remains outside the 2Ways core.

The existing capability kernel already provides `CapabilityState.DERIVED`; H18 uses
that state rather than inventing a new capability category or bumping the
`DocumentIR` schema.

## Definitions

### Remote origin

The HTTP/HTTPS Wikipedia URL that names the remote page.

H18 preserves the supplied URL as provenance. It does not canonicalize, rewrite or
resolve it through network access.

### Materialized snapshot

The exact bytes already obtained by the caller or the one-way MarkItDown HTTP layer.
H18 computes and records their SHA-256 digest and byte length.

The snapshot is evidence about what was analyzed; it is not evidence that the current
remote page is still identical.

### Derived projection

The Markdown semantic result produced from the materialized snapshot.

The projection is not a native Wikipedia representation and receives no native locator.

### Native writeback

Any operation that would claim to modify the Wikipedia page, its HTML origin, its
server-side revision or any other remote state.

H18 exposes no such operation.

## In scope

H18 adds:

1. a bounded remote-derived snapshot evidence model reusable by later v0.9 readers;
2. strict validation for HTTP/HTTPS Wikipedia snapshot inputs;
3. bounded capture of the supplied materialized source bytes;
4. one-way Wikipedia semantic extraction from those bytes without network access;
5. exact one-way-output parity tests against the public MarkItDown stream path;
6. deterministic `DocumentIR` construction from the derived Markdown result;
7. source SHA-256/size/URI provenance;
8. result Markdown SHA-256/UTF-8 byte-size evidence;
9. a single root text node carrying the derived Markdown;
10. explicit `DERIVED` capability state for `replace_text`;
11. reason code `remote.source.not_native_writable`;
12. deterministic diagnostics explaining why remote/native writeback is unavailable;
13. serialization/public-import tests;
14. adversarial tests for malformed URLs, wrong-origin URLs, oversized snapshots,
    oversized derived output and forged/ambiguous provenance inputs;
15. one-way regression proving the existing Wikipedia converter remains unchanged.

## Explicitly out of scope

H18 does not:

- fetch a URL;
- follow redirects;
- perform DNS resolution;
- open sockets;
- call `requests`, `httpx`, a browser or a subprocess;
- authenticate to Wikipedia or any other service;
- edit or submit Wikipedia content;
- model Wikipedia revisions, edit tokens, page IDs or MediaWiki write APIs;
- treat derived Markdown as native HTML ownership;
- expose `replace_text` as writable;
- expose identity-Markdown writeback;
- mutate the materialized HTML snapshot;
- synthesize a replacement HTML page;
- create a local editable Markdown artifact as part of the reader;
- handle RSS, Atom, Bing SERP, YouTube or Azure extraction in H18;
- change `WikipediaConverter` or the public one-way `MarkItDown` behavior.

Explicit local materialization of derived content is a later v0.9 capability. H18 only
establishes safe read semantics and provenance.

## Public module placement

The new code lives under a source-adapter namespace rather than pretending Wikipedia is
a native file format.

Recommended layout:

```text
packages/markitdown/src/markitdown/twoways/readers/remote.py
packages/markitdown/tests/twoways/test_remote_wikipedia_reader.py
packages/markitdown/tests/twoways/test_remote_wikipedia_public_imports.py
```

The stable public exports are available from:

```python
from markitdown.twoways.readers.remote import (
    RemoteDerivedLimits,
    read_wikipedia_snapshot_ir,
)
```

and, after the public-import gate passes, from the top-level `markitdown.twoways`
surface if doing so does not create an import cycle.

H18 does not add a writer registration.

## Input contract

`read_wikipedia_snapshot_ir()` accepts:

- `source_stream: BinaryIO`;
- keyword-only `stream_info: StreamInfo`;
- optional `limits: RemoteDerivedLimits`.

### URL authority

`stream_info.url` is mandatory.

The URL must:

- use `http` or `https`;
- be accepted by the same Wikipedia URL shape as the existing one-way
  `WikipediaConverter`;
- contain no credentials;
- have a valid non-empty host;
- identify a Wikipedia host supported by the current converter.

H18 must not broaden one-way Wikipedia URL acceptance.

A non-Wikipedia URL is rejected instead of being silently downgraded to generic HTML.

### Snapshot authority

The reader consumes only the supplied stream.

The complete snapshot is captured under the configured byte limit. The reader records:

- SHA-256;
- exact byte size;
- filename, MIME type and charset when supplied by `StreamInfo`;
- source URI;
- one-way converter identity;
- one-way converter baseline identifier used by the implementation;
- derived Markdown digest and size.

No metadata supplied by the HTML page is allowed to replace source URI authority.

### Stream-position rule

The H18 public reader may consume the caller's source stream like existing 2Ways readers.
Internal calls to the one-way converter must use a private `BytesIO` over the captured
snapshot so converter `accepts()`/`convert()` behavior cannot alter caller-owned
stream state after capture.

## Resource limits

H18 introduces a small immutable limit object:

```python
@dataclass(frozen=True)
class RemoteDerivedLimits:
    max_source_bytes: int = 32 * 1024 * 1024
    max_markdown_utf8_bytes: int = 16 * 1024 * 1024
```

Requirements:

- both limits are positive integers;
- booleans are rejected;
- source capture must fail before retaining bytes beyond `max_source_bytes`;
- derived Markdown is UTF-8 encoded only for measuring the output budget;
- exceeding either limit fails closed;
- the limits affect only H18 read work and do not mutate global one-way settings.

Later v0.9 tranches may extend the limit model, but H18 must not silently reinterpret
these two fields.

## One-way semantic parity

The H18 derived text must match the public one-way Wikipedia semantic result for the same
materialized bytes and `StreamInfo`.

The parity oracle is:

```python
MarkItDown().convert_stream(
    BytesIO(snapshot),
    stream_info=stream_info,
).markdown
```

Tests compare the H18 text payload to this public result exactly.

Production H18 code must not perform an HTTP request to obtain this parity.

The implementation may invoke the existing `WikipediaConverter` directly against a
private byte stream and reproduce the public one-way normalization rules, but parity
tests are authoritative. If the public one-way normalization changes later, H18 must
either track it deliberately or fail its parity tests; silent semantic drift is not
allowed.

H18 must verify that the supplied URL is accepted as Wikipedia before constructing IR.
If the specialized Wikipedia converter would not own the snapshot under the supplied
stream information, the reader rejects the input instead of falling back to another
converter.

## Remote-derived evidence model

H18 stores a versioned evidence record in document metadata under:

```text
twoways.remote_snapshot.v1
```

The record contains at minimum:

```json
{
  "kind": "wikipedia",
  "uri": "https://en.wikipedia.org/wiki/Example",
  "source_sha256": "...",
  "source_size_bytes": 12345,
  "converter": "WikipediaConverter",
  "converter_blob_sha": "ba0c751092fa9e37fcf982f1fae9c4dcd774e049",
  "markdown_sha256": "...",
  "markdown_utf8_size_bytes": 6789,
  "network_performed_by_twoways": false
}
```

Optional source hints such as MIME type, charset and filename may also be retained.

The evidence record is descriptive provenance. It does not grant mutation authority.

The metadata key is versioned so later source adapters can add different evidence
without changing the `DocumentIR` wire version.

## IR mapping

H18 creates one document, one canvas and one root text node.

### SourceDescriptor

The source descriptor records:

- `format="remote-wikipedia-snapshot"`;
- `filename` from `StreamInfo.filename` when present;
- `mimetype` from `StreamInfo.mimetype` when present;
- `uri=stream_info.url`;
- `sha256` of the materialized snapshot bytes;
- `size_bytes` of the snapshot;
- no claim that the remote resource can be rewritten.

`preserved_source_ref` remains unset in H18 because the reader does not install a
persistent local source store.

### Document metadata

`DocumentMetadata.title` uses the one-way result title when present.

`DocumentMetadata.custom` contains the versioned remote-snapshot evidence.

### Canvas

The document contains one:

```text
Canvas(kind="remote-derived")
```

The canvas has one root node and no native locator.

### Root text node

The node:

- has `kind="text"`;
- has semantic role `derived_document`;
- has `TextPayload(text=<one-way markdown>)`;
- has no native locator;
- has no geometry;
- records derived provenance;
- carries capability metadata described below.

H18 does not parse the Markdown into independently writable paragraphs/tables. The
one-way Markdown string is the semantic parity object for this tranche.

## Provenance

The root node contains one `Provenance` entry:

- `source_format="remote-wikipedia-snapshot"`;
- `extraction_method="WikipediaConverter"`;
- metadata with source URI, source snapshot digest, derived Markdown digest and an
  explicit `remote_writeback=False` marker.

No `NativeLocator` is attached.

This distinction is essential: provenance explains where text came from; a native
locator would imply a mutation owner and is therefore forbidden in H18.

## Capability contract

The root node carries exactly one explicit semantic edit decision in H18:

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

Consequences:

- `capabilities_for_node(node).for_operation("replace_text")` returns `DERIVED`;
- `build_capability_report(document)` counts the node as derived;
- `writable_by_operation` remains empty;
- unknown operations still default to read-only through the existing kernel;
- no H18 code converts the derived state to writable.

The exact reason code is stable for the v0.9 program:

```text
remote.source.not_native_writable
```

## Diagnostics

H18 adds a deterministic information diagnostic at document level:

```text
code: remote.source.not_native_writable
severity: info
```

The message explains that the visible Markdown is derived from a materialized remote
snapshot and cannot be written back to the remote origin by H18.

The diagnostic must not claim that Wikipedia itself is immutable; it describes only the
absence of mutation authority in this IR.

## Deterministic identity

H18 uses a deterministic document-local ID seed derived from stable evidence:

```text
remote-wikipedia-snapshot
+ source URI
+ source SHA-256
+ derived Markdown SHA-256
+ converter identity
```

Two reads of identical inputs under the same converter semantics must produce identical
document/canvas/node IDs and identical canonical serialization.

A changed URI, snapshot digest or derived Markdown digest changes the identity seed.

No timestamp, randomness, response date or wall-clock value participates in IDs.

## No writer

H18 intentionally adds no writer.

There is no:

- `patch_wikipedia`;
- `write_remote`;
- `update_remote_page`;
- remote writer registry entry;
- generic fallback writer for the derived text node.

Attempting to discover a native writer for this H18 document must fail through the
normal registry/capability path.

Future explicit local materialization must use a distinct API and produce a local
artifact with a new local source descriptor; it must never retroactively make the H18
remote document writable.

## Security and trust boundaries

### Network firewall

No module under the H18 2Ways reader may import or call `requests`, `httpx`,
`urllib.request`, socket APIs, browser automation or subprocess execution.

Tests should enforce this structurally where practical.

### URL is provenance, not a fetch instruction

The URL is recorded and validated but never dereferenced.

### Snapshot digest is not remote freshness

A source SHA-256 proves the exact bytes H18 analyzed. It does not prove what the remote
server serves later.

### Derived content is untrusted text

The Markdown may contain links, HTML fragments or content controlled by the remote
source. H18 stores it as text and does not execute it.

### No credential propagation

URLs containing user-info credentials are rejected. H18 does not accept authentication
headers or cookies.

### Fail closed

Malformed URLs, non-Wikipedia origins, missing URL provenance, oversized inputs,
converter ownership failure or parity inconsistency prevent IR construction.

## One-way invariance

H18 must not modify:

- `packages/markitdown/src/markitdown/converters/_wikipedia_converter.py`;
- the one-way converter registry ordering;
- `MarkItDown.convert_uri()`;
- `MarkItDown.convert_response()`;
- public HTTP fetching behavior;
- generic HTML converter behavior.

The final scope audit records the baseline Wikipedia converter blob:

```text
ba0c751092fa9e37fcf982f1fae9c4dcd774e049
```

and requires the same blob at the final H18 head.

## Test plan requirements

Implementation must proceed RED → GREEN.

### Reader/parity tests

At minimum:

- valid English Wikipedia snapshot produces one derived text node;
- valid two/three-letter Wikipedia language host accepted according to current one-way
  ownership rules;
- one-way result title is preserved;
- text payload equals public one-way MarkItDown stream output exactly;
- source URI/digest/size recorded exactly;
- Markdown digest/UTF-8 size recorded exactly;
- repeated reads are canonically deterministic;
- input source stream is not used for network I/O.

### Capability tests

At minimum:

- `replace_text` is `DERIVED`;
- reason code is exactly `remote.source.not_native_writable`;
- capability report counts one derived node and zero writable nodes;
- identity-Markdown mutation is not advertised;
- no writer registration exists.

### Provenance tests

At minimum:

- no native locator on canvas or node;
- provenance contains source URI and both source/result digests;
- `network_performed_by_twoways` is false;
- converter identity is preserved;
- forged caller metadata cannot turn the node writable because capability state is
  generated by the reader rather than accepted from input.

### Adversarial tests

At minimum:

- missing URL;
- `file:`, `data:`, FTP or other non-HTTP scheme;
- non-Wikipedia HTTP/HTTPS host;
- Wikipedia-like attacker host such as `wikipedia.org.example.com`;
- user-info credentials in URL;
- malformed/empty host;
- snapshot exactly at and one byte above source limit;
- result exactly at and above Markdown output limit;
- invalid limit values including zero, negatives and bool;
- specialized Wikipedia ownership rejection;
- empty/degenerate HTML remains derived rather than becoming writable.

### Serialization/public tests

At minimum:

- canonical JSON round trip preserves derived state and evidence;
- public imports remain stable;
- no schema-version bump;
- capability report after serialization remains identical.

### Regression tests

At minimum:

- existing one-way Wikipedia converter behavior remains green;
- baseline converter blob unchanged;
- full package tests Python 3.10–3.13;
- OCR tests Python 3.10–3.13;
- pre-commit;
- exact final-head verification;
- synthetic PR merge tree equality before merge.

## Expected implementation surface

The intended production delta is small:

```text
packages/markitdown/src/markitdown/twoways/readers/remote.py
packages/markitdown/src/markitdown/twoways/readers/__init__.py
packages/markitdown/src/markitdown/twoways/__init__.py
packages/markitdown/tests/twoways/test_remote_wikipedia_reader.py
packages/markitdown/tests/twoways/test_remote_wikipedia_public_imports.py
TWOWAYS.md
```

The implementation should not need to modify core `DocumentIR`, capability enums,
serialization schema, writer registries or one-way converters.

If implementation discovers that one of those core changes is required, H18 must stop
and return to design review rather than expanding scope silently.

## Completion gate

H18 is complete only when one frozen final branch head satisfies all of the following:

1. the implementation matches this design;
2. Wikipedia one-way converter blob remains
   `ba0c751092fa9e37fcf982f1fae9c4dcd774e049`;
3. no H18 production code performs network I/O;
4. no H18 writer or remote write capability exists;
5. exact one-way Markdown parity tests pass;
6. remote provenance/capability/adversarial tests pass;
7. public serialization/import tests pass;
8. PR changed-file scope contains only approved H18 reader/tests/docs/public exports;
9. pre-commit succeeds;
10. package tests succeed on Python 3.10, 3.11, 3.12 and 3.13;
11. OCR tests succeed on Python 3.10, 3.11, 3.12 and 3.13;
12. exact final-head court is 9/9 GREEN;
13. synthetic PR merge parents are current `main` plus the exact H18 final head;
14. synthetic merge tree equals the frozen H18 final tree;
15. guarded merge uses the exact expected H18 head SHA;
16. post-merge `main` parents/tree are revalidated.

## Follow-on v0.9 sequence

H18 deliberately establishes only the first Class-D proof.

After H18 is merged, the preferred continuation is:

- H19: reuse the remote-snapshot kernel for RSS/Atom and Bing SERP where derivation is
  still snapshot-local;
- H20: YouTube with explicit multi-input provenance for HTML plus transcript-service
  derivation;
- H21: Azure Document Intelligence bridge with endpoint/analyzer/API-version/service
  provenance and explicit derived semantics;
- H22: Azure Content Understanding bridge with modality/analyzer/model/service
  provenance;
- later: explicit local materialization semantics, still without implicit remote
  writeback.

Each tranche remains separately gated so no source is marked writable merely because a
one-way converter exists.
