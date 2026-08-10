# 0003: Send perception-only requests straight to Ollama, not through OpenClaw

**Status:** Accepted, with a correction to the reasoning (see below).
Largely absorbed by [0004](0004-single-gateway-in-front-of-ollama.md).

## Context

I got the whole chain working: an image goes into OpenClaw, reaches Ollama, and comes
back with a real description of my test photo. The backend works.

The problem is it took about 33 seconds. For the glasses, "what am I looking at" has
to answer in a few seconds or the feature is pointless.

## Decision

Instead of just timing the request again, I logged GPU utilization continuously
through it so I could see where the time went.

The GPU showed two separate bursts of work (about 6 seconds and about 10 seconds)
with roughly 18 seconds of 0% utilization in between. So only about 16 of the 33
seconds was actual compute. The rest was the GPU sitting idle.

That gap is the agent loop. On the first pass the model works out that it needs to
read a file and asks for a tool. OpenClaw then goes and reads the image and rebuilds
the prompt, none of which touches the GPU. The second pass is where it finally looks
at the image.

I ran the same thing straight at Ollama (same model, same image, same prompt, both
warm) and got 4.6 seconds.

So perception-only requests go direct to Ollama. Describing a scene, reading cards,
that kind of thing. I only use the OpenClaw agent loop when I actually need it to
do something, like add to a list or send a message.

## Consequences

Three measurements, same model, same image, same prompt. Direct to Ollama: 4.6s.
Agent loop with the image attached: 25.5s. Agent loop where the agent has to go
find the file itself: about 33s.

I expected attaching the image to close most of the gap, since it skips the first
pass and the tool call entirely. It didn't. Still 5.5x slower than direct. So the
tool round-trip was never the main cost.

Getting the agent path to work with an image at all took five config fixes. None
were guesses. I found all of them by reading the overflow numbers in
`openclaw logs`.

- `agents.defaults.model.primary` was missing the `:latest` tag. It didn't match
  the declared provider model, so OpenClaw invented a phantom text-only model with a
  200k context. The real vision model was never being used at all.
- `tools.profile` was `coding`, which loaded about 9,280 tokens of tool definitions
  against an 8,000 token input budget. Nothing fit. Not even "say hello".
- `BOOTSTRAP.md` was still in the workspace, costing ~264 tokens. The file itself
  says to delete it after first run.
- `compaction.reserveTokens` was holding back 8,000 of the model's 16,000 context
  for the reply, so half the window was gone before I sent anything.
- `tools.profile: minimal` strips the `image` tool, which is the one thing vision
  actually needs. I added it back with `tools.alsoAllow`. Note that `alsoAllow`
  merges on top of the profile. Plain `allow` would have replaced the whole thing.

All five are captured in `scripts/configure-openclaw.sh` so they're reproducible.

The model writes several paragraphs debating itself before answering, so I tried to
disable that. `--think=false` only changes how Ollama renders it. The `<think>` tag
shows up as raw text in the output instead, and the model still generates every one
of those tokens. `/no_think` in the prompt did nothing either. That's a Qwen3 text
model feature and it doesn't seem to reach this one. Thinking appears to be baked
in for this model as Ollama serves it.

I also couldn't measure any of this properly. I ran the same command four times and
got 2.2s, 2.5s, 4.6s and 6.5s. Temperature is 1, so the model rambles a different
amount every run. A single timing is not a measurement. I need real percentiles
before tuning anything, which is why observability comes next.

The broader lesson: watching the GPU showed me the two-pass structure, and reading
actual token counts in the logs showed me the five config bugs. Just timing it, or
guessing at fixes, would have told me nothing. Every hypothesis I had before looking
at real numbers turned out wrong.

## Correction (measured later)

The ~21s is not prompt overhead, and I was wrong to say it was.

I measured prompt evaluation on this box at 4,387 tokens/sec. So those 8,264 tokens
of system prompt cost about 1.9 seconds, not 21. Generation runs at ~119 tokens/sec,
so a 21-second gap is roughly 2,500 generated tokens: the model thinking, plus
multiple sequential turns of the agent loop.

Reading the input is fast. Writing the output is slow. I had those backwards.

So trimming `tools.profile` bought me about 2 seconds, not the 20 I thought. The
real lever is cutting thinking output and agent round-trips, not tool definitions.

The decision stands, the reasoning was wrong. That's the second time on this project
a hypothesis I formed before measuring turned out wrong by a wide margin.

One more thing worth recording: every timing in this ADR is warm. Ollama's default
keep-alive is 5 minutes, and `load_duration` measured 5.07s of a 7.82s request. For
a wearable used a few times a day, essentially every request is cold, so none of
these numbers describe what the glasses will actually experience.
