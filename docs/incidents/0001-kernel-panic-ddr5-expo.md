# Kernel panic on every boot — DDR5 overclock, not the GPU driver

**Impact:** Atlas would not complete a boot. Unusable until resolved.
**Root cause:** EXPO memory overclock left enabled in BIOS from the machine's
previous life as a gaming PC.
**When:** During initial OS setup, before this repo existed. No exact date — the
incident predates the git history, and uptime is not a proxy for it either,
since I was power-cycling the box constantly in that period.

## What happened

Fresh Ubuntu Server 24.04 install on a repurposed gaming PC (Ryzen 7 7700X,
32GB DDR5, RTX 3070). Kernel panic on boot — not intermittently, every time,
from cold.

That mattered as a signal. An intermittent panic suggests something marginal.
One that reproduces on every boot is deterministic, and deterministic means it
can be isolated by changing one variable at a time.

## What I ruled out

**The NVIDIA driver.** My first assumption, and the usual suspect on a fresh
Linux install with a discrete GPU. I remember working through Ubuntu's
safe-graphics boot option as part of this. I cannot reconstruct the exact test
that cleared it — I was not keeping notes yet, which is part of why this
document exists at all.

**A bad install.** Reburned the ISO to the USB and installed again from
scratch. Same panic, same point in boot.

Both guesses were about things I had *recently done*. That framing was the
problem.

## Root cause

Once "what did I change this week" was exhausted, the better question was "what
about this machine is not stock?" The answer was in BIOS: **EXPO** was enabled,
the DDR5 equivalent of XMP, running the memory above its JEDEC-standard speed.
It had been on since the box was built as a gaming PC and had never caused a
visible problem under Windows.

Memory that is almost stable can run a Windows desktop for years and still
corrupt the kernel during early boot, where there is no tolerance for a bad read.

## Fix

Disabled EXPO; memory back to its JEDEC default of 4800 MT/s. Booted clean on
the next attempt and has been stable since. Cost is some memory bandwidth,
which is irrelevant for a container host.

## Lesson

I was scoping "what changed" too narrowly. Checking recent changes first is
correct practice — it just was not sufficient, because the cause predated
everything I was considering. The overclock had been on since before Linux ever
touched the box, so it never appeared on a list of things I had done that week.

Once recent changes are exhausted, the question becomes **"what about this
system is not default?"** — regardless of when it became that way.

Related: "it worked before" is not evidence of stability. Different workload,
different tolerance for a marginal read.

## Not done

The memory has never been validated under sustained load at JEDEC speed. A long
memtest86+ run would turn "stable so far" into "tested."

---

*Written retrospectively. The diagnosis is accurate; some procedural detail is
reconstructed from memory rather than from notes taken at the time.*
