# Contributing

English and Chinese contributions are welcome. A small reproducible experiment is more useful than a broad capability claim.

~~~bash
uv sync --frozen
uv run --frozen pytest -q --basetemp runtime/pytest
~~~

Use fresh runtime directories. Default tests isolate models; infrastructure requires explicit opt-in. See [evaluation](docs/evaluation.md).

Good first contributions: English UI, focused regression cases, synthetic missing/conflicting evidence, documentation and bounded adapters. Larger study ideas are in [research](docs/research.md).

For new tools, define typed inputs/outputs, scope/resource limits, failure behavior, independent validation and publication rules. Preserve the distinction between execution success, business conformity and permission to publish.

## Pull requests

1. Describe concrete input, observed behavior and intended behavior.
2. Keep scope focused and record configuration/fixture revision.
3. Add meaningful regression coverage for changed behavior.
4. Report the relevant checks and actual outcomes.
5. Distinguish real models, mocked responses and rules. Record usage without credentials.

Do not include .env, tokens, passwords, real customer records, private documents, databases or browser profiles. Never paste complete request headers into issues.

No CLA is required. Contributions use MIT; respect the terms of added dependencies/data.
