#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
command -v docker >/dev/null
command -v uv >/dev/null
test -f .env || { printf '%s\n' 'First run: uv run python -m scripts.init_env --mode production'; exit 1; }
docker compose config --quiet
docker compose --profile full up -d --build --wait --wait-timeout 300
docker compose ps
printf '%s\n' 'Loopback inspection: http://127.0.0.1:8080'
printf '%s\n' 'Use the HTTPS overlay for browser login. Vector indexing is an explicit optional step.'
