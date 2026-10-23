# Evaluation and reproducibility

Separate deterministic tools, end-to-end behavior, infrastructure and actual model decisions. Passing one category does not establish the others.

## Regression

~~~bash
uv run --frozen pytest -q --basetemp runtime/pytest
~~~

Tests cover numerical tampering, missing/non-finite measurements, permissions, guarded SQL, outbox/recovery and mocked decisions. Infrastructure is skipped without explicit opt-in. [Public-release validation](public-release-validation.md) records the checks performed for this release; CI reruns them for later changes.

## End-to-end scenarios

~~~bash
uv run --frozen python -m scripts.smoke --output runtime/evaluation/smoke
~~~

Eight authored scenarios run through the service with models disabled. Outputs record expected/actual status, elapsed time and trace counts. This is functional validation, not a latency benchmark or proof of model reasoning.

## Fixture counts

~~~bash
uv run --frozen python -m scripts.evaluate --split all --output runtime/evaluation/all.json
uv run --frozen python -m scripts.evaluate --split holdout --output runtime/evaluation/holdout.json
~~~

The evaluator runs CSV/limit tools against authored violation/missing-count labels and checks the CSV digest. Count agreement does not establish citation identity, end-to-end publication correctness or semantic reasoning.

Holdout batches share the synthetic generator. They are not external industrial generalization data.

## Scientific path

~~~bash
uv run --frozen python -m scripts.verify_heating_agent --offline --output runtime/evaluation/heating
~~~

Real SciPy subprocesses and independent analytical checks run with explicit rules choices. Removing --offline opts into configured paid model calls. Model-backed evidence requires actual decisions that consumed prior observations; mocked responses do not count.

## Infrastructure

Configure isolated MySQL/Redis/Milvus plus embeddings/reranking, then set RUN_INFRA_TESTS=1 before pytest. This can download weights or call paid services and is excluded from public CI.

## Experiment record

Include commit, lock/fixture digests, split, model IDs, configuration changes, seeds, exact commands and failures/skips. Log returned token usage rather than inventing cost estimates. Strip credentials, private prompts and production records.
