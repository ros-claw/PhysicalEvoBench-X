# 新几何任务：真实源学习与零预算迁移

状态 `GEOMETRY_LEARNING_TRACE_AUDIT_PASSED`；36 次真实调用，108 个评分重算；`formal_result_eligible=false`。

本包是看到两个源学习回滚后选择的高度覆盖诊断；使用全新条件，按原接受规则选择，不与原两种方法直接排名。
Panda→Robotiq；1 个提案器包，各一个源学习 seed。每组 20 回合源练习，四个源审计配对、四个目标配对；目标适配 0 回合。即使源回滚，两侧仍实际执行，成本全部保留。

| 提案器 | 源验证接受 | 原因 | 源验证 Before→候选 | 独立源审计 Before→After | 目标 Before→After | 目标收益/退化条件数 |
|---|---|---|---|---|---|---|
| height | True | success | 2/4 → 4/4 | 2/4 → 4/4 | 0/4 → 2/4 | 2 / 0 |

上述四个配对条件仅作开发描述，不给显著性或总体效果结论。源审计与目标成绩不参与更新或回滚。

| 提案器 | 阶段 | 条件层 | Before | After |
|---|---|---|---|---|
| height | source_audit | tall_narrow | 0/2 | 2/2 |
| height | source_audit | wide | 2/2 | 2/2 |
| height | target_zero | tall_narrow | 0/2 | 2/2 |
| height | target_zero | wide | 0/2 | 0/2 |

## 准备状态检查

- height: 全字段精确一致 17/22；其余已观测最大数值差 {'.observation.joint_positions': 1.1408701539039612e-08, '.observation.joint_velocities': 1.2036878018761854e-06, '.observation.tcp_pose_w.position_m': 1.1548399925231934e-07, '.observation.tcp_pose_w.quaternion_xyzw': 1.73225998878479e-07}。未事后引入容差将这些标成精确一致，未改变成绩或源产物。

## 真实模型调用与成本

- height: 0 次模型请求，0 个有效输出，0 个错误请求；provider usage {'completion_tokens': 0, 'prompt_tokens': 0, 'total_tokens': 0}，缺少 usage 的请求 0；实际响应模型 []。

物理累计观察仿真时间 558.00 s；累计回合壁钟 2398.20 s（建场景至结果捕获，不含 teardown；模型耗时另列）。

精确条件与大型原始逐步状态留在本机运行目录，不提交私有目标 manifest。公开 CSV 保留每次真实执行、失败、安全停止、两采样频率及旧评分；source projection、模型调用、源冻结及只读重建证据可检查。
完整时段轨迹不表示首次成功后始终稳定。新任务显式使用候选判据，不替换旧默认或重新标记旧成绩。
本批没有无反馈提案消融，模型先验、搜索与反馈的贡献没有单独分离。完整观察成本不因首次成功而提前停止，不能从完成时间差直接声称仿真成本节省。
条件层在看到校准后选定；只检验全局五维参数，尚未验证条件技能、反向、多 seed 或目标适配预算。
