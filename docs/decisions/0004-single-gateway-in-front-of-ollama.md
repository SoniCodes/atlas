# 0004: Make one gateway the only thing that talks to Ollama

**Status:** Proposed, not built yet. One section is unresolved (see "Open question").

## Context

The assistant will have three clients: a web UI, a phone app, and the Meta Ray-Ban
glasses. The glasses path is real now (hardware owned, supported country, iOS 17.2+,
Apple Developer account), so this is a constraint, not a hypothetical.

The hardware is one RTX 3070 with 7,841 MiB usable (8,192 minus 352 the driver keeps).
One GPU means one loaded model and one request at a time. All three clients share it.

I measured instead of guessing, because ADR 0003 burned me twice on that.

Switching models or context size costs 11.45 seconds. Ollama tears the old runner
down before building the new one, so you pay both ways in a single request. Three
runs, days apart: 11.45s, 11.49s, 11.49s. Cold load with matching settings is 5.08s;
warm with matching settings is 0.14s. That kills the design I wanted: small context
for glasses, large for the web assistant. Alternating would cost 11.45s each way.
One process has to own the settings. Every client lives with them.

Images dominate the cost, and 1024px is the floor. A full 4032x3024 phone photo is
4,033 tokens and 2.72s of prefill (the time spent reading input before the model
writes anything). At 1024px that's 1,054 tokens and 0.48s. At 640px it's still 1,054
tokens, so going smaller buys nothing. Quality held on the test image. Image tokens
cost about 3x text (1,485 tok/s vs the 4,387 tok/s from ADR 0003).

Thinking was over half the generation. `qwen3-vl:4b` has it baked in. All three ways
to turn it off are dead: `--think=false` and `/no_think` from ADR 0003, and
`"think": false` on Ollama 0.32.5 now. At `num_predict=120` it produced 120 tokens
and zero characters of answer. `qwen3-vl:4b-instruct` is the same size and
quantization. Same image, same limit: 595 characters of actual answer. Left to stop
naturally, 2.70s warm vs 4.73s, from about half the tokens, at an identical 4,683
MiB. More answer, less time, same memory.

Cold start is half a cold request. Default keep-alive is 5 minutes, and
`load_duration` was 5.11s of a 6.77s cold request. A wearable used a few times a
day is cold almost every time, so every warm number I've recorded is fiction as a
user-facing figure.

Context costs about 142 MiB per 1,000 tokens. 4000 is 4,567 MiB, 16000 is 6,273 MiB,
and that constant predicts the 16k figure to within 2 MiB. Prefill was 0.48s at both,
so this is a memory lever, not a speed one.

## Decision

All inference goes through one gateway, and the gateway is the only thing that talks
to Ollama. Not a preference, a consequence of the 11.45s reload. Two clients with
different settings would thrash the GPU.

Concurrency is a queue of depth one (`asyncio.Semaphore(1)` around the Ollama call).
Two vision requests will not fit in 7,841 MiB, so the second one waits instead of
dying on out-of-memory. Single-user system, collisions will be rare. The queue is
there so I have a real answer for the rare case.

Clients differ by prompt and generation settings, never by model or context. Free
per request: system prompt, temperature, `num_predict`, whether an image is attached.
Fixed globally, because changing them costs 11.45s: `num_ctx` and which model.

```
Modelfile:
  FROM qwen3-vl:4b-instruct
  PARAMETER num_ctx 16000
  PARAMETER temperature 0.3

Gateway supplies:
  keep_alive: -1              # model stays resident; kills the 5.11s cold start
  images downscaled to 1024px # server-side, do not trust clients
  num_predict: ~120 quick     # glasses, one-line answers
  num_predict: ~600 chat      # web and phone
```

Downscaling happens in the gateway. Clients can do it too for bandwidth, but I
can't trust them. One full-resolution image blows the context budget and
quadruples prefill.

`/readyz` probes Ollama. `/healthz` only reports the process. While Ollama was
stopped for a test, `openclaw-gateway` stayed active, zero restarts, logged nothing.
It would have found out on the next request. A service that reports healthy while
its only dependency is down is the failure mode that makes on-call miserable, and
I watched one do it.

## Open question: retire OpenClaw?

Unresolved. Decide this before treating the ADR as final.

ADR 0003 already demoted OpenClaw to actuator-only. The gateway would take that
remaining role.

Keeping it costs 1,706 MiB of VRAM forever, for something nothing currently uses.
OpenClaw sends 8,264 tokens of system prompt and tools on every request, which
forces `num_ctx 16000`. At 4000 you'd have about 2,000 tokens of input budget and
nothing would fit. ADR 0003 already hit that with `tools.profile: coding`, where
even "say hello" failed. A second model at 16000 next to a 4000 gateway model just
brings back the 11.45s thrash.

v1 answers questions. It does not take actions. Actions are a v2 feature, and when
they arrive the gateway should own them instead of paying an 8,264-token tax on
every request forever.

## Consequences

Warm vision is 1.77s and consistent. Four runs, fresh image each time so nothing
came from cache, landed between 1.76s and 1.79s. Against 13.47s cold at the start
of this work, 7.6x faster.

The consistency matters more than the speed. ADR 0003 had four identical runs at
2.2s, 2.5s, 4.6s and 6.5s. Spread is now 0.02s. Temperature 0.3 stops the rambling,
and `num_predict 120` fixes the token count. A latency you can predict is one you
can put in a spec. At 4.3s of spread that wasn't possible.

Cold is still 6.77s without `keep_alive: -1`. The trade is 6,273 MiB held on an
otherwise idle GPU. Worth it here, wouldn't be on a shared box.

`num_ctx` stays 16000 until OpenClaw is actually gone. Once it is, 4000 is safe: a
1024px image is 1,054 tokens, plus prompt plus ~400 of generation is about 1,500,
with 2.6x headroom. That also reverses an earlier call. The full local stack
(vision, whisper, embed, reranker, ~8,571 MiB) didn't fit. At 4000 it comes to
~6,865 MiB against 7,841 usable, with ~976 MiB spare. It fits.

Clients can't be tuned independently. If the web assistant later needs long
documents, the answer is retrieval (fetch the relevant chunks), not a bigger
window.

Two concurrent vision requests will never fit. The queue turns that into a wait
instead of a crash. Hard ceiling, not a tuning problem.

The gateway should emit these numbers as Prometheus histograms so this isn't a
one-off campaign: request latency, queue depth, and the `load_duration`,
`prompt_eval_count` and `eval_count` fields Ollama already returns. Record
`load_duration` separately or a p95 blends warm and cold and tells you nothing.

If I keep OpenClaw, it's now running against an instruct model with no reasoning
step. It won't crash (context is unchanged), but it's untested.

## Notes on method

Four hypotheses died, which is the reason to write this down. `num_predict` would
buy latency. Not while thinking is on, you just get an empty string. The GPU
exporter's 15s polling was holding the card at P0. Stopping it for 180s changed
nothing. The July 29 short boots were the kernel panic. They were clean
install-night reboots, and the panic predates this journal. A `--think` flag or
API field could disable thinking. Three mechanisms, all dead.

Clocks and power can't disprove "the query woke it up", because reading
`nvidia-smi` initializes NVML and wakes the GPU. Temperature is the valid
instrument: it has thermal inertia, and a query can't warm a heatsink. That's how
the exporter was exonerated.
