# 证据追溯与工作区可靠性优化 2026-09-26

- DONE：修复断线后的自动刷新、旧异步响应与项目绑定、上传重试重复保存，以及搜索参数证据缺少版本快照的问题。详见 [RELIABILITY_UPDATE.md](RELIABILITY_UPDATE.md)。
- DONE：本轮前端 18 项测试、后端 84 项及 6 项子测试、语法/lint/构建/schema 核验通过；真实参考流程 37 项通过，实际 EnergyPlus 调用 6 次。
- LIMITATION：后端 6 项历史原生运行测试因缺少对应目录跳过；1 项 Windows DPAPI 测试受隔离账号限制未通过，已单独记录。浏览器连接不可用，未声称本轮目视复测。
- SCOPE：物理核心、参考输入、比较目标、来源性质和工程复核边界沿用现有实现。

# 调研材料与界面复测 2026-09-24

- DONE：为温工交流重新执行 86 项后端测试及 6 项子测试、13 项前端测试、lint/build/契约导出；真实 Trust 验收 31 项通过。另在隔离 UI 数据库运行三方案及有限搜索，合计本轮 12 次实际 EnergyPlus 调用。
- DONE：浏览器发现并修复 `.app-body` 缺少 `min-height:0` 导致长页面无法滚动、通用 SVG 尺寸覆盖 DAG 连线的两处显示问题。修复后构建、13 项前端测试及浏览器滚动/连线/构件详情复测通过。物理计算代码未变。
- DONE：项目介绍、技术验证资料、温工调研提纲与记录表保存于仓库外 `../outputs/20260924_温工调研资料`，附实际截图、测试日志及参考报告草稿。原始运行保留在 validation。
- BLOCKED / DEFERRED：外部 Provider Key 联网、真实建筑校准、第二台电脑与云部署仍未验收；本轮参考结果不构成工程实测成绩或机构认可。
- NEXT：取得真实业务流程反馈，确认最小资料集、拒答规则和经授权历史项目的对照验收方法。

# Implementation status · Trust / Agent / Spatial 增量

## DONE

- 开发者后台：管理员设置 DeepSeek 模型与 Key；Windows DPAPI 加密，前端不持久化 Key；连接与工具协议测试按钮。
- 节点依赖图、证据版本身份、独立碳因子版本和碳派生记录。真实验收证明因子修改保留能耗/EUI、碳与相关证书失效；只重算碳，原始 run 文件不变。
- 本地/Provider 两种明确模式，受控工具执行、持久时间线、项目隔离、计算授权、轮次/工具预算；LLM 解释与正式指标分离。
- 有来源、离散域、预算与容差的真实 EnergyPlus 反例搜索，原始输出 ZIP；结果区分发现反例、限定预算未发现、完整离散域、并列不确定。
- 条件补证成本候选排序和持久 actionplan；无已发现反例时收益 null，保存进同源证书。
- 图纸证据人工确认 → Building Schema → 简单墙体三维 → 构件证据详情、楼层筛选/X-ray；假设/未知/推断保留。
- 首页八步可控工作流演示，标明非实时仿真；浏览器实际核验开发者入口、本地工具执行、三维及构件详情。

## IN PROGRESS

- 首四项为可运行的限定范围闭环，不是全面优化、任意图纸理解或完整工程数字孪生。当前代码与验收见 TRUST_AGENT_SPATIAL_DELIVERY.md。

## BLOCKED / DEFERRED

- 外部 Provider 联网验收：待管理员在后台填入有效 Key 并点击测试；不在聊天中收取 Key。
- 没有获授权的真实建筑/实测资料，官方参考算例不能替代。
- 服务器、第二台实体电脑与受控部署：用户最新指示暂缓，未尝试连接或部署。
- GitHub app 上轮实际写入 403，未声称远程 CI、PR 或发布成功；本轮本地工作继续。

## NEXT

1. 管理员配置真实 Key，完成真实 Provider 的工具闭环与失败恢复验收。
2. 补充获授权的真实建筑、现场参数和业务目标，做校准及专业复核。
3. 将搜索域扩展到有工程依据的 HVAC / Schedule，接入真实多目标方案优化。
4. 完成图纸识别候选与人工校正、构件到 IDF 对象映射，再做空间 Claim 影响追踪。
5. 用户恢复环境任务后，完成第二台电脑复算、GitHub CI 与受控云部署。

---
以下为上一轮历史状态（不得代替当前增量）：

# Implementation status · 2026-09-23

本轮范围：Phase 0 本地工程化 + Phase 1 官方参考输入纵向闭环。不是完整产品验收，也不等于真实建筑验证。

## DONE

最新增量 DONE：真实注册/登录/退出、HttpOnly 会话、CSRF、项目及下载授权；首个账号接管既有项目。Codex 风格侧栏、中央任务区、独立视图、右侧详情、搜索与明暗主题。最新验证为 70 后端测试、13 前端测试、34 项带认证真实流程；下方保留上一轮历史记录。详见 ACCOUNT_WORKSPACE_UPDATE.md。

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
