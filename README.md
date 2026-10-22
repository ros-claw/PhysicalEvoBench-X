# PhysicalEvoBench-X

Measuring whether newly acquired robot experience improves another embodiment under matched adaptation budgets.

The v0.1 track compares Franka/Panda Hand and Franka/Robotiq 2F-85 using a shared state-based StableLift executor. It measures the marginal effect of **SourceAfter versus SourceBefore**, under independent target budgets of 0, 5 and 20 episodes. This is near-embodiment parameter transfer, not a claim of arbitrary robot generalization.

**Current status: pinned native runtime, both-body reset/step and 10 nominal StableLift successes per body are GPU verified.** A real 20-episode source run and 0/5-budget paired development bridge are complete; formal transfer experiments are not complete. The real Kimi K3 proposer is connected. See [implementation status](docs/status.md) and [中文说明](README.zh-CN.md).

## CPU development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-cpu.lock.txt
pytest -q
pebx --help
pebx skill-check examples/skills/initial_v1.json
pebx doctor
```

The CPU package supports Python >=3.10; simulation requires Python 3.12. Importing the CPU CLI never imports Isaac/Kit. `doctor` exits 2 when the pinned simulation environment is unavailable and saves the detailed check report. The CPU lock was verified on Linux x86_64 / Python 3.12.7.

## Pinned simulation setup

The validated route is the [independent native uv environment](docs/native_runtime.md). Use `scripts/setup_native.sh` and `ACCEPT_EULA=Y PEBX_GPU=0 scripts/run_native.sh ...`. The container alternative below remains unvalidated.


```bash
GIT_LFS_SKIP_SMUDGE=1 git submodule update --init --recursive
# Fetch required asset payloads separately; skipping LFS is only for source setup.
./scripts/build_container.sh
ACCEPT_EULA=Y PEBX_GPU=0 ./scripts/run_container.sh doctor --sim
ACCEPT_EULA=Y PEBX_GPU=0 ./scripts/run_container.sh smoke \
  --embodiment franka_panda --episodes 10 --output runs/panda_nominal
ACCEPT_EULA=Y PEBX_GPU=0 ./scripts/run_container.sh smoke \
  --embodiment franka_robotiq --episodes 10 --output runs/robotiq_nominal
```

These container build and simulation commands are implementation entry points **awaiting successful execution**, not reproduction claims. NVIDIA EULA acceptance belongs to the operator. The wrapper mounts the entire project and selects one GPU; it leaves existing processes alone. Arena and Lab commits are pinned in [dependencies.lock.yaml](dependencies.lock.yaml). A registry manifest digest is recorded separately from a successfully pulled local image digest.

## Implemented interfaces

- `doctor [--sim]`: environment checks and an actual upstream Arena reset/step probe.
- `skill-check`: strict complete five-dimensional SkillSpec validation.
- `generate-conditions`: deterministic private **development** manifests; never a frozen test split.
- `smoke`, `acquire`, `adapt`: real PhysX development entry points, gated on runtime availability. Acquire uses 12 exploration + 8 validation episodes; adapt uses fresh 0/5/20 budgets.
- `freeze`: refuses unvalidated development configurations, absent local digest, missing physical evidence or stale hashes.
- `reconstruct`: rebuilds the selection and final artifact from candidate and episode logs.
- `validate-run`: checks evidence schemas, dependencies, trajectories and accounting; rejects fake records. It does not yet certify a complete formal pilot matrix.

Python modules additionally implement paired evaluation with both-side retries, target adaptation aliases, random proposals, a bounded OpenAI-compatible LLM transport, canonical SE(3) action encoding, an acceleration-limited executor and the authoritative stable-hold judge. A real Kimi K3 request has been validated; see [configuration and measured usage](docs/kimi_k3.md).

`calibrate`, `dynamics-check` and `llm-probe` are also available. `evaluate`, `run` and `report` are not yet exposed as CLI commands. Complete P1/P2 physical acceptance before freezing or running a pilot. The development runner creates a new environment per episode to isolate dynamics; throughput and reset correctness still require GPU checks.

## Evidence and protocol

[Protocol](docs/protocol_v0.1.md), [full task specification](docs/implementation_plan.md), [reproduction](docs/reproduction.md), [upstream audit](docs/upstream_audit.md), [limitations](docs/limitations.md).

Fake runners exist only in tests and every fake result is labeled. CPU tests verify contracts and protocol logic; they do not validate contacts, reachability, dynamics, or physical grasp success. Negative or zero transfer is a valid research outcome.
