# H32 implementation plan

1. Add a machine-readable v1 compatibility corpus.
2. Freeze canonical size and SHA-256 for minimal and representative IR documents.
3. Assert byte-identical encode/decode/encode behavior.
4. Freeze strict, forward and unknown-major decoder semantics.
5. Keep H31 hardening intact and add no runtime capability.
6. Run pre-commit plus package/OCR Python 3.10-3.13.
7. Merge only an exact tested head.
