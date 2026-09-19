# MarkItDown 2Ways Phase H30 — v1.0 contract and support-matrix closure

Date: 2026-09-19
Status: frozen design
Base: `main@64cce7b05f5bce47c466a1ab6f85403c8269faf9`

## Purpose

H30 closes the roadmap's v1.0.0 gate. It does not add a new converter, writer, mutation
surface, remote writeback path or serializer. Its job is to freeze the already-proven
2Ways behavior into a reviewable, machine-checked release contract.

The full-parity roadmap says v1.0.0 is permitted only when public capability contracts,
source-preservation semantics and the format support matrix are stable enough to maintain
long term. H1-H29 established those behaviors tranche by tranche; H30 makes the resulting
boundary explicit and regression-protected.

## Non-goals and compatibility invariants

H30 must not:

- change the upstream MarkItDown package version;
- change `MarkItDown2WaysDocument` schema name or schema version `0.1.0`;
- change the supported IR schema major;
- alter `twoways.capabilities.v1` wire semantics;
- add/remove/rename a public root symbol merely to satisfy the gate;
- add a native writer to any H18-H29 derived adapter;
- alter one-way converter implementations;
- widen any native writable boundary;
- claim archive structural editing, remote writeback or unsupported media/PDF mutation.

The v1 product/release gate is independent from the serialized IR schema major. A future
IR schema major bump is a separate compatibility event and is not implied by H30.

## Machine-readable v1 contract

Add `docs/twoways-v1-contract.json` containing:

1. contract identity/version;
2. IR schema name/version and supported major;
3. capability metadata key and stable state values;
4. the exact public `markitdown.twoways.__all__` surface at the gate;
5. the native support matrix with direct/routed operations and preservation notes;
6. the H18-H29 derived support matrix with explicit `native_writeback=false`;
7. explicitly out-of-scope mutation surfaces.

The manifest is descriptive of implementation already proven by H1-H29. It is not a
runtime registry and must not become an alternate dispatch mechanism.

## Public-contract court

A v1 contract test must fail closed when the manifest and runtime diverge. At minimum it
must prove:

- contract version is exactly `1.0.0`;
- IR schema remains `MarkItDown2WaysDocument@0.1.0`;
- supported schema major remains 0;
- capability metadata key remains `twoways.capabilities.v1`;
- capability states remain exactly writable/read-only/derived;
- every manifest public root symbol exists and the manifest set exactly equals
  `markitdown.twoways.__all__`;
- native and derived matrix keys are unique and complete;
- every derived entry explicitly denies native writeback;
- the documented v1 gate section references the machine-readable manifest.

Any future public-contract change must update the manifest and its tests intentionally in
the same change.

## Support-matrix authority

The matrix freezes capability boundaries, not broad file-format marketing claims.
"Writable" means only the listed, already-proven typed operation and constraints.
Derived rows remain read-only even when another native adapter for the same physical
format exists.

ZIP is represented as a preservation/routing container: it can route supported inner
typed operations but archive structure itself remains read-only.

DOCX/PPTX rows list only edit types currently accepted by their native writers. XLS/XLSX
share the `update_sheet_cells` operation name but retain separate native authority and
format-specific constraints.

## Documentation closure

`TWOWAYS.md` gains a v1.0 contract-freeze section that:

- points to the manifest;
- distinguishes the v1 product gate from IR schema versioning;
- records H30 as a no-capability-expansion closure tranche;
- adds H28, H29 and H30 execution documents to the v1.0-gate roadmap list.

## Exact completion authority

H30 is complete only when the exact final branch head has:

- pre-commit SUCCESS;
- package tests SUCCESS on Python 3.10, 3.11, 3.12 and 3.13;
- OCR tests SUCCESS on Python 3.10, 3.11, 3.12 and 3.13;
- final scope review showing only H30 contract/docs/tests;
- 0-behind relation to the frozen base;
- synthetic two-parent merge proof with exact tree equality;
- expected-head guarded merge;
- post-merge verification of main parents/tree.

No v1 completion claim is valid before that exact-head closure.
