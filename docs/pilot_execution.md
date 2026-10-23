# 双向矩阵与续跑

`scripts/pilot_suite.py` 将两种 learner、两个源本体和三个完整学习 seed 展开为 12 个 package。每个 package 先获得一次 20 回合源经验，再做 50 条件源审计，以及目标预算 0/5/20 的独立适配和各 50 条件配对评测。未去重为 5,640 个逻辑回合；别名规则决定实际执行数。

当前命令默认属于开发矩阵。正式实验需要先通过 `pebx freeze`，再将真实冻结清单传给 `plan --freeze ...`；存在冻结清单本身也不会自动授予正式结果资格。

```bash
.venv312/bin/python scripts/pilot_suite.py plan --output runs/matrix-NEW
# 工程检查可用 --seeds 1 --test-count 10 --learner random_search_v1，仍非正式 pilot。
env ACCEPT_EULA=Y OMNI_KIT_ACCEPT_EULA=YES HEADLESS=1 CUDA_VISIBLE_DEVICES=0 \
  ISAACLAB_ARENA_FORCE_EXIT_ON_COMPLETE=1 PYTHONUNBUFFERED=1 \
  third_party/IsaacLab-Arena/.venv/bin/python scripts/pilot_suite.py worker \
  --suite runs/matrix-NEW --package random_search_v1/franka_panda/seed-0
.venv312/bin/python scripts/summarize_pilot.py --suite runs/matrix-NEW
```

每个 worker 必须独占自己的 package；文件锁阻止同时启动两个 worker。不同 package 可由不同 GPU 执行。不要中断或修改共享机器上的其他用户进程。正式运行前要测量吞吐，不能把逻辑配额当成实际执行记录。

`plan.json` 固定执行代码/配置 hash，私有条件以 0700 目录、0600 文件保存。条件不会传给 proposer。所有预算均创建 fresh proposer；同一 package 的 Before/After 共享配对条件与提案 RNG。源回滚时 After 整次适配 alias Before，增益严格为零。不同 package 不做结果缓存。

正常中断后，用同一个 worker 命令继续：完整 stage 会校验产物和轨迹后复用；部分 stage 重建到新 attempt 目录，按 journal 重放已完成的物理结果和提案响应，并恢复随机提案器 RNG。模型服务不会因为重放而再次收费。旧 attempt 保留，主账本仅按 journal 中真实物理调用计一次。

断电/强杀可能发生在物理执行后、结果落盘前。此时 `STARTED` journal 会阻止自动重跑，防止重复物理成本被悄悄隐藏。应先根据轨迹与错误记录核对该调用；不能直接删除 journal 或把它算作零成本。正常返回的基础设施失败仍经过协议重试规则，旧尝试不删除。

报告同时列出全部独立 run 点、各方向各预算的均值和范围、源端接受/回滚、失败原因、别名及物理/模型成本。未完成 package 单列，不填补为零增益。没有从三个 run 推导强显著性结论。当前外部模型与 evaluator 共机，仅提供进程内 allowlist，不能宣称恶意代码的强隔离。

完整门控流水线入口：

```bash
ACCEPT_EULA=Y .venv312/bin/python scripts/complete_pipeline.py \
  --config configs/tasks/stable_lift_dev.yaml --output runs/complete-v2-NEW --gpus 0 1
```

该命令按顺序执行：11 组最终版本 GPU 验收 → 每本体 100 个真实开发回合的吞吐/中位数/P95 → 冻结 → Random 与 Kimi 两方向三种子、0/5/20 和 50 配对条件 → 独立审计。它不会为了正迁移修改参数、选 donor 或删除失败。任一验收失败会阻止正式启动，现有验收目录和冻结输出不会覆盖。

读取 `runs/complete-v2-NEW/pipeline_status.json` 查看当前阶段。只有独立审计通过时，最终报告才会给出受限于可信内部 learner 的 `formal_result_eligible=true`；开发矩阵禁止事后改标签成为正式 pilot。该结果不声称支持恶意外部参赛代码的强隔离。

运行可能持续数日；`pilot_timing_estimate.json` 只在每本体 100 回合实测完成后生成，估计单列应用启动、模型延迟、基础设施故障和共享 GPU 负载变化的影响。这里没有以名义成功或 CPU 通过代替实测吞吐。

如果主监督进程中断，先检查状态和仍存活的 worker；不要同时启动第二个同 package 的 worker。pilot 阶段可以直接对已有 `pilot/` 目录运行 `run_suite.py --suite ... --gpus 0 1` 接续。未完成的物理调用仍需先核对，不能删除在途标记。低于 2 GiB 可用磁盘时，在下一个真实物理调用开始前停止；不清理共享目录。

报告分开记录 episode wall time、原生子进程完整墙钟（含应用启动/退出）、模型调用与 token。选中 GPU 的进程时间只是共享 GPU 上的分配区间，不能解释为独占 GPU 计算用量。历史开发、标定和本次正式 pilot 的成本分别列出，不把某一组账本称为整个项目的全部资源支出。

发布 tag 前仍要做最终结果审查、清洁 checkout 的复现 smoke，以及固定采样的可视化证据；流水线不会在后台自动创建发布 tag。
