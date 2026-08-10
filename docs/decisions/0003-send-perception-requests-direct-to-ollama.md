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

About 7x faster for the query I'll use most. Cost is two paths instead of one, plus
something has to decide which path a request takes.

The 33s isn't what the glasses will actually see even on the agent path. The phone app
sends the image with the request so it skips the first pass and the tool call entirely.
Haven't measured that yet, the CLI can't attach images.

Tried to speed up the direct path by turning off the model's thinking, since it writes
several paragraphs debating itself before it answers. Two attempts, neither worked:
-> --think=false only changes how Ollama renders it. The <think> tag just shows up as raw
text in the output instead. Model still generates the tokens.
-> /no_think in the prompt did nothing either. That's a Qwen3 text model thing, doesn't
seem to reach this one.
Looks like thinking is baked in for this model as Ollama serves it.

Also couldn't really measure any of it. Ran the same command four times and got 2.2s, 2.5s,
4.6s and 6.5s. Temperature is 1 so the model rambles a different amount every time, and
that swing is bigger than anything I was trying to measure. Single timings aren't
measurements. Need real percentiles before tuning this, which is why observability is next.

Lesson: watching the GPU showed me the two pass thing. Just timing it would have only told
me "slow".
