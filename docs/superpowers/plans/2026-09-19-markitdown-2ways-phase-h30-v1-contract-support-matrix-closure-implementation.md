# MarkItDown 2Ways Phase H30 — implementation plan

Date: 2026-09-19
Base: `main@64cce7b05f5bce47c466a1ab6f85403c8269faf9`
Design: `2026-09-19-markitdown-2ways-phase-h30-v1-contract-support-matrix-closure-design.md`

## Execution discipline

Proceed strict RED -> GREEN. H30 is a release-contract closure tranche, not a capability
tranche. Production converter/writer/reader semantics remain unchanged.

## Task 1 — freeze RED v1 contract courts

Add `test_v1_contract_gate.py` before the contract manifest exists.

The court must require:

- contract version `1.0.0`;
- exact IR schema identity and supported major;
- exact capability wire key/state values;
- exact equality with root `markitdown.twoways.__all__`;
- complete unique native support rows;
- complete unique H18-H29 derived rows;
- `native_writeback=false` for every derived row;
- explicit out-of-scope surfaces;
- TWOWAYS v1 contract section and manifest reference.

Expected state: RED because the machine-readable v1 contract and docs closure do not yet
exist.

## Task 2 — add the machine-readable contract

Create `docs/twoways-v1-contract.json` from the already-proven implementation.

Do not infer unsupported write surfaces. Record current native operations only. ZIP is
routing/composition rather than archive-structure mutation.

## Task 3 — align TWOWAYS roadmap/documentation

Add the v1 contract-freeze section and complete the v1.0-gate execution list with H28,
H29 and H30.

Do not change source-preservation semantics or claim a package/IR version bump.

## Task 4 — focused GREEN

Run the v1 contract court plus the directly relevant public-import/capability/serialization
tests. Repair only demonstrated H30 defects.

## Task 5 — exact closure

Run exact final pre-commit plus package/OCR matrices on Python 3.10-3.13.

After 9/9 GREEN:

1. freeze final head/tree;
2. verify 0-behind relation and H30-only scope;
3. create two-parent synthetic merge and prove exact tree equality;
4. mark PR ready;
5. guarded merge with expected final head;
6. verify post-merge main parents/tree;
7. close/supersede stale historical draft PRs only when main demonstrably contains their
   completed work and the closure note identifies the replacement lineage.
