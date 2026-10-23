<div align="center">

# ProcLab

### Evidence before conclusions.

**A research workbench for traceable industrial agents, guarded analytics, and feedback-driven scientific tools.**

[中文](README.zh-CN.md) · [Architecture](docs/architecture.md) · [Research guide](docs/research.md) · [Contributing](CONTRIBUTING.md)

![Python](https://img.shields.io/badge/Python-3.11–3.13-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-10b981)
[![CI](https://github.com/hfeiuhog/ProcLab/actions/workflows/ci.yml/badge.svg)](https://github.com/hfeiuhog/ProcLab/actions/workflows/ci.yml)

</div>

![ProcLab workbench — generated locally with synthetic fixtures and offline rules](assets/workbench.png)

An agent can finish a task and still reach an unsupported conclusion. ProcLab makes that distinction inspectable: plans, tool inputs, source versions, independent checks, review decisions, and published results remain connected.

It is a working research prototype built around **synthetic process data**. Start locally without API keys, then connect your own models and retrieval services to study what changes.

## What you can explore

| Research question | Implemented mechanism | Start reading |
|---|---|---|
| Can an agent stay within a task's scope? | Frozen plans, capability contracts, bounded DAG scheduling, tool allowlists | [orchestration/](app/orchestration/) |
| Can a fluent answer survive independent checks? | Source identity/version checks, Decimal recomputation, publication gates | [steps.py](app/steps.py), [harness.py](app/harness.py) |
| Can a model use a tool's actual feedback? | Bounded heating-design loop with recorded decisions, observations and solver calls | [design.py](app/design.py) |
| Can analytics preserve metric meaning? | Semantic plans compiled to SQL, server-bound scope, read-only authorizer | [analytics/](app/analytics/) |
| Can incomplete evidence stay incomplete after approval? | Human review, supplements, preserved repair/result versions | [evidence.py](app/evidence.py) |
| Can results survive a restart? | SQL checkpoints, transactional outbox, replayable analytical read model | [store.py](app/store.py), [checkpoint.py](app/checkpoint.py) |

The specialist path uses a persistent DAG runtime; the original LangGraph path remains for compatibility. Nodes within one task run sequentially. Independent tasks share a bounded thread pool.

## Quick start

**Python 3.12 is the reference environment**; the package declares Python 3.11–3.13. Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

~~~bash
git clone https://github.com/hfeiuhog/ProcLab.git
cd ProcLab
uv sync --frozen
uv run --frozen uvicorn app.api:app --host 127.0.0.1 --port 8000
~~~

Open **http://127.0.0.1:8000**.

The defaults use SQLite, offline lexical retrieval, and deterministic rules. No Docker services, model credentials, or embedding-model downloads are required. The UI is primarily Chinese; this guide and the research protocols are in English.

The loopback-only starter has authentication disabled. For account isolation or server deployment, follow [Configuration](docs/configuration.md) and [Deployment](docs/deployment.md).

### Try these experiments

| Scenario | Prompt/input | Expected behavior |
|---|---|---|
| Out-of-range measurements | 分析 B-102 批次的温度、压力和黏度，列出超限证据 | Six parameter violations, independently checked |
| Missing evidence | 分析 B-103，缺失数据不得补值 | Pauses for review |
| Historical analytics | 按设备统计全部模拟批次的超限批次比例 | Governed metrics and inspectable SQL |
| Heating simulation | 用一阶模型仿真升温过程，反算达到目标温度的时间 | Numerical/analytical cross-check |
| Heating design | Use “设计升温方案：试算与调整” in the workbench | Bounded candidate trials with stopping reason |

Heating design requires initial/target temperature, time constant, deadline, oven bounds and an objective. Missing constraints trigger clarification. Offline trials use an explicitly labeled rules fallback; connect a model to study feedback-driven decisions.

## Reproduce the checks

~~~bash
# Deterministic regression suite; no paid models
uv run --frozen pytest -q --basetemp runtime/pytest

# Eight end-to-end fixture scenarios
uv run --frozen python -m scripts.smoke --output runtime/evaluation/smoke

# Count-based deterministic fixture benchmark
uv run --frozen python -m scripts.evaluate --split all --output runtime/evaluation/fixtures.json

# Held-out synthetic batches, separated by batch ID
uv run --frozen python -m scripts.evaluate --split holdout --output runtime/evaluation/holdout.json

# Real SciPy, with explicit offline decisions
uv run --frozen python -m scripts.verify_heating_agent --offline --output runtime/evaluation/heating
~~~

[Evaluation](docs/evaluation.md) explains the limits of each check. The fixture benchmark measures deterministic tools against authored labels; it does not measure LLM reasoning or external industrial accuracy.

## How a run works

~~~mermaid
flowchart LR
    A[Task + constraints] --> B[Frozen plan]
    B --> C[Scoped agent runtime]
    C --> D[Tool gateway]
    D --> E[Sources + calculations]
    E --> F[Independent checks]
    F --> G{Sufficient evidence?}
    G -->|Yes| H[Versioned result]
    G -->|No| I[Review / supplement]
    I --> B
    H --> J[Outbox + analytical read model]
~~~

**Business state:** SQLite locally or MySQL. **Short-term context:** SQL with optional Redis. **Retrieval:** lexical by default, with optional Milvus vectors and reranking. **Analytics:** a separate SQLite read model with ODS/DWD/DWS/ADS layers. **Scientific tools:** fixed SciPy subprocesses plus independent analytical checks.

## Dataset and scientific boundaries

- **487 measurements, 63 synthetic batches, 10 authored scenarios**, including 10 synthetic holdout batches. See the [dataset card](data/README.md).
- Limits come from a self-authored, versioned mock SOP, not an industry standard.
- Small sample summaries do not establish process capability, causality, or factory compliance.
- The first-order heating model is not commercial CAE, curing kinetics, or a device controller.
- Hashes bind stored artifacts; they do not authenticate real sensors.
- Distributed ownership, high availability and production hardening remain engineering work.

## Research and contributions

Useful contributions include retrieval ablations, adversarial evidence tests, recovery experiments, multilingual UI work and additional bounded scientific tools. Proposed studies and metrics are in [the research guide](docs/research.md).

[Open an issue](https://github.com/hfeiuhog/ProcLab/issues/new/choose) with a reproducible bug or experiment proposal. Include inputs, configuration **without secrets**, data revision and the boundary you are testing.

~~~text
app/                    API, workbench, checks, retrieval and persistence
  orchestration/        Plans, contracts, scheduling and tool gateway
  analytics/            Semantic metrics, SQL guard and read model
data/                   Synthetic fixtures and attributed source summaries
scripts/                Initialization, evaluation and reproducibility
tests/                  Behavioral, numerical and recovery regression
deploy/                 Portable proxy/vector-store configuration
docs/                   Architecture, configuration and research protocols
.github/                CI and contribution templates
~~~

## License and citation

Code and project-authored synthetic fixtures use [MIT](LICENSE). Attributed summaries link to their sources; third-party dependencies, services and models retain their own terms. No weights, private credentials or production records are included.

Use [CITATION.cff](CITATION.cff) and identify the release/commit used. ProcLab has no associated peer-reviewed paper, DOI, or claimed industrial benchmark result.
