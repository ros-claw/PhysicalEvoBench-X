# Native Arena runtime (2026-10-22)

The project now has its own Arena virtual environment at `third_party/IsaacLab-Arena/.venv`. It was created with the pinned upstream `uv.lock` using `uv sync --locked --extra dev`. A prepopulated download cache was reused, but no old-project Python package or environment is a runtime dependency. The original repository and its running processes were left alone.

Validated versions: Python 3.12.13, Isaac Sim 6.1.0.0, Isaac Lab 17.0.2, Arena's package version 0.3.0 at the required git SHA, Torch 2.11.0+cu128. Native NumPy 2.3.1 and Pydantic 2.11.10 pass the same CPU contracts as the separate CPU environment. Runtime records and the upstream uv lock hash are in `evidence/native/` and `dependencies.lock.yaml`.

```bash
# Optional: point UV_CACHE_DIR at a prepopulated cache to avoid repeat downloads.
./scripts/setup_native.sh
ACCEPT_EULA=Y PEBX_GPU=0 ./scripts/run_native.sh doctor --sim --embodiment franka_panda
ACCEPT_EULA=Y PEBX_GPU=0 ./scripts/run_native.sh doctor --sim --embodiment franka_robotiq
ACCEPT_EULA=Y PEBX_GPU=0 ./scripts/run_native.sh calibrate \
  --embodiment franka_panda --output runs/panda_calibration_new
ACCEPT_EULA=Y PEBX_GPU=0 ./scripts/run_native.sh dynamics-check \
  --embodiment franka_panda --output runs/panda_dynamics_new
```

The fixed AppLauncher parser has no `--headless` flag. The wrapper supplies `HEADLESS=1`. It uses one selected GPU and preserves the venv executable path without resolving its Python symlink. Arena's force-exit workaround avoids Kit shutdown hanging; acceptance relies on written results plus process status, not an exit code alone.

The native route records package/lock provenance rather than claiming a successfully pulled container digest. The Docker route remains available; the earlier download timeouts remain in evidence. Freeze checks accept native provenance only when both lock/snapshot checksums and actual simulator version match, and still require every physical acceptance artifact. A native install alone cannot freeze the task.

Development findings and repairs:

- The high upstream Panda ready pose exceeded the declared control workspace. Both robots now receive the same explicit seven arm-joint ready angles; gripper initial joints follow their actual configurations.
- Both configurations use 64 position and 4 velocity contact-solver iterations and explicit 2 mm contact offsets. Panda's fixed gripper drive uses 40 N effort limit, stiffness 500 and damping 40. These are development calibration choices, not learnable parameters. Before/After and both learners use the same frozen configuration within an embodiment. Judge thresholds were retained.
- Manager configs are deep-copied upstream. Authoritative task state is bound to the live environment, avoiding disconnected success/failure/recorder task copies.
- Every process/episode gets a unique HDF5 recorder path; the initial parallel calibration attempt exposed a shared default dataset lock collision.
- Full 505-step Panda and Robotiq calibration traces were recorded before a NumPy boolean serialization error. The CPU audit recovered those complete traces; the serialization issue was fixed. Both calibrations were subsequently rerun with clean process exits; the older recovered evidence is retained separately. Recovered evidence is explicitly labeled.
- A first dynamic-setter mass diagnostic failed backend/impulse consistency. The production runner does not use that path: it isolates every condition in a new scene with spawn-time mass. The diagnostic was changed to test that same production strategy. Fresh low/high/low scenes give correct backend mass/inertia/material readbacks and force response. Persistent online mass randomization remains unsupported.

Raw task runs and full traces are retained locally under `runs/`; small authentic episode tables, checksums and diagnostic reports are tracked under `evidence/gpu/`. Nominal successes are development acceptance evidence, not formal transfer measurements.
