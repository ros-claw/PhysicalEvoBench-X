# Current limits and next physical gates

- No true StableLift grasp, TCP calibration, parameter sensitivity study, or transfer gain has been measured.
- The GPU factory/reader/task/runner are implemented against inspected pinned source, but remain unexecuted. Development mappings, common workspace and robot/table geometry must be calibrated.
- Joint/workspace safeguards, failure subtype classification, full terminal trajectory coverage and physical calibration need further GPU work. Current judge excludes throws, relative drift, out-of-bounds and known table support; it has no validated contact topology sensor.
- Development runner rebuilds the environment per episode. Mass readback is coded, but impulse/inertia/material validation and throughput have not been performed.
- Protocol source/target, alias and paired-retry paths are CPU tested. Complete physical pilot accounting, source-audit orchestration, resume, stronger learner isolation and full formal reporting remain pending. Evidence schema validation never grants formal eligibility.
- The LLM transport has bounded repair/fallback tests but no real provider/model test. Model revision and provider token validation need actual service configuration.
- No test split is frozen, no image/asset is assumed verified, and no paper/benchmark claim is supported by the CPU unit tests.
