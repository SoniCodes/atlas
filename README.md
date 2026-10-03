# Atlas

A self-hosted GPU server I built and operate as if it were production.
Ubuntu 24.04, Ryzen 7 7700X, RTX 3070 8GB, 32 GB RAM. Headless, managed over SSH.

Atlas runs the workloads. macnode runs monitoring, and it's a separate machine on
purpose: if Atlas dies, something that isn't Atlas notices. Backups are pulled by
Atlas, not pushed by macnode.

See [the architecture diagram](docs/images/atlas-architecture.jpg).

## What runs here

**atlas**, the GPU machine:

| Service | Bound to | What it does |
|---|---|---|
| `ollama` | `127.0.0.1:11434` | GPU-accelerated local LLM and vision inference |
| `gateway` | tailnet `:8080` | FastAPI service with bearer-token auth, the only client of Ollama |
| `postgres` | `127.0.0.1:5432` | Postgres 17, holds the vulnerability scan data |
| `jenkins` | `127.0.0.1:8081` | CI, reachable only over an SSH tunnel |
| `node-exporter` | `:9100` | host metrics |
| `nvidia-exporter` | `:9835` | GPU metrics |

Three different exposure levels, on purpose. Ollama, Postgres and Jenkins are
loopback-only and can't be reached from any network. The gateway is the single
entry point and requires a token. `ufw` default-denies inbound; only SSH and
tailnet traffic are allowed.

Persistent data lives on `/data` (the HDD), never inside a container.

**macnode**, an old MacBook running Fedora Asahi (ARM). Prometheus scrapes all
three targets over Tailscale every 15s with 90-day retention, and Grafana serves
dashboards provisioned from this repo. There's one alert rule so far,
`TargetDown`, which fires when a target has been unreachable for 5 minutes.

Monitoring is on a separate machine so that a failure of Atlas doesn't take the
evidence of that failure with it.

## Vulnerability scanning

`tools/sbom/` scans my container images with Trivy and loads the results into
Postgres, so I can query them instead of scrolling through JSON.

- `scan.sh` runs Trivy against each image and writes one JSON report per image.
- `load.py` loads one or more of those reports into four tables: `scans`,
  `packages`, `vulnerabilities`, and `findings`, which ties the other three
  together.

The most useful thing it's shown me is that most findings can't be fixed yet.
Of the 724 distinct package and CVE pairs found so far, 476 have no fixed
version because the distro hasn't shipped a patch. The total is a scary number
that doesn't tell you much. The ones with a fix available are the ones worth
acting on.

To run it, put the Postgres credentials in `~/.pgpass` (the scripts never handle
the password themselves), create the venv, then run the scanner:

```bash
cd tools/sbom
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./scan.sh
```

If loading fails, run `.venv/bin/python3 connect_test.py` first. It only checks
that the database is reachable, which tells you whether the problem is the
connection or the loader.

## CI

`Jenkinsfile` at the repo root defines a four-stage pipeline: checkout, a
structure check, a secret scan that fails the build if a token value appears
anywhere in git history, and a `docker build` of the gateway image.

Jenkins itself is loopback-bound and reached over an SSH tunnel. The service has
no network exposure at all, and access is gated by SSH key auth.

## How it's operated

Rules I set for myself, because the point was understanding rather than a
working server:

- **Everything is in git.** If it isn't in this repo, it isn't real infrastructure.
- **Every non-obvious decision is written down** as an ADR: what was chosen and why.
- **Runbooks for the parts I'd forget.**
- **Nothing is "working" because it started.** A service is working when it's been
  tested. A backup isn't a backup until it's been restored.
- **No new tool until there's a problem that needs it.**
- **No AI manages this server.** I'd already seen what happens when you make
  something work without understanding it.

Commits follow Conventional Commits.

## Things that are proven, not assumed

- The Prometheus backup has been **restored**, on Atlas (x86_64) from a snapshot
  taken on macnode (ARM), with retention forced so the default 15-day window
  wouldn't silently delete the blocks being verified. Live and restored queries
  returned identical results.
- The `TargetDown` alert has been watched going from inactive to pending to
  firing when the GPU exporter on atlas went down, with the summary rendering as
  "gpu on atlas is down".
- Gateway auth verified four ways: no token → 401, bad token → 401, good token →
  200, `/healthz` → 200.
- GPU access verified **inside a container**, not just on the host.
- When I restructured `load.py`, I loaded the same report with the old code and
  the new code and checked that both produced the same 382 findings.

## Known gaps

Listed because they're real, not because they're planned:

- **Nothing notifies.** I added `TargetDown` after finding a 55-hour monitoring
  outage by accident, two days late. But there's no Alertmanager, so the alert
  only shows up in the Prometheus UI. Someone still has to be looking.
- **Backups are manual.** There's no timer yet, so the archive is only as fresh
  as the last time I ran it.
- **No resource limits on containers.** Nothing stops one from taking the host down.
- **The gateway's `requirements.txt` is unpinned**, so two builds of identical
  source can produce different images.
- **The secret scan only knows about the gateway token.** The Postgres password
  lives in its own `.env`, and nothing in CI checks that it stays out of git.
- **No offsite backup.** Both machines are in the same building.

## Layout

- `stacks/`: Docker Compose services on atlas (ollama, gateway, postgres, monitoring, jenkins)
- `hosts/macnode/`: Prometheus and Grafana Quadlet units, configs and alert rules
- `tools/sbom/`: container image vulnerability scanner and loader
- `docs/decisions/`: ADRs
- `docs/incidents/`: incident writeups
- `docs/runbooks/`: how to rebuild and operate things
- `Jenkinsfile`: CI pipeline
- `scripts/`: setup helpers
- `network/`: netplan
- `security/`: sshd hardening drop-in
