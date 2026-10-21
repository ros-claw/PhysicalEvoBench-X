#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
arena=third_party/IsaacLab-Arena
[[ $(git -C "$arena" rev-parse HEAD) == c7edf3a9d5d8276565208f72422f8f8a0806d6cf ]]
[[ $(git -C "$arena/submodules/IsaacLab" rev-parse HEAD) == 91a0906f93802eb859192dcb0bca879f891e92d6 ]]
docker build --target dev --build-arg BASE_IMAGE=nvcr.io/nvidia/isaac-sim@sha256:0c16dd67d09a70ea474f2c809a13c4d09bd23c738184cf1bf28af487ecd39080 -f "$arena/docker/Dockerfile.isaaclab_arena" -t pebx-arena:dev "$arena"
docker build -f docker/Dockerfile -t pebx:dev .
