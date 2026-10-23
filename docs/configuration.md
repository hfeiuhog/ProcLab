# Configuration

Pydantic Settings reads environment variables and an optional local .env. No private file is needed for the loopback demo.

| Mode | State | Retrieval | Models |
|---|---|---|---|
| Default offline | SQLite in runtime/ | Lexical | Rules; no paid calls |
| Optional vector research | SQLite or MySQL | Milvus + configured embeddings/reranking | Independently configured |
| Shared deployment | Supplied MySQL stack | Same adapters | Opt-in services |

Copy .env.example to .env only when customizing settings. Git ignores the private file.

## Chat and planning

For a compatible service, configure USE_LLM=true, MODEL_PROVIDER=openai, OPENAI_BASE_URL, OPENAI_API_KEY and OPENAI_MODEL. The implementation expects native function/tool calls and structured arguments; compatibility is provider-specific.

For SiliconFlow, set MODEL_PROVIDER=siliconflow, SILICONFLOW_API_KEY and the applicable AGENT_MODEL/HIGH_RISK_EXTRACT_MODEL/RULE_REASONING_MODEL identifiers. Select identifiers supported by your own account. The repository does not promise model availability, pricing or interchangeable schemas.

Failures are bounded and recorded as fallback behavior. A rules run does not establish a successful model call.

## Retrieval

An empty MILVUS_URI keeps retrieval lexical. With Milvus, select a provider, model and matching dimension. FastEmbed can download weights on first vector use. Remote embeddings require a valid embedding configuration; chat access does not imply embedding access.

Hash embeddings are deterministic test fixtures, not semantic retrieval. Reranking is a separate optional service.

## Accounts

For account-based local experiments:

~~~bash
uv run --frozen python -m scripts.init_env --mode local
~~~

This enables authentication and creates private local credentials. The ignored .env holds initial local account passwords for the owner to retrieve; do not commit or share it.

Production initialization prompts for passwords without saving those prompted passwords in plaintext:

~~~bash
uv run --frozen python -m scripts.init_env --mode production
~~~

Production cookies are Secure. Use HTTPS for browser login. API_TOKEN is for backend administration.

## Documents and voice

Explicitly enable document parsing or voice transcription and configure the required service keys/model identifiers. Requests can transfer inputs to that provider. Use synthetic documents/audio and check provider terms.

Regression tests mock relevant remote responses; they do not validate live OCR/transcription services.

## Dependency provenance

pyproject.toml and uv.lock are authoritative. The verified lock records the Tsinghua PyPI mirror; this release preserves it instead of silently resolving new dependencies.

If that index is unavailable, choose a trusted index, change the project index declaration and regenerate the lock deliberately. Record the new lock digest in experiments. Python 3.12 is the reference environment; validate other declared versions in your target environment.
