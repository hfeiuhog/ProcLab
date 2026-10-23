# Architecture

~~~mermaid
flowchart TD
    A[Task + explicit constraints] --> B[Account/project scope]
    B --> P[Requirement planner + SuperAgent]
    P --> F[Freeze DAG / versions / inputs / budget]
    F --> S[Supervisor: ready dependencies]
    S --> R[Persistent runtime + agent calls]
    R --> T[Tool gateway: scope and contracts]
    T --> K[Retrieval / batch / statistics]
    T --> Q[Semantic plan / guarded SQL]
    T --> N[Bounded scientific subprocess]
    K --> E[Evidence and independent checks]
    Q --> E
    N --> E
    E --> H{Publication gate}
    H --> V[Versioned result or human review]
    V --> O[Transactional outbox]
    O --> W[Independent analytical read model]
    W --> Q
~~~

## Execution boundaries

The requirement planner maps a task to registered capabilities and freezes scope, implementation fingerprints, model settings, source versions and budgets. The supervisor schedules dependency-ready nodes. The runtime records attempts, calls and handoffs; the gateway checks tool permissions and trusted arguments.

The specialist path lives in app/orchestration. Nodes within a task run sequentially; independent tasks use a bounded executor. The original LangGraph path remains compatible. Cross-process task ownership is not implemented.

## State and stores

| Store | Responsibility |
|---|---|
| SQLite / optional MySQL | Conversations, tasks, accounts, plans, evidence indexes, results, outbox and checkpoints |
| Optional Redis | Expiring short-term context cache, reloadable from SQL |
| Optional Milvus | Dense knowledge retrieval with configured embeddings |
| Separate analytical SQLite | ODS/DWD/DWS/ADS read model; generated from fixtures and durable events |
| runtime/documents | Uploaded artifacts and parsed/reviewed document versions |

## Evidence and publication

Current versioned sources and original measurements remain authoritative. Source identity/digests, numerical snapshots and tool ledger bindings are checked independently of fluent text. Decimal recomputation covers process-limit comparisons; heating calculations are checked against an independent analytical solution.

Execution success, business conformity and permission to publish are separate fields. Human approval of an incomplete case must retain limitations. A repair produces a new version instead of silently replacing the original.

Hashes help bind persisted content; they cannot certify real sensors or physical correctness.

## Analytics

Natural-language intent maps to a bounded metric/dimension plan. SQL is compiled from that plan with server-bound scope, then checked against the expected compilation and executed via a read-only connection, SQLite authorizer and time limit.

Query snapshots preserve their plan/source binding. Result publication and outbox insertion share a transaction; consumers apply events idempotently. Measurement layers can be rebuilt from versioned fixtures, while result layers can be replayed from durable events.

## Scientific design

The heating-design loop records constraints, decisions, trials, observations and stopping reasons. A model may request a candidate, finish or clarify; the program enforces bounds and budgets. Fixed SciPy subprocesses perform solve_ivp/brentq calculations, independently checked against the first-order analytical model.

No arbitrary code execution, device actuation, commercial CAE or distributed scientific scheduler is claimed.
