# PhysicalEvoBench-X 实验记录

完成独立学习包 12/12；正式结果资格：True。
源端接受更新 2 次；回滚或无行为变化 10 次。研究状态：INCONCLUSIVE。

| 方法 | 方向 | fresh 目标预算 | 独立 run 数 | Before 成功率 | After 成功率 | 平均配对差 | run 差值范围 |
|---|---|---:|---:|---:|---:|---:|---|
| bounded_llm_v1 | franka_panda → franka_robotiq | 0 | 3 | 0.9733 | 0.9733 | 0.0000 | 0.0000 / 0.0000 |
| bounded_llm_v1 | franka_panda → franka_robotiq | 5 | 3 | 0.9733 | 0.9733 | 0.0000 | 0.0000 / 0.0000 |
| bounded_llm_v1 | franka_panda → franka_robotiq | 20 | 3 | 0.9733 | 0.9733 | 0.0000 | 0.0000 / 0.0000 |
| bounded_llm_v1 | franka_robotiq → franka_panda | 0 | 3 | 1.0000 | 0.9667 | -0.0333 | -0.1000 / 0.0000 |
| bounded_llm_v1 | franka_robotiq → franka_panda | 5 | 3 | 1.0000 | 0.9667 | -0.0333 | -0.1000 / 0.0000 |
| bounded_llm_v1 | franka_robotiq → franka_panda | 20 | 3 | 1.0000 | 0.9667 | -0.0333 | -0.1000 / 0.0000 |
| random_search_v1 | franka_panda → franka_robotiq | 0 | 3 | 0.9733 | 0.9733 | 0.0000 | 0.0000 / 0.0000 |
| random_search_v1 | franka_panda → franka_robotiq | 5 | 3 | 0.9733 | 0.9733 | 0.0000 | 0.0000 / 0.0000 |
| random_search_v1 | franka_panda → franka_robotiq | 20 | 3 | 0.9733 | 0.9733 | 0.0000 | 0.0000 / 0.0000 |
| random_search_v1 | franka_robotiq → franka_panda | 0 | 3 | 1.0000 | 1.0000 | 0.0000 | 0.0000 / 0.0000 |
| random_search_v1 | franka_robotiq → franka_panda | 5 | 3 | 1.0000 | 1.0000 | 0.0000 | 0.0000 / 0.0000 |
| random_search_v1 | franka_robotiq → franka_panda | 20 | 3 | 1.0000 | 1.0000 | 0.0000 | 0.0000 / 0.0000 |

全部 run 点、源审计、失败类型、硬约束、完成时间和物理/模型成本保存在 report.json。未完成包单列，不当作零收益补入。三个 run 仅为 pilot，不据测试回合数量宣称强显著性。开发结果不能事后改标签成为正式实验；当前机器人配置与仿真结果不构成任意真机泛化证明。
