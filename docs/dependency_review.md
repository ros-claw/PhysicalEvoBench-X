# 原生依赖元数据审查（2026-10-23）

结论：仅对本项目的 **state observation + differential IK + PhysX** 路径接受下列已知元数据例外。保留 Arena 原始 `uv.lock` 和覆盖声明，不修改上游，不声称 `uv pip check` 全部通过。此审查不能证明所有可选组件兼容。

| 冲突 | 安装/锁定状态与依据 | 适用范围与处理 |
|---|---|---|
| openpi-client 要求 numpy<2 | Arena `override-dependencies` 明确固定 numpy 2.3.1，Isaac Sim 核心要求该版本 | 不调用 OpenPI 客户端；公开 NumPy 状态读取、控制数学与轨迹写入已有实际物理证据 |
| simready-search 要求 requests>=2.32.5 | 上游明确固定 2.32.3；pyproject 注释说明与 Isaac Sim HTTP 依赖的冲突 | 本 track 不使用 SimReady 搜索；实际资产加载已完成 |
| simready-search 要求 boto3==1.42.58 | 上游明确固定 1.40.61，注释说明其 AWS 依赖组合 | 本 track 不使用 SimReady 搜索或 AWS 客户端 |
| isaacsim-core 要求 newton==1.5.0 | 上游明确覆盖为 1.5.2 | 本 track 后端为 PhysX；不声称 Newton 通过 |
| isaacsim-kernel 要求 websockets<15 | 上游明确固定 16.1.1，并说明 teleop/cloudxr 的依赖冲突 | 不使用 WebSocket、CloudXR 或远程遥操作；离线仿真启动通过 |
| ovphysx 要求 packaging<24 | 上游明确固定 26.0 | 两本体的 PhysX 初始化、质量/惯性读回、受控冲量和实际任务执行通过 |
| isaacsim-robot 要求 onnxruntime-gpu==1.26.0 | 上游锁文件选用 onnxruntime 1.26.0（CPU），并未安装 GPU 分发包 | 本 track 不运行 ONNX 推理；Kimi 使用独立 HTTP 服务，不以 CPU ONNX 冒充 GPU ONNX |

支持证据：`evidence/native/package_check.log`、上游 pyproject/uv.lock 固定 SHA，以及 `evidence/gpu/` 中双本体 reset、标定、名义任务和 dynamics 验收。接受例外的依据是锁定配置和已执行的具体路径，不是对未测试组件的兼容性推断。

重新安装、包版本/覆盖声明变动、切换 Newton、启用 OpenPI/ONNX/遥操作/资产搜索时，必须重新审查；不能继承此范围限定的结论。远程 Kimi 不提供不可变权重 revision，需继续记录每次响应的模型 ID 与调用时间。

资产依赖另行审查。USD 依赖遍历中的未解析项必须显式记录；不能仅凭两个顶层 USD 的校验和宣称全部资产已冻结。
