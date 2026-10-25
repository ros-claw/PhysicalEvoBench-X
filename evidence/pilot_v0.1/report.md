# PhysicalEvoBench-X matrix report

Track: `frozen_pilot`; formal result eligible: **true**.

Complete learning packages: 12/12. Unresolved physical calls: 0.

| Learner | Direction | Budget | Independent runs | Before SR | After SR | Mean delta | Min / max |
|---|---|---:|---:|---:|---:|---:|---|
| bounded_llm_v1 | franka_panda → franka_robotiq | 0 | 3 | 0.9733 | 0.9733 | 0.0000 | 0.0000 / 0.0000 |
| bounded_llm_v1 | franka_panda → franka_robotiq | 5 | 3 | 0.9733 | 0.9733 | 0.0000 | 0.0000 / 0.0000 |
| bounded_llm_v1 | franka_panda → franka_robotiq | 20 | 3 | 0.9733 | 0.9733 | 0.0000 | 0.0000 / 0.0000 |
| bounded_llm_v1 | franka_robotiq → franka_panda | 0 | 3 | 1.0000 | 0.9667 | -0.0333 | -0.1000 / 0.0000 |
| bounded_llm_v1 | franka_robotiq → franka_panda | 5 | 3 | 1.0000 | 0.9667 | -0.0333 | -0.1000 / 0.0000 |
| bounded_llm_v1 | franka_robotiq → franka_panda | 20 | 3 | 1.0000 | 0.9667 | -0.0333 | -0.1000 / 0.0000 |
| random_search_v1 | franka_panda → franka_robotiq | 0 | 3 | 0.9733 | 0.9733 | 0.0000 | 0.0000 / 0.0000 |
| random_search_v1 | franka_panda → franka_robotiq | 5 | 3 | 0.9733 | 0.9733 | 0.0000 | 0.0000 / 0.0000 |
| random_search_v1 | franka_panda → franka_robotiq | 20 | 3 | 0.9733 | 0.9733 | 0.0000 | 0.0000 / 0.0000 |
| random_search_v1 | franka_robotiq → franka_panda | 0 | 3 | 1.0000 | 1.0000 | 0.0000 | 0.0000 / 0.0000 |
| random_search_v1 | franka_robotiq → franka_panda | 5 | 3 | 1.0000 | 1.0000 | 0.0000 | 0.0000 / 0.0000 |
| random_search_v1 | franka_robotiq → franka_panda | 20 | 3 | 1.0000 | 1.0000 | 0.0000 | 0.0000 / 0.0000 |

All run points, source acceptance decisions, aliases, failure counts and model costs are retained in `report.json`. Missing packages are not replaced with zero-gain observations.

- Pilot points are independent learning runs; test episodes are not independent learning replicates.
- No significance claim from three learning runs.
- Known completed physical calls only; unresolved in-flight work has unknown additional cost.
- Excludes development, calibration, and other suites; GPU time is not exclusive occupancy.
- Formal eligibility requires independent frozen-evidence audit.
