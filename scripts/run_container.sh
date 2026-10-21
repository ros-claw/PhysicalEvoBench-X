#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${ACCEPT_EULA:?Set ACCEPT_EULA=Y after accepting the NVIDIA Isaac Sim EULA}"
# Dedicated GPU by index; don't consume all four GPUs or affect existing jobs.
docker run --rm --gpus "device=${PEBX_GPU:-0}" --shm-size=8g \
  -e ACCEPT_EULA -e PRIVACY_CONSENT=Y \
  -v "$PWD:/workspaces/physicalevobench_x" \
  -w /workspaces/physicalevobench_x pebx:dev "$@"
