# 开发分布校准 v1：完整实际结果

完成 30/30 次真实 PhysX 调用；离线审计 `CALIBRATION_TRACE_AUDIT_PASSED`；`formal_result_eligible=false`。

候选 50/200 Hz 分类分歧 0；细高条件六对重复轨迹全部精确一致：True。

| 本体 | 条件 | 技能 | 候选 50 Hz | 候选 200 Hz | 旧判据 | 最大抬升 m |
|---|---|---|---|---|---|---|
| franka_panda | nominal | initial | 成功 | 成功 | 成功 | 0.1180 |
| franka_panda | nominal | high_grasp | 成功 | 成功 | 成功 | 0.1181 |
| franka_panda | nominal | slow_lift | 成功 | 成功 | 成功 | 0.1180 |
| franka_panda | tall_narrow | high_grasp | 成功 | 成功 | 成功 | 0.1180 |
| franka_panda | tall_narrow | slow_lift | 失败 | 失败 | 失败 | 0.0009 |
| franka_panda | tall_narrow | initial | 失败 | 失败 | 失败 | 0.0009 |
| franka_panda | wide | slow_lift | 成功 | 成功 | 成功 | 0.1180 |
| franka_panda | wide | initial | 成功 | 成功 | 成功 | 0.1180 |
| franka_panda | wide | high_grasp | 成功 | 成功 | 成功 | 0.1180 |
| franka_panda | heavy_low_friction | initial | 成功 | 成功 | 成功 | 0.1137 |
| franka_panda | heavy_low_friction | high_grasp | 成功 | 成功 | 成功 | 0.1136 |
| franka_panda | heavy_low_friction | slow_lift | 成功 | 成功 | 成功 | 0.1137 |
| franka_panda | tall_narrow (重复) | initial | 失败 | 失败 | 失败 | 0.0009 |
| franka_panda | tall_narrow (重复) | high_grasp | 成功 | 成功 | 成功 | 0.1180 |
| franka_panda | tall_narrow (重复) | slow_lift | 失败 | 失败 | 失败 | 0.0009 |
| franka_robotiq | nominal | initial | 成功 | 成功 | 成功 | 0.1139 |
| franka_robotiq | nominal | high_grasp | 成功 | 成功 | 成功 | 0.1200 |
| franka_robotiq | nominal | slow_lift | 成功 | 成功 | 成功 | 0.1137 |
| franka_robotiq | tall_narrow | high_grasp | 成功 | 成功 | 成功 | 0.1069 |
| franka_robotiq | tall_narrow | slow_lift | 失败 | 失败 | 失败 | 0.0035 |
| franka_robotiq | tall_narrow | initial | 失败 | 失败 | 失败 | 0.0035 |
| franka_robotiq | wide | slow_lift | 成功 | 成功 | 成功 | 0.1151 |
| franka_robotiq | wide | initial | 成功 | 成功 | 成功 | 0.1150 |
| franka_robotiq | wide | high_grasp | 失败 | 失败 | 失败 | 0.0132 |
| franka_robotiq | heavy_low_friction | initial | 成功 | 成功 | 成功 | 0.1100 |
| franka_robotiq | heavy_low_friction | high_grasp | 成功 | 成功 | 成功 | 0.1147 |
| franka_robotiq | heavy_low_friction | slow_lift | 成功 | 成功 | 成功 | 0.1096 |
| franka_robotiq | tall_narrow (重复) | initial | 失败 | 失败 | 失败 | 0.0035 |
| franka_robotiq | tall_narrow (重复) | high_grasp | 成功 | 成功 | 成功 | 0.1069 |
| franka_robotiq | tall_narrow (重复) | slow_lift | 失败 | 失败 | 失败 | 0.0035 |

## 执行阶段与解释

失败回合不能仅凭分数解释：下面列出其真实阶段及最大抬升。抓取高度同时影响接近和下降目标，不能直接把效果归因于夹持质量。慢抬升参数只有到达 LIFT 后才被消费；未进入 LIFT 的回合不能检验抬升参数敏感性。

- franka_panda / tall_narrow__slow_lift: {'APPROACH': 179, 'DESCEND': 571, 'PREPARE': 25}；最大抬升 0.000934 m。
- franka_panda / tall_narrow__initial: {'APPROACH': 179, 'DESCEND': 571, 'PREPARE': 25}；最大抬升 0.000934 m。
- franka_panda / tall_narrow_repeat__initial: {'APPROACH': 179, 'DESCEND': 571, 'PREPARE': 25}；最大抬升 0.000934 m。
- franka_panda / tall_narrow_repeat__slow_lift: {'APPROACH': 179, 'DESCEND': 571, 'PREPARE': 25}；最大抬升 0.000934 m。
- franka_robotiq / tall_narrow__slow_lift: {'APPROACH': 750, 'PREPARE': 25}；最大抬升 0.003516 m。
- franka_robotiq / tall_narrow__initial: {'APPROACH': 750, 'PREPARE': 25}；最大抬升 0.003516 m。
- franka_robotiq / wide__high_grasp: {'APPROACH': 211, 'DESCEND': 539, 'PREPARE': 25}；最大抬升 0.013231 m。
- franka_robotiq / tall_narrow_repeat__initial: {'APPROACH': 750, 'PREPARE': 25}；最大抬升 0.003516 m。
- franka_robotiq / tall_narrow_repeat__slow_lift: {'APPROACH': 750, 'PREPARE': 25}；最大抬升 0.003516 m。

这些是固定技能的开发比较，不是学习或迁移实验。联合压力条件不能分解各物理因素的因果作用。
候选成功表示首次满足判据；留存完整时段不表示成功后始终稳定。原始轨迹位于运行目录，公开归档包含逐回合结果、计划、哈希和离线重算。
总观察仿真时间 465.00 s；累计回合壁钟（建场景至捕获最终结果，不含 teardown） 2977.18 s（共享 GPU，不作为吞吐基准）。
