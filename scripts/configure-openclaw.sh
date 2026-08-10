#!/usr/bin/env bash
#
# Apply OpenClaw's non-default configuration for Atlas.
# Safe to re-run: every `openclaw config set` is idempotent.
#
# Does NOT cover the gateway token or install steps — see
# docs/runbooks/ for the full OpenClaw setup procedure.
#
# Usage: ./scripts/configure-openclaw.sh

set -euo pipefail

command -v openclaw >/dev/null || { echo "ERROR: openclaw CLI not found" >&2; exit 1; }

echo "==> Model: point at the TAGGED id"
# Without the :latest tag OpenClaw cannot match this to the declared provider
# model, and silently invents a phantom descriptor that is text-only with a
# 200k context. Vision breaks and the context accounting is wrong.
openclaw config set agents.defaults.model.primary ollama/qwen3-vl-atlas:latest

echo "==> Workspace: scope the agent off the home directory"
# Default put the agent's workspace at /home/vraj, giving its file tools reach
# over ~/.ssh and the atlas repo. This confines it.
openclaw config set agents.defaults.workspace /home/vraj/.openclaw/workspace

echo "==> Tools: minimal baseline"
# 'coding' loaded ~9,280 tokens of tool definitions on every request, against
# an 8,000-token input budget — nothing fit, not even "say hello".
# 'minimal' drops that to ~8,264 and removes shell/filesystem/web access.
openclaw config set tools.profile minimal

echo "==> Tools: add back the image tool"
# 'minimal' strips `image`, which vision obviously needs. alsoAllow MERGES on
# top of the profile; plain `allow` would REPLACE it entirely.
openclaw config set tools.alsoAllow '["image"]' --strict-json

echo "==> Compaction: shrink the response reserve"
# Default reserved 8,000 of the model's 16,000 context for the reply, leaving
# only 8,000 for input. 2,000 is ample for these responses and returns ~6,000
# tokens of usable prompt space.
openclaw config set agents.defaults.compaction.reserveTokens 2000

echo "==> Gateway: disable the insecure Control UI auth flag"
openclaw config set gateway.controlUi.allowInsecureAuth false

echo "==> Validating"
openclaw config validate

echo "==> Done. Restart the gateway to apply:  systemctl --user restart openclaw-gateway"
