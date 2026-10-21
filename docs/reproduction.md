# Reproduction

This checkout has CPU verification evidence only. There is no completed physical experiment to reproduce yet.

Use Python 3.12 and `pip install -r requirements-cpu.lock.txt`, then `pytest -q`. The local environment used `/home/dell/anaconda3/bin/python` (3.12.7) to create `.venv312`, because the system Python 3.10 lacked ensurepip. This did not modify global Python packages.

Initialize pinned submodules with LFS smudging disabled for code checkout; required robot and external asset payloads must still be verified before GPU acceptance. Use the project's build/run scripts. A successful registry manifest lookup is not a successful image pull or a successful runtime installation.

The current real GPU development commands are `doctor --sim`, `smoke`, `acquire` and `adapt`. They fail before launching when pinned dependencies are missing. The smoke command fixes nominal mass/position/yaw; condition generation for learning uses development ranges. These are not frozen evaluation distributions.

Never reuse an existing learning output directory: the learning engine rejects overwriting it. There is no resume implementation yet; do not branch an interrupted run into multiple candidates and retain only a favorable result. Preserve incomplete logs.

`pebx reconstruct --run-dir runs/<learning-output>` replays a completed 5/20-episode learning log. Reconstruction uses actual recorded candidates and feedback and fails on changed output/hash or missing episode groups.

Private manifests belong in `private/` and runs in `runs/`; both are ignored. Do not pass condition objects or evaluator paths to the LLM. The local Python interface is a trusted-development allowlist, not strong adversarial process/container isolation.
