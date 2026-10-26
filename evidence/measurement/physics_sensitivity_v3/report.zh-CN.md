# 物理步长与求解器敏感性 v3：实际结果

状态：`NATIVE_CANDIDATE_DIAGNOSTICS_PASSED`；`formal_result_eligible=false`。

配置探针 8/8 通过；完整任务 36/36 通过。
候选观察频率分类分歧 0，成功完成时间最大差 0.0150 s。

| 本体 | 场景 | 配置 | 验证 | 候选 50 Hz | 候选 200 Hz | 旧原生判据 |
|---|---|---|---|---|---|---|
| franka_panda | nominal | half_physics_step | 通过 | 成功 | 成功 | 成功 |
| franka_panda | nominal | double_position_iterations | 通过 | 成功 | 成功 | 成功 |
| franka_panda | nominal | double_velocity_iterations | 通过 | 成功 | 成功 | 成功 |
| franka_panda | nominal | baseline | 通过 | 成功 | 成功 | 成功 |
| franka_panda | toss | double_position_iterations | 通过 | 失败 | 失败 | 失败 |
| franka_panda | toss | double_velocity_iterations | 通过 | 失败 | 失败 | 失败 |
| franka_panda | toss | baseline | 通过 | 失败 | 失败 | 失败 |
| franka_panda | toss | half_physics_step | 通过 | 失败 | 失败 | 失败 |
| franka_panda | release | double_velocity_iterations | 通过 | 失败 | 失败 | 失败 |
| franka_panda | release | baseline | 通过 | 失败 | 失败 | 失败 |
| franka_panda | release | half_physics_step | 通过 | 失败 | 失败 | 失败 |
| franka_panda | release | double_position_iterations | 通过 | 失败 | 失败 | 失败 |
| franka_panda | oscillate | baseline | 通过 | 失败 | 失败 | 失败 |
| franka_panda | oscillate | half_physics_step | 通过 | 失败 | 失败 | 失败 |
| franka_panda | oscillate | double_position_iterations | 通过 | 失败 | 失败 | 失败 |
| franka_panda | oscillate | double_velocity_iterations | 通过 | 失败 | 失败 | 失败 |
| franka_robotiq | nominal | half_physics_step | 通过 | 成功 | 成功 | 成功 |
| franka_robotiq | nominal | double_position_iterations | 通过 | 成功 | 成功 | 成功 |
| franka_robotiq | nominal | double_velocity_iterations | 通过 | 成功 | 成功 | 成功 |
| franka_robotiq | nominal | baseline | 通过 | 成功 | 成功 | 成功 |
| franka_robotiq | toss | double_position_iterations | 通过 | 失败 | 失败 | 失败 |
| franka_robotiq | toss | double_velocity_iterations | 通过 | 失败 | 失败 | 失败 |
| franka_robotiq | toss | baseline | 通过 | 失败 | 失败 | 失败 |
| franka_robotiq | toss | half_physics_step | 通过 | 失败 | 失败 | 失败 |
| franka_robotiq | release | double_velocity_iterations | 通过 | 失败 | 失败 | 失败 |
| franka_robotiq | release | baseline | 通过 | 失败 | 失败 | 失败 |
| franka_robotiq | release | half_physics_step | 通过 | 失败 | 失败 | 失败 |
| franka_robotiq | release | double_position_iterations | 通过 | 失败 | 失败 | 失败 |
| franka_robotiq | oscillate | baseline | 通过 | 失败 | 失败 | 失败 |
| franka_robotiq | oscillate | half_physics_step | 通过 | 失败 | 失败 | 失败 |
| franka_robotiq | oscillate | double_position_iterations | 通过 | 失败 | 失败 | 失败 |
| franka_robotiq | oscillate | double_velocity_iterations | 通过 | 失败 | 失败 | 失败 |
| franka_robotiq | development_disagreement | half_physics_step | 通过 | 成功 | 成功 | 成功 |
| franka_robotiq | development_disagreement | double_position_iterations | 通过 | 成功 | 成功 | 失败 |
| franka_robotiq | development_disagreement | double_velocity_iterations | 通过 | 成功 | 成功 | 成功 |
| franka_robotiq | development_disagreement | baseline | 通过 | 成功 | 成功 | 失败 |

全部结果均保留，配置探针没有任务成功成绩。改变物理参数可能改变真实轨迹，不将全部差异归咎于判据。
固定控制与事后选定开发病例不能估计总体效果，测量变更不能解释为学习收益。
场景读回仅认证 USD 求解器设置。观察固定为 200 Hz，未记录更细 400 Hz 物理步长的全部中间状态。
候选尚未采用为默认 judge，也未冻结新的正式 benchmark。v0.1 的成绩保持原定义。
