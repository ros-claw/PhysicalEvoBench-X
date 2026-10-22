# 实施状态与验收记录

日期：2026-10-22。原先的部署阻断已解除；上游依赖元数据例外仍需正式审查；当前已有真实 PhysX 仿真证据，尚未完成正式 v0.1 pilot。

正式研究状态：`INCONCLUSIVE`。首个开发源学习包：`NO_ACCEPTED_UPDATE`。没有声称正迁移。

| 阶段 | 当前状态 | 实际证据与剩余关卡 |
|---|---|---|
| P0 | GPU_VERIFIED | X 独立原生 uv 环境，Arena/Lab 指定 SHA；两本体分别真实 reset + 10 控制步，0.005/0.02 秒频率读回正确 |
| P1 | 基础控制 GPU_VERIFIED | 两夹爪开闭、world x/y/z、旋转保持检查通过；各 10 次名义 StableLift 全部成功；完整本体差异清单与更广工作区验证仍需完善 |
| P2 | 部分 GPU_VERIFIED | 连续保持、任务终止和 pre-reset 证据已接通；质量/惯性/材料读回与受控力响应通过；Panda 五维低中高 15 回合测量完成，Robotiq 五维 15 回合测量也完成；低界仍有不可行/失败点，任务分布和边界尚未冻结 |
| P3 | 开发闭环 GPU_VERIFIED | 真实源学习 20 回合，12 探索 + 8 验证；随机搜索、选择、回滚、成本与重建通过；首包回滚，无有效源更新 |
| P4 | 开发物理检查通过（0/5 预算） | fresh budget/alias/双侧重试已有测试；Panda→Robotiq 的 0 和 5 回合预算分别完成，两预算各 2 个配对条件均成功；源回滚触发整次适配/评测正确 alias，差值精确为 0；5 回合预算实际执行 3 探索 + 2 验证，未把重复候选免费缓存；正式 0/5/20 矩阵、源审计和续跑未完成 |
| P5 | 真实服务与目标反馈链通过 | Kimi K3 实测请求；真实 5 回合 Robotiq 适配，3 探索 + 2 验证，3 次模型请求含一次格式修复，重建通过；未接受技能更新 |
| P6 | NOT_STARTED | 无正式双向 pilot，不发布正式迁移成功率或显著性结论 |
| P7 | 部分 IMPLEMENTED | 原生复现脚本、模型配置、证据与 CI；未发布 v0.1 tag |

实际结果（全部为开发验收）：

- Panda：10/10 名义稳定抬升成功，最大抬升约 0.118 m。
- Robotiq：10/10 名义稳定抬升成功，最大抬升约 0.113 m。
- 请求 TCP 平移 10 mm，实际约 9.5–9.6 mm；旋转保持 TCP 漂移小于 0.25 mm。
- 空夹开/关/再开：Panda 约 80/0.24/80 mm，Robotiq 约 83.1/0.075/83.1 mm。
- 0.1/0.5/0.1 kg 独立场景中，相同 2 N × 0.02 s 水平作用产生约 0.40/0.08/0.40 m/s 的速度增量；后端质量、惯性、材料读回符合声明。
- 首个随机源包：探索选中候选 4，验证初值与候选均 4/4 成功，中位完成时间 8.24 → 8.06 s。约 2.2% 改善未达到冻结规则的 5%，因此回滚。没有降低门槛来制造更新。
- K3 首次合法提案：模型返回 `k3`，9.605 秒，707 输入 + 247 输出 token。后续真实目标适配中，两候选共 3 次调用、3,449 token；最终保留初始产物。

证据入口：`evidence/native/`、`evidence/gpu/`、`evidence/protocol/source_random/`、`evidence/llm/kimi_k3/`。原始大轨迹和完整运行目录保留在本机 `runs/`。CPU 与 native 环境均通过 65 项测试。两个本体的上抛/主动松夹四个物理反例均未误判成功。

实际命令：

```bash
UV_CACHE_DIR=/code/rosclaw/physicalEvoBench/.cache/uv uv sync --locked --extra dev --project third_party/IsaacLab-Arena
# 这里仅复用下载缓存；cold checkout 可用自己的缓存。旧项目不是运行依赖。
ACCEPT_EULA=Y PEBX_GPU=0 scripts/run_native.sh doctor --sim --embodiment franka_panda
ACCEPT_EULA=Y PEBX_GPU=0 scripts/run_native.sh doctor --sim --embodiment franka_robotiq
ACCEPT_EULA=Y PEBX_GPU=1 scripts/run_native.sh smoke --embodiment franka_panda --episodes 10 --output runs/nominal-panda-v1
ACCEPT_EULA=Y PEBX_GPU=0 scripts/run_native.sh smoke --embodiment franka_robotiq --episodes 10 --output runs/nominal-robotiq-v1
ACCEPT_EULA=Y PEBX_GPU=1 scripts/run_native.sh acquire --embodiment franka_panda --seed 0 --output runs/source-panda-random-dev-001
.venv312/bin/pebx reconstruct --run-dir runs/source-panda-random-dev-001
```

这些输出目录已经存在，复现时必须换新目录，不能覆盖证据。复现环境和修正记录见 [原生运行环境](native_runtime.md)，模型配置见 [Kimi K3](kimi_k3.md)。

发现并保留的问题：最初 Panda 默认准备姿态越界、默认 HDF5 路径的并行锁冲突、标定报告的 NumPy 布尔序列化错误、低层动态改质量诊断不一致。它们均保留原始失败日志；最终名义验证使用统一固定的开发配置。Panda/Robotiq 的低抓取高度下降受阻；Robotiq 还在最低净空与最长等待处失败。下降受阻与桌面几何干涉一致，具体接触机理仍需诊断。不能把全部参数范围当作已验证可行。

下一步：审查已完成的双本体敏感性测量并确定共同可行范围 → 冻结独立分布/私有 split 和全部版本 → 完整源审计及 0/5/20 fresh target 配对实验 → 双向多种子 pilot → 完整统计、成本与复现验收。当前所有开发结果 `formal_result_eligible=false`。原生 `uv pip check` 的 7 个元数据例外已保留并逐项对照上游锁/覆盖配置；当前物理路径通过不等于全部可选功能通过，正式例外审查标记仍为未完成。
