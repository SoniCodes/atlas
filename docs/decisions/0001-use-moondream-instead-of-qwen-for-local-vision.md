# 0001: Use moondream instead of qwen2.5vl for local vision

**Status:** Superseded by [0002](0002-switch-to-qwen3-vl-for-local-vision.md)

## Context

Atlas has one GPU: an RTX 3070 with 8GB of VRAM. VRAM is the GPU's own memory, and
it's separate from the 32GB of system RAM. A model has to fit in VRAM to run on the
GPU at all. There's no second card and no bigger one, so 8GB is a hard ceiling.

I wanted a vision model (one that can look at an image and describe it) running
locally through Ollama. Two reasons: prove that GPU passthrough into a container
actually works end to end, and have something ready for the glasses project later.

## Decision

I started with `qwen2.5vl:7b`. The download worked fine, 6GB on disk.

Then the first real request failed with a CUDA out-of-memory error at around
7,000MiB used. I retried and got a different error: it needed 4,110 tokens of
context but only had 4,096 available.

Two different failures, one root cause. A model's size on disk is not its size
when running. Loading the weights is only part of it. The model also needs room
for the image, the prompt, and the answer it's building. 6GB of weights does not
fit comfortably in 8GB of VRAM once you add all that.

So I switched to `moondream`, which is 1.7GB. It downloaded, ran on a real photo,
and described it correctly with no errors.

## Consequences

I confirmed it was genuinely using the GPU rather than quietly falling back to the
CPU, by logging GPU utilization continuously during the request instead of checking
once. One sample hit 94% and then dropped back to idle. Memory usage stayed well
under 8GB with real room to spare.

The trade-off is precision. moondream describes things vaguely. On my test image
it said "at least ten individuals" instead of giving a count. That's fine for a
general "what am I looking at" question. It is not good enough for anything that
needs exact recognition. Reading specific card values for the blackjack-advisor
idea, for example, would need a different and narrower approach than this model.
