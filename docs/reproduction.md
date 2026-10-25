# Reproduction

The frozen internal pilot completed all twelve learning packages and passed the full frozen-evidence audit on 2026-10-25. [Archived results](../evidence/pilot_v0.1/report.md) include zero and negative transfer; no positive target success-rate transfer was observed. Release review and independent-installation reproduction remain pending. Audit eligibility does not certify positive transfer, arbitrary robot generalization or isolation against malicious submissions.

## CPU

Use Python 3.12 and `pip install -r requirements-cpu.lock.txt`, then `pytest -q`. The separate CPU environment uses Python 3.12.7; the native simulation environment uses 3.12.13 and its upstream-locked dependencies. The latest CPU check passes 87 tests, including three tests of the completed-package review tool. A CPU test result never certifies physics.

## Native simulation

Initialize the pinned submodules with `GIT_LFS_SKIP_SMUDGE=1 git submodule update --init --recursive`. Skipping model payloads during code setup is not asset acceptance. `scripts/setup_native.sh` uses upstream `uv sync --locked --extra dev` and installs this package without replacing pinned upstream dependencies. An optional `UV_CACHE_DIR` can reuse an existing download cache; the original PhysicalEvoBench code/environment is not required.

```bash
./scripts/setup_native.sh
ACCEPT_EULA=Y PEBX_GPU=0 scripts/run_native.sh doctor --sim --embodiment franka_panda
ACCEPT_EULA=Y PEBX_GPU=0 scripts/run_native.sh doctor --sim --embodiment franka_robotiq
ACCEPT_EULA=Y PEBX_GPU=0 scripts/run_native.sh smoke --embodiment franka_panda --episodes 10 --output runs/new_panda_nominal
ACCEPT_EULA=Y PEBX_GPU=0 scripts/run_native.sh smoke --embodiment franka_robotiq --episodes 10 --output runs/new_robotiq_nominal
ACCEPT_EULA=Y PEBX_GPU=0 scripts/run_native.sh acquire --embodiment franka_panda --seed 0 --output runs/new_source
.venv312/bin/pebx reconstruct --run-dir runs/new_source
```

The wrapper sets the actual supported headless environment flag and selects one GPU. Outputs are exclusive-create; never reuse an existing run directory. The current fresh-scene worker is slow, so measure throughput before a pilot. The checked runtime/package/lock snapshot is in `evidence/native/`; installation and physical acceptance are separate checks.

For the development paired bridge, use the native interpreter with `HEADLESS=1`, `ACCEPT_EULA=Y`, `OMNI_KIT_ACCEPT_EULA=YES`, `CUDA_VISIBLE_DEVICES=<one GPU>` and `ISAACLAB_ARENA_FORCE_EXIT_ON_COMPLETE=1`:

```bash
third_party/IsaacLab-Arena/.venv/bin/python -m physicalevobench_x.dev_evaluate \
  --source runs/new_source --target franka_robotiq --target-budget 0 \
  --test-conditions 2 --output runs/new_zero_bridge
```

Repeat separately with target budget 5 or 20 and a new output. Each budget starts fresh. This bridge is explicitly non-formal and does not replace source audits or the pilot. An equivalent source artifact aliases the whole target adaptation and paired evaluation; it must not be sampled twice to manufacture a delta.

`scripts/run_sensitivity.py` and `scripts/check_adversarial_judge.py` run with the same native startup environment. They record real development sensitivity and trusted evaluator diagnostics. Do not mix their deliberately perturbed diagnostic rollouts into learner success-rate tables.

Model configuration, local credential handling and measured request evidence are documented in [Kimi K3](kimi_k3.md). Do not put private conditions, source histories or test feedback into target model requests. The current local interface is not an adversarial container security boundary.

Resume uses immutable completed-stage checkpoints and request-bound physical/model journals. Completed calls replay without new physical execution or model requests; ambiguous `STARTED` calls stop automatic resume. Preserve all attempts and never branch checkpoints to retain a favorable result. The current pilot has actually resumed after a disk-space stop. Commands and limitations are in [pilot execution](pilot_execution.md).

While a pilot runs, check only finished packages with an exclusive new output:

```bash
.venv312/bin/python tools/check_completed_packages.py \
  --suite runs/complete-v2-20261023/pilot \
  --output runs/progress-review-NEW.json
```

The tool captures the completed package set once, verifies checkpoints, request identities, condition/skill coverage, trajectories, source/target reconstruction, paired arithmetic and costs. It excludes unfinished packages and always returns `formal_result_eligible=false`. It does not replace the full frozen-suite auditor, including its model-call and full-matrix checks. Do not edit frozen source/configuration/scripts during a running experiment. This review tool lives outside that execution input set.

Docker remains an alternative implementation path whose image download/build has not been validated here. Native provenance is recorded honestly without inventing a container digest.

On 2026-10-24, a separate local clone of project commit `d2e1c13` ran one nominal episode per embodiment successfully. Import provenance confirmed the package came from the new clone. This reused the pinned upstream checkout, installed native environment and cached assets, with the upstream directory explicitly linked into the clone. It is a clean **project-source** smoke, not a clean dependency installation or independent-machine replication. [Evidence and checksums](../evidence/reproduction/source_smoke_20261024.json) record both physical episodes separately from the formal pilot.
