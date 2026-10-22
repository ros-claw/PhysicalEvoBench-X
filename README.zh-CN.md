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
pebx skill-check examples/skills/initial_v1.json
```

`doctor` 的退出码 2 表示仿真环境不就绪，详情写入 `evidence/doctor.json`。容器安装和运行入口见 [英文 README](README.md)，当前阶段和阻断证据见 [实施状态](docs/status.md)。

下一道关卡是固定环境真实 reset/step，随后验证双夹爪开闭、TCP 轴向、名义抓取、质量写入与参数敏感性。完成后才能冻结分布和进入双向 pilot。未实现的正式批次编排、完整验收和报告功能有明确记录，不会生成占位成功率。

已验证的原生安装与命令见 [原生运行环境](docs/native_runtime.md)，真实模型配置和用量见 [Kimi K3 接入](docs/kimi_k3.md)。当前 CPU 契约测试为 65 项，CPU 与仿真环境均通过。
