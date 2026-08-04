# 0001: Use moondream instead of qwen2.5vl for local vision inference

## Context

Atlas runs on a single RTX 3070 with 8GB VRAM which is the only GPU available, no second card or
bigger one to fall back on. Goal was to get a vision-capable model running locally on Ollama,
to prove GPU passthrough actually worked end to end and to have a model ready for the Meta
Glasses project later.

## Decision

- Initially planned to use qwen2.5vl:7b. Pull succeeded (6GB on disk).
-> First inference request hit a CUDA out of memory error, ~7000MiB used.
-> Retried — hit a different error this time: context size exceeded (4110 tokens needed vs
4096 available). Two different failures, same root cause: not enough VRAM headroom for this
model's actual runtime footprint, not just its size on disk.
- Switched to moondream instead. Pull succeeded (1.7GB).
-> Test run on a real image completed with no errors, described the image correctly.

## Consequences

Confirmed with a continuous GPU utilization log that moondream actually uses the GPU — one
sample spiked to 94% during the request, then dropped back to idle, memory usage well under
the 8GB limit with real headroom left over.

Trade-off: moondream is noticeably less precise than a bigger model would be. Its description
of the test image used approximate language ("at least ten individuals") instead of exact
counts. Fine for general "what am I looking at" queries, but not reliable for anything needing
precise recognition, reading exact card values for a blackjack-advisor feature, for example,
will need a narrower, specialized approach instead of this model.
