# Implementation status · 2026-09-23

本轮范围：Phase 0 本地工程化 + Phase 1 官方参考输入纵向闭环。不是完整产品验收，也不等于真实建筑验证。

## DONE

- 通读商业计划书文字/表格、原始交付与活动代码，输出 CURRENT_STATE_AUDIT.md、来源清单和模块去向。原文件未改。
- 独立修订目录、本地 Git main/dev/feature 分支、AGENTS.md、Repo Skill、数据真实性规则与 OpenAPI/Pydantic 契约。
- 历史静态结果隔离到 fixtures/demo；旧 Three.js、Agent、材料、优化与研究源码保留，未冒充活动服务。
- FastAPI + SQLite 项目、建筑声明、资料上传、Evidence Manifest、人工复核与历史版本、Evidence Gate、持久队列。
- 真实 EnergyPlus 9.0.1、原生 SQL、独立 run_id、完整输入快照及 provenance、同项目三方案比较。
- 哈希损坏、区域不匹配、未确认、跨项目串用、输入/代码失效、面积冲突时拒绝确定结果；缺失值保持 null。
- 前端真实 API 流程、运行级依赖追溯、同一核验快照 JSON/HTML/PDF、原始证据 ZIP、未签署证书草稿。
- 最新验证：61 后端测试、6 subtests、11 前端测试、33 项真实 API Golden Path 检查、lint/build/schema export 通过。
- 真实负例：EnergyPlus 成功但 SQL 面积与声明冲突，API 仍 failed 且无数值。证据撤回导致 baseline stale，R1 保持有效。
- 独立复算工具实际运行：重新调用相同引擎，R1 能耗匹配误差小于 0.01 kWh。
- CI 三份工作流、Docker Compose 配置及后续 Issue 清单已落地；Compose 只通过配置解析。

## IN PROGRESS

- 整体产品仍在分阶段集成中；Phase 1 的真实建筑适用性和跨电脑验收尚待外部资料与环境。
- GitHub 发布工作仅在本地准备完毕，不能算远程完成。

## BLOCKED

- GitHub 协作者 push 权限已生效，但连接器实际 create_file / create_issue 返回 403 `Resource not accessible by integration`；本机没有可用 Git 凭据。未推送、未创建 PR/Issues、未运行远程 CI。
- 阿里云尚无实例连接/域名配置；本机 Docker daemon 未启动，未部署或验证容器。
- 尚无获授权的真实建筑模型、图纸、账单及实测资料；公开参考模型不替代现场验证。
- 未配置 LLM Provider 凭据；当前不声称存在真正的 Agent Tool Calling。

## NEXT

1. 通用 Claim DAG 与节点级依赖版本：碳因子变化只重算碳节点，避免当前整份后端代码哈希触发保守失效。
2. Agent 工具注册、受控执行、一个真实 Provider，先贯通证据准入与拒答。
3. 基于真实仿真的有限域反例搜索、覆盖与预算记录、补证成本和决策价值排序。
4. Drawing Intelligence 最小闭环：候选识别/缺口/人工确认 -> Building Schema -> 确定性几何与空间证据。
5. 真实建筑 Golden Path、第二台电脑复算；解除 GitHub/云环境阻塞后完成 PR/CI/部署验收。

详见 ROUND1_DELIVERY.md；任何后续阶段未经测试不得改为 DONE。
