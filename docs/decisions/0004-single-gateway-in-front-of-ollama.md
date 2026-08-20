# 0004: Make a single gateway the only client of Ollama

## Context

The assistant is going to have three clients: a web UI, a phone app, and the Meta Ray-Ban
glasses. All five prerequisites for the glasses path are now confirmed (hardware owned,
supported country, iOS 17.2+, Apple Developer account), so this is a real constraint and not a
hypothetical one.

The hardware is one RTX 3070 with **7,841 MiB usable** — 8,192 total minus 352 MiB that the
driver reserves permanently and never gives back. One GPU means one loaded model, realistically
one request at a time. Every client has to share it.

I spent a few days measuring instead of guessing, because ADR 0003 already burned me twice on
hypotheses formed before looking at numbers. What the measurements showed:

**Switching models or context size costs 11.45 seconds.** Ollama tears down the old runner
before building the new one, so you pay both ways in a single request. Measured three separate
times, days apart: 11.45s, 11.49s, 11.49s. Cold load with matching options is 5.08s; warm with
matching options is 0.14s.

That single fact kills the obvious design. I wanted glasses to run a small context for speed
and the web assistant to run a large one for documents. Impossible — alternating between them
would cost 11.45s each way. **One process has to own the settings, and every client lives with
them.**

**Images dominate the cost, and resolution is the lever.** A full-resolution 4032x3024 phone
photo costs 4,033 context tokens and 2.72s of prefill. Downscaled to 1024px it costs 1,054
tokens and 0.48s. At 640px it is *also* 1,054 tokens — the model floors out, so 1024 is the
sweet spot and going smaller buys nothing. Answer quality held on the test image.

Image prefill runs at ~1,485 tok/s against the 4,387 tok/s ADR 0003 measured for text, so image
tokens cost roughly 3x more each.

**Thinking was over half the generation.** `qwen3-vl:4b` has thinking baked in. All three ways
to disable it are dead: the `--think=false` CLI flag and `/no_think` in the prompt (ruled out in
ADR 0003), and the API field `"think": false` on Ollama 0.32.5 (ruled out now, identical
result). At `num_predict=120` the thinking model produced **120 tokens and zero characters of
answer** — it spent the entire budget reasoning and never reached a reply.

`qwen3-vl:4b-instruct` exists, same Q4_K_M quantization, same size. Side by side on the same
image:

| | thinking | instruct |
|---|---|---|
| num_predict=120 | **empty answer**, 542 chars of thinking | **595 chars of answer**, 0 thinking |
| natural stop | 509 tok / 4.54s -> 1029 chars | 283 tok / 2.51s -> 1382 chars |
| warm total | 4.73s | 2.70s |
| VRAM | 4,683 MiB | 4,683 MiB, identical |

More answer from half the tokens, at the same memory cost.

**Cold start is half of a cold request.** Ollama's default keep-alive is 5 minutes, and
`load_duration` measured 5.11s of a 6.77s cold request. A wearable used sporadically through the
day is cold essentially every time, so every timing recorded warm is fiction as a user-facing
number.

**KV cache is priced at ~142 MiB per 1,000 tokens of context.** num_ctx 4000 costs 4,567 MiB,
num_ctx 16000 costs 6,273 MiB. That constant predicts the 16k figure to within 2 MiB. Context
size barely affects latency — prefill was 0.48s at both — so it is purely a VRAM lever.

## Decision

**All inference goes through one gateway. The gateway is the only thing that talks to Ollama.**

Not a preference — a consequence of the 11.45s reload. Two independent clients with different
options would thrash the GPU between them. One process owns the connection, owns the settings,
and serializes access.

**Concurrency is a queue of depth one.** An `asyncio.Semaphore(1)` around the Ollama call. Two
concurrent vision requests will not fit in 7,841 MiB, so the honest design is to make the second
one wait and say so, rather than let it fail on an out-of-memory error. This is a single-user
system; collisions will be rare. The queue exists for the rare collision and for having a real
answer to "what happens under concurrency."

**Clients differ by prompt and generation parameters, never by model or context.** The split
falls exactly along what forces a reload:

Free to vary per request:
- system prompt
- `temperature`
- `num_predict`
- whether an image is attached

Forces an 11.45s reload, therefore fixed globally:
- `num_ctx`
- which model

So a glasses request and a web request hit the same loaded model and differ only in the prompt
wrapped around them and how many tokens they are allowed to emit.

**The measured configuration:**

```
Modelfile:
  FROM qwen3-vl:4b-instruct
  PARAMETER num_ctx 16000
  PARAMETER temperature 0.3

Gateway supplies:
  keep_alive: -1              # model stays resident; kills the 5.11s cold start
  images downscaled to 1024px # server-side, do not trust clients
  num_predict: ~120 quick     # glasses: one-line answers
  num_predict: ~600 chat      # web/phone
```

**Image downscaling happens in the gateway, not the client.** Clients may downscale too, for
bandwidth, but the gateway must not trust them to. A full-resolution image would blow the
context budget and quadruple prefill.

**`/readyz` probes Ollama; `/healthz` only reports the process.** While Ollama was stopped for a
test, `openclaw-gateway` stayed `active` with zero restarts and logged nothing at all. It
survived, but there is no evidence it *noticed* — it would have discovered the failure only on
the next request. A service reporting healthy while its only dependency is down is the exact
failure mode that makes on-call miserable, and I watched one do it. Readiness has to be an
active check.

**OpenClaw is retired.**

> **DECISION PENDING — confirm or flip this section before committing.**

ADR 0003 already demoted OpenClaw to actuator-only: perception requests go direct to Ollama
because the agent loop cost 25.5s against 4.6s. The gateway absorbs that remaining role.

The concrete cost of keeping it: OpenClaw sends **8,264 tokens** of system prompt and tool
definitions on every request. That forces `num_ctx 16000`, because at 4000 there are only ~2,000
tokens of input budget and nothing fits — ADR 0003 already recorded exactly this failure mode
with `tools.profile: coding`, where "nothing fit, not even 'say hello'." Keeping OpenClaw
therefore costs **1,706 MiB of VRAM**, permanently, for a capability nothing currently uses.

The alternative — a second model at num_ctx 16000 alongside a 4000 gateway model — reintroduces
the 11.45s thrash this ADR exists to prevent.

v1 answers questions. It does not take actions. Actions are a real v2 feature, and when they
arrive the gateway should own them properly rather than paying an 8,264-token tax on every
request forever.

## Consequences

**Warm vision requests are 1.77s, and effectively deterministic.** Four runs, a fresh image each
time so nothing came from prefill cache:

```
1000px 1.79s | 960px 1.78s | 900px 1.77s | 880px 1.76s
min 1.76s   median 1.77s   max 1.79s   spread 0.02s
```

Against the 13.47s cold request at the start of this work, that is **7.6x faster**.

**The variance result matters more than the speed.** ADR 0003 recorded four identical runs at
2.2s, 2.5s, 4.6s and 6.5s — a 4.3 second spread — and concluded that single timings are not
measurements. The spread is now **0.02 seconds**. Two causes: `temperature 0.3` stops the model
rambling a different amount each time, and `num_predict 120` fixes the token count by
construction. A latency you can predict is a latency you can put in a spec and alert on. At 4.3s
of spread none of that was possible.

**Cold is still 6.77s** and that is what a user hits without `keep_alive: -1`. The trade is
6,273 MiB held permanently on a GPU that is otherwise idle. Worth it here; would not be on a
shared box.

**num_ctx stays at 16000 until OpenClaw is actually gone**, so the 1,706 MiB is still spent.
Once retired, dropping to 4000 is safe: a 1024px image is 1,054 tokens, plus prompt plus ~400
generation is roughly 1,500, leaving 2.6x headroom. That also reverses the earlier conclusion
that the full local stack (vision + whisper + embed + reranker, ~8,571 MiB) could not fit — at
num_ctx 4000 it comes to ~6,865 MiB against 7,841 usable, with ~976 MiB spare.

**Clients cannot be tuned independently, and that is by design.** If the web assistant later
needs long documents, the answer is retrieval — fetch the three relevant chunks — not a bigger
context window. Good retrieval with a modest context beats a huge context with none, and it is
cheaper on both VRAM and prefill.

**Two concurrent vision requests will never fit.** The queue makes that a wait instead of a
crash, but it is a hard ceiling, not a tuning problem.

**The gateway becomes the measurement apparatus.** Every one of these numbers came from throwaway
scripts. The gateway should emit them as Prometheus histograms — request latency, queue depth,
and the `load_duration` / `prompt_eval_count` / `eval_count` fields Ollama already returns — so
this becomes continuous instead of a one-off campaign. Record `load_duration` separately or a
p95 blends warm and cold requests and tells you nothing.

**OpenClaw's behaviour changed the moment the model was rebuilt.** `qwen3-vl-atlas` is now
instruct-based, so if OpenClaw is kept after all, its tool selection is running without the
reasoning step it used to have. It will not crash — context is unchanged — but it is untested.

## Notes on method

Four hypotheses died during this work, which is the actual reason to write any of it down:

- `num_predict` would buy latency. It does not while thinking is on — capping output just
  returns an empty string.
- The GPU exporter's 15s polling was keeping the card at P0. Stopping it for 180s changed
  nothing.
- The July 29 short boots were the kernel panic. They were clean install-night reboots; every
  recorded boot ended gracefully and the panic predates this journal entirely.
- A `--think` flag or API field could disable thinking. Three mechanisms, all dead.

Also worth keeping: **clocks and power cannot disprove "the query woke it up," because reading
nvidia-smi initializes NVML and wakes the GPU.** Temperature is the valid instrument — it has
thermal inertia and a query cannot warm a heatsink. That is how the exporter was exonerated.
