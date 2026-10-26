# PhysicalEvoBench-X

在相同适配预算下，测量一台机器人的新增经验能否改善另一台机器人的表现。

首版是 Franka + Panda Hand 与 Franka + Robotiq 2F-85 之间的近本体参数经验迁移。用共享冻结执行器完成 StableLift，比较源学习前后产物，源学习 20 回合，目标预算 0/5/20 分别全新启动。源端回滚时复用目标适配和评测，避免相同输入两次随机搜索制造假收益。

目前实现了可安装包、CLI、五维严格 schema、坐标与夹爪适配数学、轨迹和固定执行器、稳定抬升判定、随机提案器、有界 LLM HTTP 提案器、预算账本、选择/回滚、重建、配对重试和等价复用。真实 Arena 任务工厂、状态读取与 runner 已通过最终 GPU 验收，完整双向 pilot 已实际执行。

**2026-10-25：冻结内部 pilot 已完成 12/12 包、3,390 次真实物理执行，通过完整证据审计。** 10 个源 run 回滚，2 个接受更新；没有观察到正的目标成功率迁移，结果包含零迁移与负迁移。三个独立学习 seed 不支持总体显著性结论。详见 [最终报告](evidence/pilot_v0.1/report.zh-CN.md) 和 [后续计划](docs/next_steps_20261025.md)。P7 的固定抽样可视化、独立安装复现与发布审查仍待完成，不将协议审计通过解释为全部 P0–P7 完成。

**物理解释边界：** 原生探针发现接触约束下 PhysX 报告角速度与姿态变化率显著不同。上述负迁移指冻结原生状态判据上的负差，不能直接证明物体持续宏观旋转或通用物理技能退化；见 [状态语义核查](docs/state_semantics_20261025.md)。新参数干预使用独立开发条件，不能事后改变原结果。

**2026-10-26 开发进展：** [144 回合独立参数干预](docs/intervention_results_20261026.md) 已全部完成，无基础设施失败或未决调用，未复现 Panda 的原负差。新的姿态轨迹测量候选在 [独立开发分支](https://github.com/ros-claw/PhysicalEvoBench-X/tree/implementation/v0.2-measurement) 实施，不修改本分支冻结输入，也不重报原 pilot。

本机开发命令：

```bash
source .venv312/bin/activate
pytest -q
pebx --help
pebx doctor --sim
pebx skill-check examples/skills/initial_v2.json
```

`doctor` 的退出码 2 表示仿真环境不就绪，详情写入 `evidence/doctor.json`。容器安装和运行入口见 [英文 README](README.md)，当前阶段和阻断证据见 [实施状态](docs/status.md)。

已实现最终验收、双向批次、阶段续跑和独立报告审计；这些工程功能须先经过当前物理修订的最终验收，再冻结并运行完整 pilot，不会生成占位成功率。

已验证的原生安装与命令见 [原生运行环境](docs/native_runtime.md)，真实模型配置和用量见 [Kimi K3 接入](docs/kimi_k3.md)。当前 v0.1 CPU 契约测试为 93 项，CPU 与仿真环境均通过。

2026-10-23 更新：v2 的 46 个开发范围测点已完成（Panda 21/23，Robotiq 23/23），失败全部保留。最终配置同时显式设置 root/link solver，仍需重新验收。`pebx run` 已接入最终验收、工程闭环 smoke、每本体 100 回合吞吐、冻结和完整双向 pilot；`pebx evaluate`、`pebx report` 也已接入。详见 [运行与续跑](docs/pilot_execution.md)。正式实验是否完成以独立审计和真实结果为准。
