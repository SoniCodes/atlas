# apt-daily hung for 48 days and quietly blocked security updates

**Impact:** No automatic security updates on atlas from Aug 19 to Oct 6, 2026.
That included fixes for openssh-server, openssl, sudo and the kernel.
**Root cause:** An `apt-get update` run by `apt-daily.service` hung, and systemd
had no timeout on it, so it never ended.
**When:** Hung on Aug 19, 2026 at 01:47 UTC. Found on Oct 6, 2026, by accident.

## What happened

I was adding a task to my Ansible baseline to install `dnsutils` on atlas. The
first run failed with a 404 from Ubuntu's mirror. After I told Ansible to
refresh the package list first, the next run just hung.

A process listing on atlas showed why. There was an `apt-get update` that had
been running for 48 days, started by `apt-daily.service`, still holding apt's
lock. My Ansible task was waiting on that lock like everything else had been.

Nothing had errored. Nothing had alerted. I only found it because I happened to
need apt that night.

## What I ruled out

**A broken mirror.** The 404 looked like Ubuntu's side. It wasn't. Atlas's
package list was 7 weeks old and still pointed at a `dnsutils` version that had
since been replaced and deleted from the server.

**Someone stopping the timers.** `systemctl list-timers` showed no next run for
either apt timer, which looked like they had been turned off by hand. The
journal said otherwise: `apt-daily.service` started on Aug 19 and never logged
anything after that. Nothing was stopped. It was stuck in `activating (start)`
the whole time.

## Root cause

Two things lined up.

`apt-daily.service` is `Type=oneshot`, and systemd gives oneshot services no
start timeout unless you set one. So when the update hung, systemd just kept
waiting. Forever, as far as it was concerned.

The service that actually installs security updates, `apt-daily-upgrade`, runs
after `apt-daily`. With `apt-daily` never finishing, the upgrade job sat in the
queue behind it for 48 days.

I don't know what made the update hang in the first place. It used about 6
minutes of CPU over 48 days, so it wasn't doing work. It was waiting on
something, most likely a network connection that never answered.

## Fix

That night I ran `systemctl stop apt-daily.service`. The timer caught up on its
own, and unattended-upgrades installed about 100 security packages, including
kernel 6.8.0-142.

Before rebooting into the new kernel I checked that the NVIDIA module had been
built for it, since a missing module would have meant coming back with no GPU.
It was there. After the reboot, all 6 containers came back on their own and
`nvidia-smi` worked inside a container.

Then I fixed it in code. Ansible now installs a systemd drop-in that sets
`TimeoutStartSec=1h` on `apt-daily` (commit `1060f96`). A hang like this now
costs a day instead of weeks. I left `apt-daily-upgrade` without a timeout on
purpose. Killing it halfway through installing packages can leave apt broken,
which is worse than waiting.

The first version of that fix didn't work either. I named the file
`timeout.config`, and systemd only reads drop-ins ending in `.conf`. Ansible
reported success, `systemctl show` still said `infinity`. Renaming it fixed it.

## Lesson

A service being "active" doesn't mean it's working, and a tool saying
"success" doesn't mean the thing it set up is working. This is the third time
I've run into that on Atlas. Now I check the result, not the status.

## Not done

- I still don't know why the update hung.
- There's no alert for "the last successful update was more than 2 days ago."
  That alert would have caught this on Aug 21 instead of Oct 6.
- 76 non-security updates are still pending, including Docker and the NVIDIA
  container toolkit. They come from third-party repos that unattended-upgrades
  doesn't touch, so they need a deliberate patching playbook.
