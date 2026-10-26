# 实施状态与验收记录

## 最新进展：2026-10-26

后续推进：全新公开源码 checkout 与新原生虚拟环境已实际安装，v0.1 的 93 项 CPU 测试及双本体各一个名义回合通过；轨迹评分离线重算一致，483 项资产/新包资源核验通过，七项依赖例外保留。共享缓存与同机限制、首次零物理调用的失败预检查均已归档，见 [全新依赖安装复现](fresh_native_reproduction_v1.md)。测量开发分支当前 121 项 CPU 测试在两个环境通过。另已预声明并启动 [物理步长/求解器敏感性 v3](physics_sensitivity_v3.md)：8 配置探针 + 36 完整任务，前者全部通过，完整矩阵仍在执行；未提前宣称整体稳定。

隔离测量分支已实现候选判据、截断感知重放、原生全时段双频观察与离线重算。新增 11 次原生调用：8 个正反例通过，首次 9 回合整批因未复现选定病例分歧而失败并保留；随后预声明的 2 回合准备动作配对符合预期，原准备动作下 775 步四组数组与原轨迹逐项完全相同。测量分歧与准备动作敏感性仅在该选定病例上成立，不作学习收益结论。CPU 两环境各 110 项通过。完整结果和限制见 [本次测量进展](measurement_progress_20261026.md)。候选未替换默认 judge，未冻结新正式版本。

独立开发干预 144/144 回合完成，重算匹配，无基础设施失败或未决调用；12 对零差重复的 NPZ 数组全部逐项相等。两个本体的 Initial、Kimi/Random 完整产物均为 6/6；仅 Robotiq 的恢复抓取高度配置为 5/6，其余配置均 6/6。本批没有复现 Panda 的原负差，不能确定单一参数归因。详见 [完整干预结论](intervention_results_20261026.md)。下一阶段采用独立 v0.2 工作树验证姿态轨迹候选评分；v0.1 冻结输入与原始结果保留。

## 诊断推进与解释修正：2026-10-25

已完成两个原生状态探针及 400 回合历史轨迹的事后分析。API 速度与直接 PhysX 速度一致，自由飞行角速度校准约 0.2 rad/s；但接触约束下原生角速度与姿态差分显著不同。因此旧负迁移结果限定为冻结成功判据上的负差，不能直接声称物体持续宏观旋转或物理技能退化；完整协议审计不认证这一物理解释。详见 [状态语义核查](state_semantics_20261025.md)。

参数干预设计已在 GPU 执行前提交：6 个独立开发条件、两个本体、12 个固定配置、144 回合。首次批次因发现上述问题中断，保留 9 次完整调用和 2 个未决调用；不自动重放未决调用。独立重跑目录 `runs/parameter-interventions-v1b-20261025/` 使用完全相同的条件、配置及顺序，旧成本单列，不调用 LLM、不改变原 pilot。CPU 与原生环境均通过 93 项测试。所有新诊断 `formal_result_eligible=false`。

## 最新状态：2026-10-25

P6：`EXPERIMENT_COMPLETE`。冻结 pilot 12/12 包完成，3,390 次真实物理执行，2,250 次等价别名，完整冻结审计通过并已重新核对；没有未决调用。10 个源 run 回滚、2 个接受更新；未观察到正的目标成功率迁移，Kimi Robotiq→Panda seed 0 为负迁移。研究状态仍为 `INCONCLUSIVE`，不据三个 seed 宣称总体显著性。已归档 [最终 pilot 报告](../evidence/pilot_v0.1/report.zh-CN.md)。P7 尚需固定抽样可视化、独立安装/机器复现及发布审查，未创建 release tag。后续顺序见 [推进计划](next_steps_20261025.md)。下文保留历史记录。

## 续跑进展：2026-10-24

已完成 5/12 个完整学习包，仍在 GPU 0/1 运行其余包。新增完成包工具已核验 1,675 次真实物理调用的配对、轨迹、重建和成本，自动检查进程会继续记录后续完成包。当前已完成结果包含零迁移和 Kimi Robotiq→Panda seed 0 的负迁移（预算 0/5/20 均 −10 个百分点），不能提前概括总体结论。干净项目源码、共享固定原生运行环境的双本体单回合 smoke 已通过；CPU 测试 87 项通过。正式全矩阵审计、独立安装复现与发布尚未完成。详见 [本次进展](pilot_progress_20261024.md)。

## 最新核对：2026-10-24

最终 11 个 GPU 验收子任务通过，各本体 100 回合吞吐完成，已生成冻结清单。完整 pilot 曾因磁盘守卫停止，审查时 12 包中 0 包完整，研究结论仍为 `INCONCLUSIVE`。已核对 776 个文件哈希并离线重放 208 回合评分，84 项 CPU 测试通过。Robotiq 随机源学习 seed 0 在四条件验证中由 2/4 到 4/4，接受更新；独立源审计与反向迁移尚未完成。Panda 源学习回滚，已完成预算 0 的目标单元差值为 0。不能声称已证明正迁移。

已迁移本批数据并恢复 GPU 0/1 的冻结矩阵续跑，完整审计与报告将于全部包完成后执行；恢复运行不代表完成。实时状态见 `runs/complete-v2-20261023/pipeline_status.json`。磁盘中断与迁移、证据和科学限制详见 [本次审查](benchmark_review_20261024.md)。下文保留各阶段的历史状态，不作为最新完成声明。

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

## 2026-10-23 后续实施

已完成请求轨迹/实际跟踪诊断，确认 v1 的阶段边界参考跳变；新增显式版本 `grasp_lift_state_v2`，保留旧分支和旧产物重建。提案器不得更换控制器。新增实测 TCP/关节位置硬约束、完整包源码与 YAML 的运行期变动检查。详见 `docs/controller_v2.md`。历史 v1 标定和名义成功记录没有重新标为 v2 验收。

共同范围候选已预先列出 23 个开发检查：15 个单参数低中高和 8 个组合物理边界压力条件。v1 的初次范围批次因发现控制器问题而主动中断，所有部分结果保留在 `runs/`；v2 双本体批次正在执行，未提前宣称通过。

依赖元数据审查记录在 `docs/dependency_review.md` 和 `evidence/native/dependency_review.json`；结论仅覆盖 state/IK/PhysX。资产清单 `evidence/native/asset_inventory_complete.json` 覆盖 483 个文件，包含完整运行时材质库；USD 遍历无未覆盖引用。它不是渲染器 resolver 的逐调用追踪。锁文件采用这些审查结论前仍保持冻结阻断。

双向矩阵脚本、私有条件、阶段 checkpoint、物理/提案 journal、随机状态恢复和锁已实现。完整默认计划是 12 个独立学习包、5,640 个逻辑回合，**计划不等于已执行结果**。正常已完成阶段可续跑；不确定的在途调用停止而不静默重试。CPU 测试已覆盖完整预算/alias/续跑链，当前 73 项通过，未代替 GPU 验收。操作见 `docs/pilot_execution.md`。

正式冻结和 pilot 仍未通过；只读缺口清单在 `evidence/freeze_readiness.json`。继续完成范围检查、最终配置/依赖采用、匹配最终代码 hash 的 GPU 验收，再启动完整矩阵。

### 最终门控流水线（2026-10-23）

首轮 v2 范围结果：Panda 21/23、Robotiq 23/23。所有测点到达任务条件或抬升参考终点，参考速度均有界；不是连续空间安全证明，不是正式性能结果。新范围已在两个 learner 与 schema 中统一，旧 v1 范围仅用于历史产物。

最终配置显式设置 articulation root 与 rigid links 的 64/4 solver。两个本体各一次真实名义检查成功，原生读回了完整关节限位/驱动增益；见 `evidence/gpu/effective_embodiment_parameters_v2.json`。这些单次检查不替代新一轮完整验收，旧 46 回合不改标。

依赖/资产审查已采用到锁文件。配置以 `development_validation_mode=evidence_gate` 预声明验收路径，保持源配置 `development_validated=false`；只有真实新验收通过后，冻结器生成派生的验证通过清单。当前缺口清单仍为 NOT_READY，不发布提前通过的冻结或 tag。

CLI 已补齐 `evaluate`、完整流水线 `run`、中英文 `report`（可选 SVG/PDF 图）。矩阵、私有 split、fresh proposer、真实别名、完整成本、随机状态恢复、原始证据 hash 和独立审计均实现。测试还覆盖一侧 infra 时另一侧原尝试不进入成功率、但成本完整保留的情形。当前 CPU 测试 84 项；阶段功能实现不等于正式矩阵已测完。

完整流水线顺序：11 组最终 GPU 验收（含双本体各 23 点重测）→ 独立开发条件上的真实 source/target/0/5/20 配对 smoke → 各本体 100 回合吞吐/P95 → 冻结 → 两个 learner、两方向、三完整 seed、每格 50 配对条件 → 独立审计与中英文报告、可再生成图表。默认未去重正式配额 5,640 回合，按别名减少真实执行。发布 tag 前仍需完成最终结果审查、清洁 checkout 复现和固定采样可视化。

流水线已实际启动于 `runs/complete-v2-20261023/`，使用 GPU 0/1。启动时阶段为 `GPU_ACCEPTANCE_RUNNING`，两个名义验收子进程已运行；这不是正式 pilot 已完成的声明。实时状态在该目录的 `pipeline_status.json`，总日志为同级 `runs/complete-v2-20261023.log`。该监督进程独立于聊天会话，验收失败会停止后续正式启动；通过后依序运行 smoke、吞吐、冻结与完整矩阵。代码 `6957b63`、清洁源码验证 `01a6c36` 对应的 GitHub CPU CI 均已成功。
