# 新几何条件上的真实源学习与零预算迁移 v1

执行前设计，2026-10-26。新任务修订 `DEVELOPMENT_GEOMETRY_LEARNING_V1`，仅为开发实验，`formal_result_eligible=false`。保留旧 v0.1 及既有测量/校准记录的源码、配置、结果定义；不更换默认 judge，不创建新正式 benchmark 或 release。

本批先比较随机搜索与 Kimi 两个真实源学习包，均为 Panda→Robotiq、提案 seed 0。每包严格 20 次源练习（12 探索、8 验证），原有选择和接受规则不变，包括同成功率时的 5% 时间改善门槛。之后冻结实际产物，在四个独立源审计条件和四个独立目标评测条件分别运行 Before/After。目标适配预算为 0；每包 36 次真实调用，共 **72 次**。即使源学习回滚，两侧仍实际执行，作为真实零差检查，无别名或免费缓存。

本阶段验收：72 次调用及全部失败/重复成本可审计；源学习可从日志及留存反馈重建；产物在源审计和目标评测前冻结；训练/验证/审计/目标几何无重叠，两个 learner 使用相同条件；每次 PhysX 质量/惯性/材料、USD 尺寸/放置和 solver 核验；50/200 Hz 全时段轨迹、三套评分完整留存并离线重算；模型仅收到源探索的公开反馈，不能获得审计、目标或上一轮人工干预的结果。**是否接受更新、是否正迁移、哪种方法胜出不作为工程验收条件。**

开发条件生成器固定 seed=2026102604。源训练 2 个、验证 4 个、审计 4 个、目标评测 4 个；每个 split 细高/宽物体各半。细高边长 .034–.036 m、高 .138–.142 m、物体摩擦 1；宽物体边长和高各 .064–.066 m、物体摩擦 .5；质量 .18–.22 kg。均中心放置、yaw=0、物体初始底部距桌面 .002 m，独立 reset seed。精确几何/质量组合不重用之前的校准场景，也不跨 split 重用。原校准数据用于选择开发问题，不进入本批提案器上下文。

本批是看到校准后设计的分层开发分布，不能声称任务发现过程盲测。四个配对条件、一套学习 seed 不支持总体显著性结论；后续反向、多 seed、目标适配预算以及正式独立分布仍需另行完成。当前仅评测全局五维参数，不宣称已实现条件技能。高抓取参照不会作为候选插入、初始值或模型提示。

主成绩为候选姿态路径判据的 50 Hz 首次成功结果，200 Hz 候选及旧判据仅作测量诊断，全部保留。它是新任务显式评分选择，不能据此重标旧实验。保持 .005 s 物理步长、50 Hz 控制、200 Hz 观察、64/4 solver、.5 s 原零相对准备动作与 15 s 任务时段，实测约束可触发提前安全停止。完整时段不表示首次成功后一直稳定。

已有 bounded_llm_v1 配置保持不变：Kimi k3、temperature=1、low effort、输入上限 6000、输出 800，每候选最多生成+修复各一次；真实 usage/error/回退全部记账。模型接口不暴露不可变权重版本，不将 seed 声称为确定性采样。模型不接触目录或精确条件 manifest；密钥从运行环境或显式 0600 本地文件加载，不写入日志和 Git。

所有调用经过不可覆盖 journal。已完成调用可重建 projection；不确定 STARTED 调用停止且保留，不自动重复。原始逐步轨迹和精确条件 manifest 位于忽略的 runs；公开报告仅发布 split hash、条件 ID/stratum、经验参数、实际成绩、成本和证据 hash，不提交私有目标条件。

离线报告还逐项比较相同条件在技能开始前的 .5 s 准备状态及实际动作，分别覆盖探索候选、源验证和两种配对评测。若存在差异则显式报告，不丢弃该回合或事后回滚产物。完整时段观察在首次成功后仍继续收费，因此任务完成时间改善不能直接宣称本批仿真成本节省。本批没有无反馈提案消融，不单独识别模型先验、搜索与物理反馈各自的贡献。

## 执行与复现

干净源码即可生成相同 split 的 canonical hash、初值、预算和执行设置，无需旧 runs。精确条件文件仅写入新运行目录。首次执行前安装 CPU 项目依赖，原生环境按依赖锁与独立安装说明准备；使用虚拟环境路径本身，不解析到系统解释器。

```bash
PYTHONPATH=src /path/to/cpu/python tools/learn_geometry_v1.py plan --study runs/new-geometry-learning
ACCEPT_EULA=Y PYTHONPATH=src /path/to/cpu/python tools/learn_geometry_v1.py run \
  --study runs/new-geometry-learning --gpus 0 1 \
  --native-python /path/to/Arena/.venv/bin/python --credential-file /secure/path/.env
PYTHONPATH=src /path/to/cpu/python tools/audit_geometry_learning_v1.py \
  --study runs/new-geometry-learning --output runs/new-geometry-learning/trace_audit.json \
  --replay-root runs/new-geometry-learning/audit-replay
PYTHONPATH=src /path/to/Arena/.venv/bin/python tools/report_geometry_learning_v1.py \
  --study runs/new-geometry-learning --archive evidence/learning/new-geometry-learning
```

也可在 supervisor 启动后用 `finalize_geometry_learning_v1.py` 的 `--study`、`--archive` 和 `--native-python` 自动等待、审计及导出。输出目录和已有日志拒绝覆盖。审计仅重放已完成 journal，缺失记录时拒绝新增调用。`audit_geometry_learning_v1.py --package random` 可单独检查已完成包，但产生明确的 package 状态，不能替代全批完成声明。恢复 worker 前必须核对原日志及未决调用；手动 worker 的 Kimi 凭证需预设运行环境，不会从父 supervisor 自动恢复。

## 完成结果：2026-10-26

原定两包已完成 72 次物理调用，Random 回滚、Kimi 保留初值，独立源审计均 2/4→2/4，目标均 0/4→0/4。216 个评分重算一致。 每方法仅一个学习 seed、四个目标配对条件，仍为开发诊断。完整结果与限制见 [本轮学习进展](learning_progress_20261026.md)。
