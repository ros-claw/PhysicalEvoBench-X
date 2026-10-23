# PhysicalEvoBench-X

在相同适配预算下，测量一台机器人的新增经验能否改善另一台机器人的表现。

首版是 Franka + Panda Hand 与 Franka + Robotiq 2F-85 之间的近本体参数经验迁移。用共享冻结执行器完成 StableLift，比较源学习前后产物，源学习 20 回合，目标预算 0/5/20 分别全新启动。源端回滚时复用目标适配和评测，避免相同输入两次随机搜索制造假收益。

目前实现了可安装包、CLI、五维严格 schema、坐标与夹爪适配数学、轨迹和固定执行器、稳定抬升判定、随机提案器、有界 LLM HTTP 提案器、预算账本、选择/回滚、重建、配对重试和等价复用。真实 Arena 任务工厂、状态读取和开发 runner 已接线，已通过双本体 reset/step、名义抓取及基础控制标定；完整参数敏感性和正式协议验收仍待完成。

**两个本体已各完成 10 次真实名义 StableLift 抓取，全部成功；Kimi K3 已实测连通。正式迁移实验尚未完成。** 不能把测试通过理解为项目已经完成 P0–P7。

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

已验证的原生安装与命令见 [原生运行环境](docs/native_runtime.md)，真实模型配置和用量见 [Kimi K3 接入](docs/kimi_k3.md)。当前 CPU 契约测试为 84 项，CPU 与仿真环境均通过。

2026-10-23 更新：v2 的 46 个开发范围测点已完成（Panda 21/23，Robotiq 23/23），失败全部保留。最终配置同时显式设置 root/link solver，仍需重新验收。`pebx run` 已接入最终验收、工程闭环 smoke、每本体 100 回合吞吐、冻结和完整双向 pilot；`pebx evaluate`、`pebx report` 也已接入。详见 [运行与续跑](docs/pilot_execution.md)。正式实验是否完成以独立审计和真实结果为准。
