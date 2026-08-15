# 0003: Send perception-only requests straight to Ollama instead of through OpenClaw

## Context

Got the end to end test working, image goes from OpenClaw to Ollama and comes back with a
real description of my test photo. So the backend works. Problem is it took about 33
seconds, and for the glasses "what am I looking at" needs to come back in a few seconds or
it's useless.

## Decision

- Ran the agent test again with a continuous nvidia-smi log instead of just timing it, so
I could see where the time actually went.
-> GPU showed two separate bursts, about 6s and 10s, with roughly 18 seconds of 0% in
between. So only about 16s of the 33 was actual compute.
-> That gap is the agent loop. First pass the model figures out it needs to read a file and
asks for a tool. OpenClaw goes and reads the image and rebuilds the prompt, none of which
touches the GPU. Second pass is where it actually looks at the image.
- Ran the same thing straight at Ollama, same model, same image, same prompt, both warm.
Came back in 4.6 seconds.
- Decided perception only requests (describe a scene, read cards) go direct to Ollama. Only
use the OpenClaw agent loop when I actually need it to do something, like add to a list or
send a message.

## Consequences

Three measurements now, same model, same image, same prompt:
-> Direct to Ollama: 4.6s
-> Agent loop, image attached: 25.5s
-> Agent loop, agent has to go find the file itself: ~33s

I expected attaching the image to close most of the gap, since it skips the first pass and
the tool call. It didn't. Still 5.5x slower than direct. So the tool round trip was never
the main cost.

The real overhead is that the agent sends 8,264 tokens of system prompt and tool definitions
on every single request before it even looks at the image. That's a fixed ~21 second tax
that the direct path doesn't pay at all. Same decision as before but for a better reason
than what I originally wrote.

Getting the agent path to work with an image at all took five config fixes. None of them
were guesses, I found them by reading the overflow numbers in `openclaw logs`:
- agents.defaults.model.primary was missing the :latest tag, so it didn't match the declared
provider model and OpenClaw invented a phantom text-only 200k context model. The real vision
model was never being used.
- tools.profile was "coding", which loaded about 9,280 tokens of tool definitions against an
8,000 token input budget. Nothing fit, not even "say hello".
- deleted BOOTSTRAP.md out of the workspace, ~264 tokens, and the file itself says to delete
it after first run anyway.
- compaction.reserveTokens was holding back 8,000 of the model's 16,000 context for the
reply, so half the window was gone before anything was sent.
- tools.profile "minimal" strips the `image` tool, which is the one thing vision needs. Had
to add it back with tools.alsoAllow. Note alsoAllow merges on top of the profile, plain
`allow` would have replaced the whole thing.

All of those are captured in scripts/configure-openclaw.sh so they're reproducible.

Also tried to speed up the direct path by turning off the model's thinking, since it writes
several paragraphs debating itself before answering. Two attempts, neither worked:
-> --think=false only changes how Ollama renders it. The <think> tag just shows up as raw
text in the output instead. Model still generates the tokens.
-> /no_think in the prompt did nothing either. That's a Qwen3 text model thing, doesn't seem
to reach this one.
Looks like thinking is baked in for this model as Ollama serves it.

Couldn't really measure that properly either. Ran the same command four times and got 2.2s,
2.5s, 4.6s and 6.5s, because temperature is 1 and the model rambles a different amount every
time. Single timings aren't measurements. Need real percentiles before tuning this, which is
why observability is next.

Lesson: watching the GPU showed me the two pass thing, and reading the actual token counts in
the logs showed me the five config bugs. Just timing it or guessing at fixes would have told
me nothing. Every hypothesis I had before looking at real numbers was wrong.

## Correction (measured later)

The ~21s is NOT the prompt overhead. Measured prompt eval on this box at 4,387 tok/s, so
those 8,264 tokens cost about 1.9 seconds, not 21. Generation runs at ~119 tok/s, so 21s of
gap is roughly 2,500 GENERATED tokens — the model thinking, plus multiple sequential turns
in the agent loop.

So trimming tools.profile bought me about 2 seconds, not the 20 I thought. The real lever is
cutting thinking output and agent round-trips, not tool definitions.

Decision stands, reasoning was wrong. Second time on this project a hypothesis I formed
before measuring turned out wrong by a wide margin.

Also worth recording: every timing in this ADR is WARM. Ollama's default keep-alive is 5
minutes and load_duration measured 5.07s of a 7.82s request. For a wearable used sporadically
through the day essentially every request is cold, so none of these numbers describe what the
glasses will actually experience. Measuring that properly is what the observability phase is
for.
