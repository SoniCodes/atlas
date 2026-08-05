# 0002: Use qwen3-vl:4b instead of moondream

**Status:** Accepted. Supersedes [0001](0001-use-moondream-instead-of-qwen-for-local-vision.md)

## Context

ADR 0001 landed on moondream. It works, but it's vague: "at least ten individuals"
instead of a number. That's not good enough for the card-reading feature, where the
exact value is the entire point.

At 1.7GB it was also leaving most of the 8GB card unused. So I had room to spend
memory to buy accuracy.

## Decision

`qwen2.5vl:4b` doesn't exist. That generation only ships 3B, 7B, 32B and 72B.
Ruled out immediately.

I rejected `qwen3-vl:8b` without testing it. 6.1GB of weights plus roughly 1.4GB
of fixed cost for the vision encoder (the part that turns an image into something
the model can read) puts it at the same margin that already blew up in ADR 0001. I
didn't need to repeat that experiment to know how it ends.

I chose `qwen3-vl:4b`: newer generation, 3.3GB, and specifically good at reading
text inside images.

It immediately hit a context-size error: a detailed description needed 8,056 tokens
against Ollama's default limit of 4,096. The context window is how much the model can
hold at once: image, prompt and answer combined. This looks like the failure in ADR
0001, but it's a different problem. In 0001 I was out of memory. Here I had memory
to spare and was just hitting a default that was set too low.

I fixed it with a Modelfile setting `num_ctx 16000`, which produces a custom model
called `qwen3-vl-atlas`. It has to be a Modelfile. Setting it live with
`/set parameter` only lasts for that session and is gone next time.

## Consequences

Clearly more precise than moondream. It read partial text off the blackjack table
and correctly identified the camera angle.

It costs 6,931MiB of 8,192MiB when loaded, leaving about 1.2GB. That's enough
room for a small embedding model later for the planned RAG work, and not enough for
anything bigger alongside it.

`qwen3-vl-atlas` is built, not downloaded. It's created by `ollama create`, so it
only exists inside the Docker volume. `docker compose up -d` will not recreate it.
If that volume is ever lost, the model silently disappears and OpenClaw breaks,
because OpenClaw references that exact name. Run `scripts/setup-ollama-models.sh` on
any rebuild.

OpenClaw also needed correcting: it had registered a context window of 262,144 (the
theoretical maximum for the architecture) instead of the 16,000 this model actually
has. It would have happily sent prompts far too big to work.
