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
