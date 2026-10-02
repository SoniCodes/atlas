#!/usr/bin/env bash
set -euo pipefail


IMAGES=("postgres:17" "jenkins/jenkins:lts" "alpine:latest")

for img in "${IMAGES[@]}"; do
    echo "==> scanning $img"
    f="/tmp/scan-$(echo "$img" | tr '/:' '__').json"

    docker run --rm \
        -v /var/run/docker.sock:/var/run/docker.sock \
        -v trivy-cache:/root/.cache/trivy \
        aquasec/trivy:latest image --scanners vuln --format json "$img" > "$f"

        .venv/bin/python3 load.py "$f"
done

echo "==> done"
