# Runbook: Monitoring on macnode

Last checked: 2026-08-15

Prometheus and Grafana run on macnode and scrape both hosts over Tailscale.
Atlas is the thing being watched, not the watcher. It gets powered off at night
and has already had one kernel panic. A monitoring stack that dies with the
machine it monitors tells you nothing.

Grafana holds dashboards and settings only. Losing its volume costs you no
history. Losing Prometheus's volume loses the history for good.

## What runs where

- atlas: `node_exporter` on :9100 and `nvidia_gpu_exporter` on :9835
  (Docker, `stacks/monitoring/docker-compose.yml`)
- macnode: `node_exporter` on :9100 (distro package, not a container)
- macnode: Prometheus on :9090 and Grafana on :3000 (rootless podman Quadlets)

Scrapes go over Tailscale every 15s. Reach them as `atlas` and `macnode`, not by
LAN IP. Atlas's wired address moves when ethernet is down.

## Files in git

```
hosts/macnode/systemd/prometheus.container
hosts/macnode/systemd/prom-data.volume
hosts/macnode/systemd/grafana.container
hosts/macnode/systemd/grafana-data.volume
hosts/macnode/prometheus/prometheus.yml
hosts/macnode/grafana/provisioning/datasources/prometheus.yml
hosts/macnode/grafana/provisioning/dashboards/dashboards.yml
hosts/macnode/grafana/provisioning/dashboards/atlas-gpu.json
stacks/monitoring/docker-compose.yml
```

Two different files are both named `prometheus.yml`. One is Prometheus
configuring itself. The other is Grafana's description of Prometheus. Check the
path before you edit.

## The password is not in git

Grafana's admin password is a podman secret. A fresh clone will not log you in.
Recreate it before starting Grafana:

```bash
read -rsp 'Grafana admin password: ' GF_PW; echo
printf '%s' "$GF_PW" | podman secret create grafana-admin-password -
unset GF_PW
podman secret ls
```

Use `printf '%s'`, not `echo`. A trailing newline becomes part of the password.
`read -rsp` keeps it out of `~/.bash_history` and out of `ps`.

## Rebuild from scratch

Assumes Fedora Asahi, user `vraj`, Tailscale already joined. Podman ships with
Fedora, so no install needed.

1. Install node_exporter. The unit name is `prometheus-node-exporter.service`,
   not `node-exporter`.

```bash
sudo dnf install -y node-exporter
sudo systemctl enable --now prometheus-node-exporter.service
```

2. Linger, so user services survive logout and start at boot:

```bash
loginctl enable-linger vraj
loginctl show-user vraj --property=Linger    # must print Linger=yes
```

3. Clone and recreate the secret (section above).

```bash
git clone git@github.com:SoniCodes/atlas.git ~/atlas
```

4. Pull images before starting any unit. Quadlet inherits systemd's 90s
   `TimeoutStartSec`. A cold pull can overshoot it, systemd kills the unit
   mid-pull, and it looks like a config error when it isn't.

```bash
podman pull docker.io/prom/prometheus:v3.13.2
podman pull docker.io/grafana/grafana:13.1.3
```

5. Deploy the units. The `cp` is the deploy. systemd only reads
   `~/.config/containers/systemd/`. Editing the repo copy alone changes nothing.

```bash
cp ~/atlas/hosts/macnode/systemd/*.container \
   ~/atlas/hosts/macnode/systemd/*.volume \
   ~/.config/containers/systemd/
systemctl --user daemon-reload
systemctl --user start prometheus grafana
```

6. Put Tailscale in the trusted zone. Scope by interface, not by the
   `100.64.0.0/10` CIDR. A LAN attacker can forge that source address, but
   packets only arrive on `tailscale0` after WireGuard has authenticated them.
   Tradeoff: every port on macnode is reachable from the tailnet. Fine for a
   single-user tailnet. Revisit if anyone else joins.

```bash
sudo firewall-cmd --permanent --zone=trusted --add-interface=tailscale0
sudo firewall-cmd --reload
```

7. Verify. See the next section.

## Day to day

Which reload for which change:

- `hosts/macnode/prometheus/prometheus.yml`:
  `podman kill -s HUP prometheus`
  (re-reads config, no data gap)
- `hosts/macnode/grafana/provisioning/**`:
  `systemctl --user restart grafana`
  (Grafana only reads provisioning at startup)
- any `.container` / `.volume`:
  `cp` into `~/.config/containers/systemd/`, then
  `systemctl --user daemon-reload` and `restart`

Validate before applying:

```bash
podman run --rm --entrypoint promtool \
  -v ~/atlas/hosts/macnode/prometheus:/c:ro,Z \
  docker.io/prom/prometheus:v3.13.2 check config /c/prometheus.yml
python3 -m json.tool \
  ~/atlas/hosts/macnode/grafana/provisioning/dashboards/atlas-gpu.json \
  >/dev/null
```

Bad dashboard JSON fails silently. The dashboard just never appears.

Dashboards are read-only in the UI on purpose (`allowUiUpdates: false`). Edit
loop: experiment in the UI, Export, JSON, paste into the repo file, commit,
restart Grafana.

```bash
systemctl --user status prometheus grafana --no-pager
podman logs grafana 2>&1 | grep -iE "level=error"
podman ps
curl -s http://localhost:9090/api/v1/targets \
  | python3 -m json.tool | grep -E '"health"|scrapeUrl'
```

## Verification

All three targets must be `up`:

```bash
curl -s http://localhost:9090/api/v1/targets \
  | python3 -c 'import sys,json
for t in json.load(sys.stdin)["data"]["activeTargets"]:
    print(t["labels"]["job"], t["scrapeUrl"], t["health"])'
```

Grafana health:

```bash
curl -s http://localhost:3000/api/health
```

End to end. This is the only test that proves secret, login, datasource,
Prometheus, and the exporter on atlas. In Grafana Explore:

```
nvidia_smi_memory_used_bytes
```

Firewall. Run both directions. From a Mac on the home LAN:

```bash
curl -s --max-time 8 http://macnode:3000/api/health     # Tailscale: must work
nc -z -w3 10.0.0.41 22                                  # LAN path must be alive
curl -s --max-time 5 http://10.0.0.41:3000/api/health   # LAN: must fail
```

The middle line matters. Without it, a failed LAN curl might just mean you're
off the network, and you've proved nothing.

After any macnode reboot, re-run the firewall tests and check both units came
back. `firewall-cmd --reload` does not prove permanence. NetworkManager can
reassign interface zones at bring-up.

```bash
systemctl --user is-active prometheus grafana
```

## Gotchas

Quadlet units cannot be `systemctl --user enable`d. They're generated into
`/run/user/1000/systemd/generator/` (tmpfs), rebuilt on every `daemon-reload`,
wiped on reboot. Boot startup comes from `WantedBy=default.target` inside the
`.container` file.

`localhost` inside a container is the container, not the host. Use
`host.containers.internal:PORT` to reach the host. Both `prometheus.yml`
(scraping macnode's node_exporter) and Grafana's datasource URL depend on this.

SELinux is Enforcing. Bind mounts need `:Z`, or you get a permission denial that
looks like a file-mode problem. Never `:Z` a top-level directory like `/home`
or `/etc`. Only specific subdirectories.

Use named podman volumes for anything the container writes. Rootless UID mapping
means container UID 472 (Grafana) lands on host UID 524759. A directory you
`chown vraj` is not writable by the container. Named volumes inherit ownership
from the image and dodge this.

Quadlet prefixes volume names with `systemd-`. `prom-data.volume` shows up as
`systemd-prom-data` in `podman volume ls`.

`cat -A` to spot trailing spaces after `\` line continuations. Invisible and
fatal.

Grafana logs `level=error` for missing provisioning subdirectories. That's why
`alerting/` and `plugins/` exist with only a `.gitkeep`. Red lines you've trained
yourself to ignore are worse than no logs.

Usable VRAM on atlas is 7,841 MiB, not 8,192. 352 MiB is permanently
driver-reserved and never shows up in `nvidia_smi_memory_used_bytes`. The
dashboard ceiling is computed from total minus reserved on purpose, so a driver
change moves the line instead of quietly lying.

## Open items

- No alert rules yet. Planned: `ServiceDownWhileHostUp`, `DiskWillFillIn7Days`,
  `GPUVRAMNearLimit` around 7,200 MiB (92% of usable. 7,600 fires at 97%, too
  late).
- No backups of Prometheus's volume. It holds the only copy of all history.
- Atlas idles around 57W with 0 MiB VRAM used. An RTX 3070 should idle nearer
  15-20W. Unexplained. Roughly 350 kWh/year of constant draw.
