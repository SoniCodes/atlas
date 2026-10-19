# An automatic update broke the GPU and nobody noticed for 9 days

**Impact:** From Oct 9 to Oct 18, 2026, no new container on atlas could use the
GPU, and `nvidia-smi` on the host didn't work either. The containers that were
already running looked fine the whole time.
**Root cause:** unattended-upgrades updated the NVIDIA driver, but the part of
the driver loaded in the kernel only changes when you reboot, and atlas didn't.
**When:** Broke Oct 9 at 06:42 UTC. I found it Oct 16. Fixed Oct 18 at 02:48 UTC.

## What happened

I was building `patch.yml` and added a check at the end that runs `nvidia-smi`
inside a throwaway CUDA container. The first time I dry ran it, it failed:

    failed to fulfil mount request: open /run/nvidia-persistenced/socket: no such file or directory

The dry run hadn't upgraded or rebooted anything yet. So the GPU was already
broken before I touched it.

## What I found

`nvidia-persistenced` had been stopped since Oct 9 at 06:42. The journal showed
it got told to stop (signal 15) and nothing ever started it back up.

`nvidia-smi` on atlas said `Driver/library version mismatch`.

`/var/log/dpkg.log` showed the NVIDIA packages going from 580.173.02 to
580.178.04 at that same minute.

The driver module loaded in the kernel was still 580.173.02.

## Root cause

The NVIDIA driver is really two pieces. There are libraries on disk that
programs use, and there's a kernel module in memory that actually talks to the
card. The update swapped the libraries to 580.178. The module in memory stays
whatever it was when the machine booted, so it was still 580.173. Once those
two don't match, nothing new can use the GPU. The update also stopped
`nvidia-persistenced`, which Docker's NVIDIA runtime needs when it starts a GPU
container.

unattended-upgrades is allowed to touch the driver because Ubuntu ships the
`-server` driver from its own repos, and those count as trusted. But it never
reboots. So it can start a driver upgrade and it can't finish it.

The funny part is this only happened because I fixed things. Automatic updates
had been stuck for 48 days until I fixed the apt-daily hang on Oct 6 (incident
0002). Three days later they started working and this driver update came in.

## Why nobody noticed

`ollama` and `nvidia-exporter` were started before the update and just kept
running. Docker showed them as "Up 10 days". The `TargetDown` alert only checks
whether Prometheus can reach the exporter, and it could. The only thing that
would show the problem was starting a new GPU container, and nothing did that
until my patch check.

## Fix

A reboot fixes it because it loads the new module and the two pieces match
again. Before rebooting I ran `dkms status` to make sure the 580.178 module had
been built for the kernel atlas would come back up on. It had, for both
6.8.0-142 and 6.8.0-147.

I let `patch.yml` do it for real. It upgraded, rebooted into 6.8.0-147, and ran
the same GPU check, which passed this time. `nvidia-smi` showed the RTX 3070 on
580.178.04.

Then I made sure it can't happen again. Ansible now puts a file at
`/etc/apt/apt.conf.d/51-atlas-nvidia-blacklist` that tells unattended-upgrades to
skip anything starting with `nvidia-`, `libnvidia-` or
`xserver-xorg-video-nvidia-` (commit 66a0f90). Driver updates only happen
through `patch.yml` now, and that always reboots and checks the GPU after. I
checked with `apt-config dump` that apt actually picked up the rule.

I didn't use `apt-mark hold`. A hold would stop `patch.yml` from updating the
driver too, and that's not what I want.

## Lesson

Up isn't the same as working. Those containers looked fine for 9 days. The only
check that caught it was one that actually used the GPU like a new workload
would. This is the fourth time Atlas has had something look fine when it
wasn't, and the first time my own automation caught it before I tripped over it.

## Not done

- The driver doesn't get security fixes on its own anymore. That's the tradeoff.
  I actually have to run `patch.yml`.
- There's no alert for missing GPU metrics. `TargetDown` only knows the exporter
  is answering, not whether it can read the GPU.
- I don't know if Ollama was still using the GPU during those 9 days or if it
  quietly fell back to the CPU.
