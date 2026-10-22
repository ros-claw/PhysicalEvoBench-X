#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
arena="$PWD/third_party/IsaacLab-Arena"
[[ $(git -C "$arena" rev-parse HEAD) == c7edf3a9d5d8276565208f72422f8f8a0806d6cf ]]
[[ $(git -C "$arena/submodules/IsaacLab" rev-parse HEAD) == 91a0906f93802eb859192dcb0bca879f891e92d6 ]]
# UV_CACHE_DIR may point to a prepopulated package cache. It is never a runtime dependency.
uv sync --locked --extra dev --project "$arena"
uv pip install --python "$arena/.venv/bin/python" --no-deps -e .
"$arena/.venv/bin/python" -m physicalevobench_x.cli doctor --output evidence/native/doctor.json
