# Research guide

These are proposed experiments, not completed ablations or external benchmark claims.

## Retrieval and evidence grounding

**Question:** Which retrieval changes improve current-SOP selection without weakening provenance?

Compare lexical, dense, RRF and reranking with fixed queries and document revisions. Hold the generator model constant. Measure current-revision recall@k, wrong-version citations, unsupported claims, latency and failures.

Entry points: app/rag.py, knowledge_library.py, steps.py. Add conflicting/historical mock SOPs while retaining the authoritative-limit rule.

## Feedback-driven scientific decisions

**Question:** Do model choices improve feasible-candidate discovery under a fixed trial budget?

Compare rules and native-function decisions using identical constraints, solver versions and independent checks. Measure feasible-run rate, violations, trials to first feasible result, objective among tested candidates, stopping behavior and returned usage.

Entry points: app/design.py, solver_worker.py, tests/test_heating_agent.py. The best tried candidate is not a global optimum; a model-specific inverse threshold is not a factory recommendation.

## Corruption and uncertainty retention

**Question:** Which layers stop an apparently successful execution from publishing unsupported conclusions?

Independently mutate row IDs, versions, numerical snapshots and tool ledger references. Remove values and inject NaN/Inf or contradictory sources. Measure tamper detection, unsupported publication, false rejections and correctly retained review states.

Keep authoritative checks active in shared demos; experiments that disable them belong in isolated runs.

## Governed analytics

**Question:** Can metric meaning and scope survive paraphrases and adversarial requests?

Freeze the semantic catalog; vary utterances, project scope and dimensions. Include unsupported metrics/ambiguous windows. Measure plan correctness, clarification, unauthorized-query rejection and equality to independently computed aggregates.

Entry points: app/analytics/semantic.py, sql_guard.py and warehouse.py. SQL execution success is separate from answer correctness.

## Recovery and publication

**Question:** What survives interruption at each durable boundary?

Interrupt after plan freeze, tool completion, publication and outbox consumption. Compare restored plans, duplicate effects, revisions and rebuilt read models.

Entry points: app/checkpoint.py, store.py and orchestration/repository.py. Current guarantees are single-process; cross-instance ownership requires additional work.

## New bounded scientific tools

Adapters should have typed contracts, resource limits, scope policy, provenance and an independent check. Candidates include richer thermal models, constrained estimation and validated measurement transforms. State physical assumptions and invalidating conditions.

## Minimal protocol

1. State a falsifiable hypothesis and predefine outcomes.
2. Record commit, lock digest, data sources, split and configuration.
3. Establish a deterministic baseline before enabling models.
4. Vary one factor; retain failures and abstentions.
5. Report all runs, including quota/model/timeouts.
6. Share sanitized commands/artifacts and separate evidence from interpretation.

Use the research Issue template to discuss a study. Clear negative results and small repeatable experiments are welcome.
