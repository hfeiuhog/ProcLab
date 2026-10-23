# Portable single-host deployment

Start with the offline demo. The supplied stack is a research deployment, not a high-availability production design.

Use a Linux host with Docker Engine/Compose and uv. The complete stack includes MySQL, Redis, Milvus, etcd, MinIO, the app and a reverse proxy. Size resources against actual workload; no capacity guarantee is provided.

Clone the public repository. Never upload a workstation .venv or private .env.

~~~bash
uv sync --frozen --no-dev
uv run --frozen python -m scripts.init_env --mode production
# Configure optional model credentials privately.
sh scripts/deploy.sh
~~~

Initialization prompts for account passwords and generates infrastructure credentials. Preserve existing private settings during upgrades.

## HTTPS

The base proxy binds to 127.0.0.1:8080 for SSH-tunnel inspection. For a DNS domain, set SITE_ADDRESS, configure valid DNS and use:

~~~bash
docker compose -f compose.yaml -f compose.https.yaml --profile full --profile https up -d --build
~~~

Only expose the public entry and necessary SSH access. Database/vector stores stay private. Domain HTTPS configuration is portable; private IP certificates and renewal units are excluded. Secure production cookies require the HTTPS browser endpoint.

## Optional vector indexing

~~~bash
docker compose --profile full exec -T app /app/.venv/bin/python -m scripts.seed
~~~

This may download weights or invoke a configured service. It is an explicit step, not part of offline validation.

## Preserve state

MySQL holds business state. The app-runtime volume holds uploaded documents and the analytical SQLite database. Redis is a cache; vector persistence includes Milvus dependencies.

Use consistent logical MySQL backups and consistent SQLite backups. Store backups/private settings off-host and test restoration independently. Do not use docker compose down -v for ordinary upgrades.

Keep one Uvicorn worker. Distributed task ownership and cross-instance leases are not implemented.

Platform references: [Docker installation](https://docs.docker.com/engine/install/) and [uv](https://docs.astral.sh/uv/).
