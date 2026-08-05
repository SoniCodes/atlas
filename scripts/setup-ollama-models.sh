#!/usr/bin/env bash

set -euo pipefail

CONTAINER="ollama"
CUSTOM_MODEL="qwen3-vl-atlas"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
MODELFILE="$REPO_ROOT/stacks/ollama/Modelfile"

# Single source of truth: read the base model out of the Modelfile itself
# instead of hardcoding it here too.
BASE_MODEL="$(awk '/^FROM/ {print $2}' "$MODELFILE")"

echo "==> Checking prerequisites"
if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "ERROR: container '$CONTAINER' is not running." >&2
  echo "Start it first:  docker compose -f $REPO_ROOT/stacks/ollama/docker-compose.yml up -d" >&2
  exit 1
fi
[ -f "$MODELFILE" ] || { echo "ERROR: Modelfile not found at $MODELFILE" >&2; exit 1; }

echo "==> Pulling base model: $BASE_MODEL"
docker exec "$CONTAINER" ollama pull "$BASE_MODEL"

echo "==> Copying Modelfile into container"
docker cp "$MODELFILE" "$CONTAINER:/root/Modelfile"

echo "==> Creating custom model: $CUSTOM_MODEL"
docker exec "$CONTAINER" ollama create "$CUSTOM_MODEL" -f /root/Modelfile

echo "==> Verifying"
docker exec "$CONTAINER" ollama show "$CUSTOM_MODEL" | grep -A5 "Parameters"

echo "==> Done. '$CUSTOM_MODEL' is ready."
