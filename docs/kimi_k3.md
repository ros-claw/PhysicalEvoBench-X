# Kimi K3 proposer integration

Validated on 2026-10-22 using the supplied Kimi Coding account. No credential is included in tracked files.

```yaml
endpoint: https://api.kimi.com/coding/v1/chat/completions
model: k3
temperature: 1
reasoning_effort: low
max_output_tokens: 800
max_input_tokens: 6000
```

The provider's authenticated `/coding/v1/models` response advertises `k3` with a 1,048,576-token context window. This is a catalog capability, not a measured 1M-context stress test. The benchmark still applies its fixed 6,000 input / 800 output limits and fresh target contexts. Do not silently use `kimi-for-coding`: it is a different model alias.

The first temperature-0 proposal attempts received HTTP errors; a separate diagnostic confirmed HTTP 400 with the message that this model only accepts temperature 1. With temperature 1 and low reasoning effort, a real bounded proposal succeeded on the first request: response model `k3`, 9.605 s wall time, 707 prompt tokens and 247 completion tokens (including 131 reasoning tokens). The complete returned SkillSpec passed schema validation without repair/fallback. This single request demonstrates connectivity and format compatibility, not algorithmic superiority.

Configuration: `configs/learners/kimi_k3.yaml`. Credentials are read from `PEBX_LLM_API_KEY`, or an ignored local `.env` file with permission 0600. `.env.example` has no key. The HTTP client identifies itself truthfully as PhysicalEvoBench-X; it does not impersonate another coding client.

```bash
.venv312/bin/pebx llm-probe --config configs/learners/kimi_k3.yaml --output runs/kimi_probe_new
ACCEPT_EULA=Y PEBX_GPU=0 scripts/run_native.sh adapt \
  --embodiment franka_robotiq --budget 5 --seed 0 \
  --skill examples/skills/initial_v1.json --learner bounded_llm_v1 \
  --learner-config configs/learners/kimi_k3.yaml --output runs/kimi_adaptation_new
```

Each candidate permits one generation plus at most one repair; failures fall back to the incumbent while the planned physical rollouts remain charged. Provider usage, response model, temperature, effort, prompt hash, response and timing are logged without authorization headers. An immutable model-weight revision is not exposed by this API and cannot be claimed pinned. API randomness is handled by the protocol's information-equivalent result aliases, not by assuming deterministic inference.

Official references: [model IDs, context and protocol URLs](https://www.kimi.com/code/docs/kimi-code/models.html), [API endpoints](https://www.kimi.com/code/docs/). Authenticated response/proposal evidence is in `evidence/llm/kimi_k3/`.

A real 5-episode Robotiq adaptation subsequently completed (3 exploration + 2 validation). Its two candidate proposals used three HTTP requests total: the first output had Markdown fences, was rejected as non-JSON, and was repaired within the one-repair allowance. All three calls together used 3,449 provider-reported tokens. The selector retained the initial artifact (`NO_BEHAVIOR_CHANGE`); deterministic reconstruction passed. This validates the feedback/proposal/budget chain without claiming a useful learned update. See `physical_adaptation_*` evidence.

2026-10-23 的 v2 实际探测：原始响应含 Markdown 围栏，严格解析失败；协议允许的一次修复返回合法 `grasp_lift_state_v2` 和新范围内的完整五维参数。两次请求分别耗时约 6.89/8.36 秒，总用量 2,132 token（1,657 输入、475 输出，205 reasoning 为输出子集）。证据在 `evidence/llm/kimi_k3/v2/`。这只验证服务和参数契约，不声称该提案改善物理性能。后续调用增加 UTC、响应 ID/created 和 HTTP 状态记录；不可变权重 revision 仍不可用。
