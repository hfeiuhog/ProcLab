# Public source release validation

Date: 2026-10-23. Reference environment: Windows, Python 3.12.3, existing locked project dependencies. The local checks reused the installed dependency environment; the public CI installs from the lock in a clean runner.

| Check | Actual local outcome |
|---|---|
| Complete offline regression | 131 passed, 1 skipped |
| Skipped check | MySQL/Redis/Milvus infrastructure test; not opted in |
| Authored fixture counts | 63/63 batches agree with violation/missing-count labels |
| Synthetic holdout | 10/10 batches agree; same generator, not an external distribution |
| End-to-end smoke scenarios | 8/8 expected terminal states |
| Heating design | Real SciPy 1.18.1 subprocess; completed; independent check passed |
| Heating decisions in this check | Explicit offline rules; zero native model decisions |
| Desktop and mobile workbench | Real Chromium, synthetic isolated state, no page errors or horizontal overflow |

Commands and metric limitations are documented in [evaluation.md](evaluation.md). The data digest is recorded in data/dataset_manifest.json. No live paid model, OCR/transcription, or infrastructure success is claimed by these checks.

The public screenshot uses newly generated synthetic tasks, not historical user sessions. Private settings, databases, server-specific materials and internal deployment evidence are excluded. The tracked-file check is a heuristic; it does not constitute a security audit.

The validation outcomes are specific to this public preparation. Later commits should be assessed using their actual CI and experiment records.
