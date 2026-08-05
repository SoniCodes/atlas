# 0002: Use qwen3-vl:4b instead of moondream for local vision inference

## Context

ADR 0001 settled on moondream. It works, but its descriptions are vague — "at least ten
individuals" instead of an exact count. That's fine for general "what am I looking at"
queries but not for the planned card-reading feature, where exact values are the point.
At 1.7GB it also left most of the 8GB card unused, so there was room to trade headroom
for accuracy.

## Decision

- qwen2.5vl:4b does not exist — that generation is only 3B/7B/32B/72B. Ruled out.
- Rejected qwen3-vl:8b WITHOUT testing: 6.1GB weights plus the ~1.4GB fixed vision-encoder
cost lands at the same margin that already caused the OOM in ADR 0001.
- Chose qwen3-vl:4b — newer generation, 3.3GB, strong at reading text in images.
-> Hit a context-size error: a detailed description needed 8056 tokens against Ollama's
4096 default. Unlike the OOM in 0001, there was VRAM headroom to raise it.
- Fixed with a Modelfile (`num_ctx 16000`), creating a custom model: qwen3-vl-atlas.
Setting it live via `/set parameter` is session-only and does not persist.

## Consequences

Clearly more precise than moondream — read partial text off the blackjack table and
identified the camera angle.

Costs 6931MiB of 8192MiB when loaded, leaving ~1.2GB. Enough for a small embedding model
later (planned RAG work), not for anything larger alongside it.

qwen3-vl-atlas is built by `ollama create`, not pulled, so it exists only inside the Docker
volume. `docker compose up -d` will NOT recreate it, which would break OpenClaw silently
since it references that exact name. Run `scripts/setup-ollama-models.sh` on any rebuild.

OpenClaw also needed correcting — it registered contextWindow 262144 (the architecture max)
instead of the real 16000 limit.

Supersedes [0001](0001-use-moondream-instead-of-qwen-for-local-vision.md).

