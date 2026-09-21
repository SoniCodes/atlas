# Atlas

A self-hosted GPU server I built and operate as if it were production.
Ubuntu 24.04, Ryzen 7 7700X, RTX 3070 8GB, 32 GB. Headless, managed over SSH.

Atlas runs the workloads. macnode runs monitoring, deliberately in a separate
failure domain — if Atlas dies, something that isn't Atlas notices. Backups are
pulled by Atlas, not pushed by macnode.

See [the architecture diagram](docs/images/atlas-architecture.jpg).

## Why this exists

I was doing contract work building containerized environments so open-source
repos could be built and tested in CI. Almost none of the failures were the
code — they were the environment. Missing dependencies, missing CA certificates,
tests that passed locally and died in the pipeline.

I was making those environments work without understanding the layer underneath
them. This is the server I built to close that gap.

## What runs here

**atlas** — the GPU machine.

| Service | Bound to | What it does |
|---|---|---|
| `ollama` | `127.0.0.1:11434` | GPU-accelerated local LLM and vision inference |
| `gateway` | tailnet `:8080` | FastAPI service, bearer-token auth, the only client of Ollama |
| `node-exporter` | `:9100` | host metrics |
| `nvidia-exporter` | `:9835` | GPU metrics |
| `jenkins` | `127.0.0.1:8081` | CI — reachable only over an SSH tunnel |

Three different exposure levels, on purpose. Ollama is loopback-only and can't be
reached from any network. The gateway is the single entry point and requires a
token. `ufw` default-denies inbound; only SSH and tailnet traffic are allowed.

**macnode** — an old MacBook running Fedora Asahi (ARM). Prometheus scrapes all
three targets over Tailscale every 15s with 90-day retention; Grafana serves
dashboards provisioned from this repo.

Monitoring is on a separate machine so that a failure of Atlas doesn't take the
evidence of that failure with it.

## CI

`Jenkinsfile` at the repo root defines a four-stage pipeline: checkout, structure
check, a secret scan over git history that fails the build if a token value
appears, and a `docker build` of the gateway image.

Jenkins itself is loopback-bound and reached over an SSH tunnel — the service has
no network exposure at all, and access is gated by SSH key auth.

## How it's operated

Rules I set for myself, because the point was understanding rather than a
working server:

- **Everything is in git.** If it isn't in this repo, it isn't real infrastructure.
- **Every non-obvious decision is written down** as an ADR — what was chosen and why.
- **Runbooks for the parts I'd forget.**
- **Nothing is "working" because it started.** A service is working when it's been
  tested. A backup isn't a backup until it's been restored.
- **No new tool until there's a problem that needs it.**
- **No AI manages this server.** I'd already seen what happens when you make
  something work without understanding it.

Commits follow Conventional Commits.

## Things that are proven, not assumed

- The Prometheus backup has been **restored** — on Atlas (x86_64) from a snapshot
  taken on macnode (ARM), with retention forced so the default 15-day window
  wouldn't silently delete the blocks being verified. Live and restored queries
  returned identical results.
- Gateway auth verified four ways: no token → 401, bad token → 401, good token →
  200, `/healthz` → 200.
- GPU access verified **inside a container**, not just on the host.

## Known gaps

Listed because they're real, not because they're planned:

- **No alert rules.** Monitoring exists; alerting doesn't. `up == 0` would have
  caught a 55-hour outage that I found by accident, two days late.
- **Backups are manual.** There's no timer yet, so the archive is only as fresh
  as the last time I ran it.
- **No resource limits on containers.** Nothing stops one from taking the host down.
- **`requirements.txt` is unpinned**, so two builds of identical source produce
  different images.
- **No offsite backup.** Both machines are in the same building.

## Layout

- `stacks/` — Docker Compose services on atlas (ollama, gateway, monitoring, jenkins)
- `hosts/macnode/` — Prometheus and Grafana Quadlet units and configs
- `docs/decisions/` — ADRs
- `docs/runbooks/` — how to rebuild and operate things
- `Jenkinsfile` — CI pipeline
- `scripts/` — setup helpers
- `network/` — netplan
- `security/` — sshd hardening drop-in
