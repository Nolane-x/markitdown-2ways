# H33 implementation plan

1. Record H32 production file-count/source-byte/max-file baselines.
2. Define bounded v1 engineering ceilings with modest explicit headroom.
3. Add a deterministic CI court for source size, file count and largest-file size.
4. Freeze public/native/derived cardinalities against accidental expansion.
5. Freeze the core dependency set against silent bloat.
6. Avoid flaky wall-clock thresholds in required CI.
7. Run pre-commit plus package/OCR Python 3.10-3.13.
8. Merge only an exact tested head.
