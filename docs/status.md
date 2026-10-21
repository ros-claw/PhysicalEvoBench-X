# 实施状态与验收记录

日期：2026-10-21。本阶段交付为可运行的 CPU 协议实现及待验收的 GPU 接线，尚未达到完整 v0.1。

工程状态：`BLOCKED_ENVIRONMENT`。研究状态：`INCONCLUSIVE`，没有物理实验结果。

| 阶段 | 当前状态 | 证据与剩余工作 |
|---|---|---|
| P0 | IMPLEMENTED / 部分 CPU_VERIFIED | 独立本地仓库与远程仓库、Python 3.12 隔离环境、两个指定 SHA、依赖锁、容器脚本、doctor；固定镜像尚未拉取完成，真实 reset/step 未通过 |
| P1 | 数学部分 CPU_VERIFIED | SE(3)、动态 TCP 转换、两夹爪编码测试；实际开闭、轴向、共同可达区域尚未标定 |
| P2 | 核心逻辑 CPU_VERIFIED / GPU 接线 IMPLEMENTED | 保持时间边界、抛掷/漂移/支撑排除、加速度轨迹、五维参数消费路径；物理敏感性与名义抓取待验证 |
| P3 | CPU_VERIFIED | 12+8 源流程、确定性随机搜索、选择回滚、账本、重建、基础设施重试；真实源学习待运行 |
| P4 | CPU_VERIFIED（协议部分） | fresh budget、Before/After 整体 alias、配对两侧重试；真实闭环、完整源审计与正式批次计费/续跑待实现验收 |
| P5 | IMPLEMENTED / 离线契约 CPU_VERIFIED | 有界 HTTP 提案器、每候选最多两请求、确定性裁剪、回退和调用日志；真实模型服务尚未验证 |
| P6 | NOT_STARTED | 无 pilot，无成功率或迁移结论 |
| P7 | 部分 IMPLEMENTED | README、中英文状态、协议、CI、复现说明；无正式发布/tag |

实际执行与证据：

```bash
.venv312/bin/python -m pytest -q
# 61 passed，详见 evidence/cpu_tests.log
.venv312/bin/python -m compileall -q src
bash -n scripts/build_container.sh scripts/run_container.sh
.venv312/bin/pebx skill-check examples/skills/initial_v1.json
.venv312/bin/pebx doctor --sim
# exit 2: BLOCKED_ENVIRONMENT，详见 evidence/doctor_sim_attempt.log
.venv312/bin/pebx freeze --config configs/experiments/smoke.yaml
# exit 2: Task distribution/bounds have not passed development validation
```

环境实况：4 × RTX A6000、驱动 595.91.07、Docker 28.2.1；系统 Python 3.10.12 缺少 ensurepip，故用现有 Anaconda Python 3.12.7 创建 `.venv312`，没有改全局环境。现有两组 Isaac Sim 6.0.1 进程继续运行，没有终止、重启或改配。

固定 6.1.0 镜像的 registry manifest 可访问，实际拉取日志见 `evidence/image_pull.log`。镜像含一个约 10.513 GB 的压缩层；两次有界拉取分别在 180 秒、600 秒达到超时，主层尚未完成；不把 registry digest 当成本地已验证镜像。`image_digest` 保持 null。当前 CPU venv 没有安装 Arena/Isaac，doctor 因此拒绝启动 Kit。

远程仓库：https://github.com/ros-claw/PhysicalEvoBench-X 。创建前已检查组织管理员身份和仓库 404；没有覆盖已有仓库。

拉取的退出码 124 记录在 `evidence/image_pull_status.json`。没有将不匹配的 6.0.1 环境冒充验收环境。

下一步顺序：完成指定镜像与上游 dev 容器构建 → 两本体 upstream reset/step → StableLift 名义抓取与 TCP/夹爪标定 → 质量/惯性/材料和参数敏感性 → 固定分布和私有 split → 随机学习真实闭环 → 真实 LLM → 双向 pilot。完整成本统计、物理故障分类、resume 和正式报告仍有工作，不能提前宣称完成。
