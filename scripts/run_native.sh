#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${ACCEPT_EULA:?Set ACCEPT_EULA=Y after accepting the NVIDIA Isaac Sim EULA}"
export OMNI_KIT_ACCEPT_EULA=YES
export HEADLESS=1
export CUDA_VISIBLE_DEVICES="${PEBX_GPU:-0}"
export ISAACLAB_ARENA_FORCE_EXIT_ON_COMPLETE=1
export PYTHONUNBUFFERED=1
# Do not resolve the executable symlink: doing so bypasses its pyvenv.cfg.
exec "$PWD/third_party/IsaacLab-Arena/.venv/bin/python" -m physicalevobench_x.cli "$@"
