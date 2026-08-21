# Atlas

Homelab box for local AI inference.
Ubuntu 24.04, Ryzen 7 7700X, RTX 3070, Docker.

## Hosts

- `atlas` - the GPU machine. Inference runs here.
- `macnode` - a Mac running Fedora Asahi (Linux on Apple Silicon).
  Monitoring lives here (Prometheus, Grafana). It scrapes atlas over Tailscale.

## Layout

- `stacks/` - Docker Compose services on atlas (Ollama, exporters)
- `hosts/macnode/` - Prometheus and Grafana Quadlet units, configs
- `docs/decisions/` - ADRs (why things are the way they are)
- `docs/runbooks/` - how to rebuild and operate things
- `scripts/` - setup helpers
- `network/` - netplan
- `security/` - sshd hardening drop-in
