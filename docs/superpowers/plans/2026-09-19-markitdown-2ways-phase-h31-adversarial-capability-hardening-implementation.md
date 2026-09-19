# H31 implementation plan

1. Freeze `CapabilityDecision.constraints` with a detached `MappingProxyType`.
2. Validate and normalize `NodeCapabilityProfile.default_state`.
3. Add adversarial tests for mutation, malformed wire values, duplicate operations and
   fail-closed fallback behavior.
4. Bind the H31 court to the frozen v1 support manifest so structural edits and derived
   writeback cannot silently enter the contract.
5. Run pre-commit plus package/OCR Python 3.10-3.13.
6. Merge only an exact tested head.
