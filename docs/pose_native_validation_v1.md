# 姿态轨迹候选：原生对照 v1

本设计在原生执行前提交。仅为开发测量验证，`formal_result_eligible=false`；不更新旧 pilot、不进行源学习、不调用模型，也不产生迁移成绩。

每个本体执行名义保持、20 N 单控制周期上抛、抬升后主动打开夹爪，以及抬升后持续 8 mm / 4 Hz 水平往复运动。Robotiq 另执行已完成开发干预中唯一的原判据失败条件，检验已知分歧能否在完整时长执行中再次观察到。后一条件经过事后选择，不能用于估计总体分歧概率。

共 9 个独立原生场景，0.005 秒物理步长、0.02 秒控制周期、0.5 秒准备加 15 秒任务观察；提前成功不停止诊断，实测硬约束仍立即终止。每次完整保存 50 Hz 控制状态与 200 Hz 物理状态，并行计算旧判据和候选判据的首次终止。候选两观测频率须分类一致，成功完成时间相差不超过 25 ms。预期名义保持通过，抛掷、释放和持续运动不通过。运动反例必须确实产生离桌抬升；释放需实测打开至少 60 mm，持续运动需在触发至少一秒后仍测得超过 0.03 m/s 的高处物体路径速度。反例未生效属于验证未通过，不能宣称候选正确拒绝。

计划文件记录固定条件、技能、源码/配置 hash、提交和来源开发轨迹 hash；在启动 GPU 前归档并提交。每个调用有持久 journal，不自动重跑 STARTED 调用；异常保留完整日志与未知成本。修改工具或判据须建立新计划，旧调用继续保留。

该工作树显式复用原项目的固定原生 Python 安装和资产，不能冒充独立安装复现。此批只能检验上述有限反例与观测频率一致性，不能认证采样间运动，也不替代物理时间步长、求解器敏感性或更广泛构念验证。

启动方式（目录须尚不存在，原生解释器路径须保留虚拟环境符号链接）：

```bash
PYTHONPATH="$PWD/src" /code/rosclaw/physicalEvoBench_X/.venv312/bin/python tools/validate_pose_native.py plan --study "$PWD/runs/pose-native-v1-20261026" --source-study /code/rosclaw/physicalEvoBench_X/runs/parameter-interventions-v1b-20261025
# 先归档并提交 plan.json，再运行。
ACCEPT_EULA=Y PYTHONPATH="$PWD/src" /code/rosclaw/physicalEvoBench_X/.venv312/bin/python tools/validate_pose_native.py run --study "$PWD/runs/pose-native-v1-20261026" --native-python /code/rosclaw/physicalEvoBench_X/third_party/IsaacLab-Arena/.venv/bin/python --gpus 0 1
```
