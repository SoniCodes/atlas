# Runbook — Monitoring stack on macnode

**Last verified:** 2026-08-15
**Owner:** vraj

Prometheus and Grafana run on **macnode**, scraping both hosts over Tailscale. This runbook
covers operating the stack day to day and rebuilding it from bare metal.

---

## Architecture

```
atlas   node_exporter        :9100  (container, stacks/monitoring/docker-compose.yml)
atlas   nvidia_gpu_exporter  :9835  (container, same compose file)
macnode node_exporter        :9100  (distro package, NOT a container)
                   │
                   ▼  scrape every 15s over Tailscale
macnode Prometheus  :9090  (Quadlet)   90d / 20GB retention
                   │
                   ▼  PromQL on demand
macnode Grafana     :3000  (Quadlet)
```

**Why monitoring lives on macnode, not atlas:** atlas is the machine that gets powered off at
night, runs the GPU workloads, and has already produced one kernel panic. It should be the
*observed*, not the observer. A monitoring stack that dies with the thing it monitors tells
you nothing about why.

**Grafana holds no metrics.** Its volume contains dashboards, users, and settings only. Losing
it costs you zero history. Losing Prometheus's volume loses the history permanently.

### Host facts

| | atlas | macnode |
|---|---|---|
| OS | Ubuntu 24.04 | Fedora Asahi 44 |
| Arch | x86_64 | aarch64, 16K pages |
| Containers | Docker | **rootless podman** |
| Tailscale name | `atlas` | `macnode` |
| LAN IP | 10.0.0.49 | 10.0.0.41 |

---

## Files (all in `~/atlas`, both hosts + GitHub)

```
hosts/macnode/systemd/prometheus.container          Quadlet unit
hosts/macnode/systemd/prom-data.volume              Quadlet named volume
hosts/macnode/systemd/grafana.container             Quadlet unit
hosts/macnode/systemd/grafana-data.volume           Quadlet named volume
hosts/macnode/prometheus/prometheus.yml             Prometheus's OWN config (what to scrape)
hosts/macnode/grafana/provisioning/
    datasources/prometheus.yml                      Grafana's description OF Prometheus
    dashboards/dashboards.yml                       dashboard provider config
    dashboards/atlas-gpu.json                       the dashboard itself
    alerting/.gitkeep  plugins/.gitkeep             silence startup errors
stacks/monitoring/docker-compose.yml                atlas exporters
```

> **Two files are named `prometheus.yml`.** One is Prometheus configuring itself; the other is
> Grafana's *description of* Prometheus. Only the path distinguishes them. Check which you're
> editing before you wonder why nothing changed.

---

## THE ONE THING NOT IN GIT

**Grafana's admin password lives in a podman secret, not the repo.** A fresh clone will not
produce a working login. Recreate it by hand:

```bash
read -rsp 'Grafana admin password: ' GF_PW; echo
printf '%s' "$GF_PW" | podman secret create grafana-admin-password -
unset GF_PW
podman secret ls
```

`printf '%s'` (not `echo`) — a trailing newline becomes part of the password.
`read -rsp` keeps it out of `~/.bash_history` and out of `ps`.

---

## Rebuild from bare metal

Assumes Fedora Asahi installed, user `vraj`, Tailscale joined.

**1. Prerequisites.** Podman ships with Fedora — no install needed. Add node_exporter:

```bash
sudo dnf install -y node-exporter
sudo systemctl enable --now prometheus-node-exporter.service
```

The unit name is `prometheus-node-exporter.service`, not `node-exporter`. It runs as its own
`prometheus` user.

**2. Linger** — user services must survive logout and start at boot:

```bash
loginctl enable-linger vraj
loginctl show-user vraj --property=Linger    # must print Linger=yes
```

**3. Clone:**

```bash
git clone git@github.com:SoniCodes/atlas.git ~/atlas
```

**4. Recreate the podman secret** — see the section above. Do this before starting Grafana.

**5. Pull images first**, before starting any unit:

```bash
podman pull docker.io/prom/prometheus:v3.13.2
podman pull docker.io/grafana/grafana:13.1.3
```

Quadlet units inherit systemd's 90s `TimeoutStartSec`. A cold pull can exceed it, and systemd
kills the unit mid-pull and marks it `failed` — which looks like a config error and isn't.

**6. Deploy the units:**

```bash
cp ~/atlas/hosts/macnode/systemd/*.container ~/atlas/hosts/macnode/systemd/*.volume \
   ~/.config/containers/systemd/
systemctl --user daemon-reload
systemctl --user start prometheus grafana
```

**7. Firewall** — bind the Tailscale interface to the trusted zone:

```bash
sudo firewall-cmd --permanent --zone=trusted --add-interface=tailscale0
sudo firewall-cmd --reload
```

**8. Verify** — see the Verification section.

---

## Day-to-day operations

### Which reload for which file

| Changed | Command | Why |
|---|---|---|
| `prometheus/prometheus.yml` | `podman kill -s HUP prometheus` | app re-reads config; container keeps running, no data gap |
| `grafana/provisioning/**` | `systemctl --user restart grafana` | Grafana reads provisioning only at startup |
| any `.container` / `.volume` | `cp` to `~/.config/containers/systemd/`, `systemctl --user daemon-reload`, then `restart` | the *unit* must be regenerated |

**The `cp` is the deploy.** The repo is the source of truth, but systemd only reads
`~/.config/containers/systemd/`. Editing the repo copy alone changes nothing.

### Validate before applying, every time

```bash
podman run --rm --entrypoint promtool -v ~/atlas/hosts/macnode/prometheus:/c:ro,Z \
  docker.io/prom/prometheus:v3.13.2 check config /c/prometheus.yml
python3 -m json.tool ~/atlas/hosts/macnode/grafana/provisioning/dashboards/atlas-gpu.json >/dev/null
```

Bad dashboard JSON fails **silently** — the dashboard simply never appears.

### Dashboards are read-only in the UI

`allowUiUpdates: false` is deliberate: git is the source of truth and it's enforced, not just
intended. The edit loop is:

> experiment in the UI → **Export → JSON** → paste into the repo file → commit → `restart`

### Common commands

```bash
systemctl --user status prometheus grafana --no-pager
podman logs grafana 2>&1 | grep -iE "level=error"
podman ps
curl -s http://localhost:9090/api/v1/targets | python3 -m json.tool | grep -E '"health"|scrapeUrl'
```

---

## Verification

**Targets** — all three must be `up`:

```bash
curl -s http://localhost:9090/api/v1/targets \
  | python3 -c 'import sys,json;[print(t["labels"]["job"],t["scrapeUrl"],t["health"]) for t in json.load(sys.stdin)["data"]["activeTargets"]]'
```

**Grafana health:**

```bash
curl -s http://localhost:3000/api/health     # {"database":"ok","version":"13.1.3",...}
```

**End-to-end** — the only test that proves the whole chain (secret → login → provisioned
datasource → container networking → Prometheus → exporter on atlas). In Grafana **Explore**:

```
nvidia_smi_memory_used_bytes
```

**Firewall — run BOTH tests.** From a Mac on the home LAN:

```bash
curl -s --max-time 8 http://macnode:3000/api/health      # over Tailscale: must SUCCEED
nc -z -w3 10.0.0.41 22                                   # LAN path must be LIVE
curl -s --max-time 5 http://10.0.0.41:3000/api/health    # over LAN: must FAIL (exit 7)
```

The middle line is not optional. Without proving the LAN path is alive, a failed `curl` to
`10.0.0.41:3000` could just mean you're off the network — and you'd have proved nothing. A rule
tested only positively is not a tested rule.

**Reboot test:** the only conclusive proof of permanence. NetworkManager can reassign interface
zones at bring-up, which a `--reload` does not exercise. After any macnode reboot, re-run the
firewall tests and confirm both units came back:

```bash
systemctl --user is-active prometheus grafana
```

---

## Gotchas — hard-won, do not rediscover

**Quadlet units cannot be `systemctl --user enable`d.** They're generated into
`/run/user/1000/systemd/generator/`, which is tmpfs — rebuilt on every `daemon-reload`, wiped
on reboot. There is no stable file to symlink. Boot startup comes from `[Install]
WantedBy=default.target` *inside* the `.container` file, which the generator re-materialises
into `default.target.wants/` each time.

**`localhost` inside a container is the container**, not the host. To reach a service on the
podman host, use `host.containers.internal:PORT`. Both `prometheus.yml` (scraping macnode's
node_exporter) and Grafana's datasource URL depend on this.

**SELinux is Enforcing.** Bind mounts need `:Z` or you get a permission denial that looks like
a file-mode problem. Never `:Z` a top-level directory such as `/home`, `/etc`, or `/usr` — only
specific subdirectories.

**Use named podman volumes for anything the container writes.** Rootless UID mapping means
container UID *N* lands on host UID 524288+*N*−1 — Grafana's UID 472 is host UID 524759. A host
directory you `chown vraj` (UID 1000) is *not* writable by the container. Named volumes inherit
correct ownership from the image and sidestep it entirely.

**Quadlet prefixes volume names with `systemd-`.** `prom-data.volume` creates a volume called
`systemd-prom-data`. Expect the mismatch in `podman volume ls`.

**`cat -A`** to spot trailing spaces after `\` line continuations — invisible and fatal.

**Grafana logs `level=error` for missing provisioning subdirectories.** It expects
`datasources/`, `dashboards/`, `alerting/`, and `plugins/`. All four exist (two hold only
`.gitkeep`) specifically so startup logs stay clean — red lines you've trained yourself to
ignore are worse than no logs.

---

## Decisions worth defending

**Firewall scoped by interface, not source CIDR.** `--zone=trusted --add-interface=tailscale0`
rather than allowing `100.64.0.0/10`. A LAN attacker can forge a `100.64.x.x` source address,
but packets only *arrive on* `tailscale0` after WireGuard has authenticated them. The interface
is the authentication.

*Tradeoff, accepted knowingly:* `trusted` accepts all traffic on that interface, so every port
on macnode is reachable from the tailnet. Acceptable for a single-user tailnet where Tailscale
ACLs are the real access control. Revisit if the tailnet ever gains another person.

**Admin password as a podman secret, not an environment variable.** An env var in a committed
file is a credential in git forever; an env var set at runtime is still visible in
`podman inspect`. The secret mounts at `/run/secrets/` and Grafana reads it via its own
`GF_SECURITY_ADMIN_PASSWORD__FILE` convention. Cost: one manual step on rebuild, documented
above.

**The dashboard's ceiling is computed, not hardcoded.**
`nvidia_smi_memory_total_bytes - nvidia_smi_memory_reserved_bytes`, not a literal 7841 MiB. If
a driver update changes the reservation, the line moves on its own instead of quietly lying.

**Usable VRAM on atlas is 7,841 MiB, not 8,192.** 352 MiB is permanently driver-reserved and
never appears in `nvidia_smi_memory_used_bytes`. Any capacity plan using 8,192 is over-budget
by 351 MiB before it starts. Verified against `nvidia-smi` 2026-08-15.

---

## Known open items

- Alerts not yet built. Planned: `ServiceDownWhileHostUp`, `DiskWillFillIn7Days`
  (predict_linear), `GPUVRAMNearLimit` at ~7,200 MiB (92% of *usable* — 7,600 would fire at 97%,
  too late to react).
- No backups of Prometheus's volume. It holds the only copy of all history.
- atlas idles at **57W** with 0 MiB VRAM used and 4% utilization; an RTX 3070 should idle nearer
  15–20W. Unexplained. ~40W constant is roughly 350 kWh/year.
