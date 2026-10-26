# 新几何任务：真实源学习与零预算迁移

状态 `GEOMETRY_LEARNING_TRACE_AUDIT_PASSED`；72 次真实调用，216 个评分重算；`formal_result_eligible=false`。

Panda→Robotiq；2 个提案器包，各一个源学习 seed。每组 20 回合源练习，四个源审计配对、四个目标配对；目标适配 0 回合。即使源回滚，两侧仍实际执行，成本全部保留。

| 提案器 | 源验证接受 | 原因 | 源验证 Before→候选 | 独立源审计 Before→After | 目标 Before→After | 目标收益/退化条件数 |
|---|---|---|---|---|---|---|
| random | False | ROLLBACK | 2/4 → 2/4 | 2/4 → 2/4 | 0/4 → 0/4 | 0 / 0 |
| kimi | False | NO_BEHAVIOR_CHANGE | 2/4 → 2/4 | 2/4 → 2/4 | 0/4 → 0/4 | 0 / 0 |

上述四个配对条件仅作开发描述，不给显著性或总体效果结论。源审计与目标成绩不参与更新或回滚。

| 提案器 | 阶段 | 条件层 | Before | After |
|---|---|---|---|---|
| random | source_audit | tall_narrow | 0/2 | 0/2 |
| random | source_audit | wide | 2/2 | 2/2 |
| random | target_zero | tall_narrow | 0/2 | 0/2 |
| random | target_zero | wide | 0/2 | 0/2 |
| kimi | source_audit | tall_narrow | 0/2 | 0/2 |
| kimi | source_audit | wide | 2/2 | 2/2 |
| kimi | target_zero | tall_narrow | 0/2 | 0/2 |
| kimi | target_zero | wide | 0/2 | 0/2 |


random 回滚后的真实同产物配对：8/8 对公开状态/实际动作精确一致。

kimi 回滚后的真实同产物配对：8/8 对公开状态/实际动作精确一致。

## 准备状态检查

- random: 全字段精确一致 17/22；其余已观测最大数值差 {'.observation.joint_velocities': 3.445870788709726e-08}。未事后引入容差将这些标成精确一致，未改变成绩或源产物。
- kimi: 全字段精确一致 17/22；其余已观测最大数值差 {'.observation.joint_velocities': 3.445870788709726e-08}。未事后引入容差将这些标成精确一致，未改变成绩或源产物。

## 真实模型调用与成本

- random: 0 次模型请求，0 个有效输出，0 个错误请求；provider usage {'completion_tokens': 0, 'prompt_tokens': 0, 'total_tokens': 0}，缺少 usage 的请求 0；实际响应模型 []。
- kimi: 5 次模型请求，5 个有效输出，0 个错误请求；provider usage {'completion_tokens': 1339, 'prompt_tokens': 6858, 'total_tokens': 8197}，缺少 usage 的请求 0；实际响应模型 ['k3']。

物理累计观察仿真时间 1116.00 s；累计回合壁钟 8270.22 s（建场景至结果捕获，不含 teardown；模型耗时另列）。

精确条件与大型原始逐步状态留在本机运行目录，不提交私有目标 manifest。公开 CSV 保留每次真实执行、失败、安全停止、两采样频率及旧评分；source projection、模型调用、源冻结及只读重建证据可检查。
完整时段轨迹不表示首次成功后始终稳定。新任务显式使用候选判据，不替换旧默认或重新标记旧成绩。
本批没有无反馈提案消融，模型先验、搜索与反馈的贡献没有单独分离。完整观察成本不因首次成功而提前停止，不能从完成时间差直接声称仿真成本节省。
条件层在看到校准后选定；只检验全局五维参数，尚未验证条件技能、反向、多 seed 或目标适配预算。
