# Runbook: patching

Security updates install on their own every night through unattended-upgrades.
Everything else goes through `ansible/patch.yml`. That includes Docker, the
NVIDIA container toolkit, anything from third-party repos, and the NVIDIA driver.

The driver is blocked from automatic updates on purpose (see incident 0003).
So if I stop running this playbook, the driver stops getting security fixes.
Don't let it slide.

## When

About once a week. Also whenever `apt list --upgradable` on atlas or
`dnf check-update` on macnode shows a lot waiting. Atlas will probably reboot,
so don't do it in the middle of something.

## Before

Make sure the repo is clean and pushed (`git status`).

Write down the kernels so you can tell if they changed:

    ssh atlas 'uname -r'
    ssh macnode 'uname -r'

Open http://macnode:9090/alerts. You can watch atlas drop and come back.

You can dry run it with `--check` first, but don't trust the reboot part of it.
The dry run doesn't actually upgrade anything, so it answers "does this need a
reboot?" based on the system before the upgrade. macnode said no reboot in the
dry run and then rebooted in the real one because a new kernel came in.

## Run

From `ansible/` on the Mac:

    ansible-playbook patch.yml -K

## What it does

It does one machine at a time (`serial: 1`). If atlas fails, macnode never gets
touched.

On each host it:

1. Upgrades everything. Atlas uses `apt` with `upgrade: dist` so new kernels
   actually come through. macnode uses `dnf`.
2. Checks if it needs a reboot. Ubuntu leaves a file at
   `/var/run/reboot-required`. Fedora has `dnf needs-restarting -r`, which
   exits 1 if it does.
3. Reboots if it needs to and waits up to 10 minutes for it to come back.
4. Checks that things still work. On atlas it runs `nvidia-smi` in a throwaway
   CUDA container and makes sure all six containers are running. On macnode it
   hits Prometheus and Grafana's health URLs and expects a 200.

## How long

Atlas is a few minutes plus a reboot. macnode takes longer since it's ARM and
Fedora pushes a lot of updates.

Heads up: when macnode reboots, nothing is watching atlas, because monitoring
lives on macnode. That's why atlas goes first and gets checked before macnode
starts.

## Check it yourself after

    ssh atlas 'uname -r; nvidia-smi --query-gpu=name,driver_version --format=csv'
    ssh atlas 'apt list --upgradable 2>/dev/null | grep -c upgradable; ls /var/run/reboot-required'
    ssh macnode 'uname -r'

Kernels should be new if there was a kernel update. The GPU should show up.
Upgradable should be 0 and the reboot-required file should be gone. Then check
http://macnode:9090/targets and make sure everything's up.

## If it breaks

Read the error first. It tells you which task and why.

Rerunning is fine. Stuff that's already upgraded just shows `ok`.

To do one host: `ansible-playbook patch.yml -K --limit macnode`

If a host doesn't come back in 10 minutes, wait a bit and try `ssh` again. If
it's still down, go look at the machine.

If a check fails but the service seems fine, `curl` it yourself before believing
the check. The Grafana check failed once because I wrote `status == 0` instead
of `200`. Grafana was fine the whole time.

If the GPU check fails, run the same `docker run ... nvidia-smi` on atlas and
read what it says. "Driver/library version mismatch" means the driver on disk
and the one loaded in memory don't match. A reboot fixes it, but check
`dkms status` first to make sure the module got built for the kernel it's going
to boot into.

Rolling back: Fedora has `dnf history undo last`. Ubuntu doesn't really have an
easy undo, which is part of why this goes one machine at a time.

## Log

- 2026-10-18: first real run. Atlas went to kernel 6.8.0-147 and NVIDIA
  580.178.04, and the GPU works again (this is what fixed incident 0003).
  macnode went to 7.1.13-402.asahi. The Grafana check failed on my typo, fixed in
  77eae27.
