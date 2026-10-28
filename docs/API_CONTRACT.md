# Phase 1 contract v1.0

账号增量：GET /api/auth/status、POST /api/auth/register、POST /api/auth/login 为公开入口；GET /api/auth/me、POST /api/auth/logout 需要会话。除 health 和三个公开账号入口外，所有业务 API 均须 vra_session Cookie；写请求另须 X-CSRF-Token。注册/登录/me 返回 csrf_token，前端只保存在内存。项目及 run/报告/文件下载按账号归属授权，无权限统一 404，未登录 401，CSRF/跨来源 403。OpenAPI 已标注 cookie 和 CSRF security schemes。

权威定义：backend/schema.py；生成件 shared/schemas/openapi.json、building.json、evidence.json、run.json。执行 python scripts/export_contract.py；CI 检查 schema drift。

- POST/GET /api/projects；GET /api/projects/{id}；PUT /api/projects/{id}/building。
- POST /api/projects/{id}/files：multipart file，64 MB 默认（VRA_MAX_UPLOAD_MB 可配置），返回 file_id；GET 对应 file_id 下载源文件。health.upload_policy 公布实际文件上限；天气解析另有 20 MB / 单年限制。上传保留 64 MB 存储余量，登记失败清理本次新文件。
- GET /api/projects/{id}/imports/{import_id}/report.json：下载持久化导入诊断、原始来源哈希和当前来源校验；失败 IFC 逐空间报告不产生部分可采纳模型。项目归属与会话校验同其他业务接口。
- Agent Chat.task：auto / weather / diagnose。weather 固定读取天气工具，AI 说明不产生工程数值；status=partial 表示存在说明或工具失败，tool_status 与 explanation_status 分别报告。
- POST/GET /api/projects/{id}/evidence；PATCH /evidence/{evidence_id} 人工复核；GET /history。
- GET /api/projects/{id}/gate?scheme_id=baseline；GET /api/projects/{id}/runs。
- POST /api/runs；GET /api/runs/{id}、/result、/evidence、/claims、/artifacts。
- GET /api/runs/{id}/report.json、report.html、report.pdf；同源核验视图。
- POST /api/comparisons；明确仅能耗排序、确定推荐为 null。
- POST /api/reference-projects：显式导入官方输入，data_nature=engineering_reference，状态待审，无历史结果。
- GET /api/factor-profiles、/api/health。

证据/建筑修改带 expected_revision；409 拒绝版本冲突、证据不齐或绑定错误；422 拒绝非法 schema；413 超限。来源文件不能通过 API 覆写，复核历史追加保留。
正式 run 结果必须包含完整 provenance。queued/running/failed/stale 的受影响数值为 null。错误不能触发 demo fallback。
建筑声明用于核对；建模工作区可显式生成、复核并发布 IDF 9.0 + SimpleAndTabular 输出。IFC 空间转换已接入，epJSON 转换尚未实现。
API 具备账号会话、项目归属及受限 Token 校验，仍绑定本机；公网部署待验收。材料方案评估已接入；完整工程优化尚未实现。


## Trust / Agent / Spatial 增量

- GET/PUT `/api/developer/provider`：首个账号为管理员；密钥不回传。Windows DPAPI 绑定当前 OS 用户；Linux 使用进程环境变量。POST `/test` 真请求 DeepSeek，不执行返回工具。
- GET `/api/agent/status`；POST `/api/projects/{id}/agent/chat`；GET `/api/projects/{id}/agent/{agent_id}`。mode=local 是确定性工具流程；mode=provider 使用真实 HTTP Adapter。工具白名单、Pydantic 参数、项目隔离、计算授权、轮次预算；工具结果与耗时持久化。LLM 文字不写入结果指标。
- GET/PUT `/api/projects/{id}/carbon-factors`：expected_revision 乐观锁，地区/来源/单位核验。因子只使碳节点失效；run.status 仍表示物理结果状态。
- POST `/api/runs/{id}/recalculate-carbon`：只使用当前有效能耗，新 carbon_id、新因子快照、新 calculator_version；EnergyPlus 调用为 0，原 run 文件不改写。
- GET `/api/projects/{id}/claims`：最新方案的节点与能耗/碳排序依赖。证据节点按 evidence_id+revision 区分，避免不同版本合并。
- GET `/api/projects/{id}/search-materials`；POST/GET `/api/projects/{id}/searches`；GET `/searches/{search_id}`、`/artifacts`；POST `/searches/{search_id}/actions`。
- 搜索：1–2 个共同 Material 对象导热系数轴，各 2–6 个离散值，2–24 次预算，能耗目标，排序容差明确。每点各方案真实仿真，完整点才能比较。NO_FLIP_WITHIN_BUDGET 不等于证明；STABLE_ON_ENUMERATED_GRID 只声明枚举点。输入/搜索代码版本变化使搜索结论 STALE。
- 补证：费用、耗时、获取方法、假设确认值由用户输入；排序为已观察反例的条件排除率/成本，不是风险概率或无偏信息价值估计。无反例时效益 null。actionplan 持久化并进入证书。
- GET/PUT `/api/projects/{id}/geometry`：人工坐标确认→Building Schema→确定性墙体；按证据版本失效。UNKNOWN/AI_SUGGESTED 保留，ASSUMED 不升级为实测。三维与 IDF 尚未映射，affected_claims 保持空。

新增共享 JSON Schema：geometry.json、factor-update.json、search.json；OpenAPI 包含上述全部受保护 API。

## 建模与开放接口 · 2026-10-20

`/api/projects/{id}` 下的 `/model`、`/model/history`、`/model/validate`、`/model/sync-area`、`/model/publish`、`/model/export.ifc`、`/model/export.idf` 提供版本化空间模型和发布。
`/imports` 创建/列举持久化识别任务，`/imports/{import_id}/review` 恢复人工复核节点。模型字段见 `building-model.json`，选项见 `model-import.json`。
`/model-runs` 提交原生仿真，`/runs/{run_id}/cancel` 仅取消排队任务。计算仍检查证据、文件哈希、发布模型快照及编译器版本。
`/tokens` 创建/列举项目 Token，`DELETE /tokens/{id}` 撤销。Token 有 read/write/compute 三类独立权限，最长 90 天；不可读取开发者设置、创建其他 Token 或访问其他项目。
`GET /api/developer/runtime` 提供实际安装组件、引擎版本、工具清单和单进程限制。通用 Provider endpoint、文本模型和视觉模型共用管理员配置。
旧 `/geometry` 保留兼容；当前建模 UI 使用 `/model`，不要把旧墙体草稿和新发布模型混为同一契约。完整步骤和限制见 `BUILDING_WORKBENCH.md`。

## 复杂建筑输入 · 2026-10-28

- `POST /api/projects/{id}/imports` 增加 `reconstruct_elements`、`reconstruction_tolerance_m`、`source_window_tolerance_m`。两个公差默认0；墙板重建仅在没有源IfcSpace时显式启用。`GET /files/{file_id}/ifc-storeys` 包含源建筑、楼层与构件清点，空空间楼层仍保留。
- `building-model.json` 增加闭合壳面、建筑/楼层归属、源窗、重建依据、设备及范围处置。IFC/模型预算2000空间、20000分段、100000最终热面，超过则拒绝；DXF/PDF线环识别仍限100。源曲面使用折面网格，不能视为精确曲面热实体。
- `GET /api/projects/{id}/model/equipment-template.csv` 下载UTF-8固定列模板；`POST /model/equipment-import` 接收`{file_id}`，仅解析本项目上传原件，返回待复核清单。功率W、风量m³/s，绝对铭牌与10项源曲线或显式原生参考模式。保存时必须逐空调空间一一匹配；源哈希、行号和参数绑定随版本保存。
- `thermal.window_geometry=source`采用源外窗/天窗；缺内外分类默认拒绝。墙板外包络、未知内部绝热及柱体等效热容均为独立的显式假设，不能绕过未恢复范围、源文件完整性或引擎校验。
- 发布和读取计算继续核对模型、编译器和源原件；逐空间PTHP结果标为耗电，理想模型标为冷热需求。`GET /api/developer/runtime`公布本机实际计算预算，生产仍为单服务进程、单原生引擎互斥。

客户端须从更新后的共享Schema取字段和约束。来源、操作与适用范围见[复杂建筑输入](COMPLEX_MODELING.md)，实际验收见[复杂建筑结果](HIGHRISE_MODELING_ACCEPTANCE.md)。

## 工程复核与交接 · 2026-10-28

- `GET /api/projects/{id}/engineering-review`：当前活动证据/模型/材料的复核台账、资料快照哈希、相邻模型字段差异。不是独立几何校验或工程签署。
- `POST /engineering-review/dispositions`：`snapshot_hash`、`finding_id`、`expected_revision`、`decision`、至少10字符`note`；当前登录人写入actor。仅假设类允许`accepted_scenario`，不会解除Gate。旧快照/修订冲突409，非法输入422。
- `GET /engineering-review/findings/{finding_id}/history`：本项目条目的不可覆盖历史；旧规则/模型/依据下处置不作为当前已复核。
- `GET /engineering-review/comparison-inputs.json`：源、空间/面积、热工/设备与选中IDF/EPW角色/版本的同题输入协议；不自动证明跨软件模型等价。
- `GET /engineering-review/report.html`、`issues.bcfzip`、`handoff.zip`：当前快照的未签署交接；BCF2.1只交换问题文字，交接包不含原件/凭据/数据库。导出有源损坏时仍可用于移交问题，但会保留来源无效及阻断，不假装可计算。

所有接口延用会话/项目归属和Token读写范围；写操作须CSRF，读Token可导出但不能写处置。相同源文件若只被已拒绝历史证据引用，不进入当前阻断；模型仍引用时继续校验。新模块变更使复核快照保守失效，物理核心未变时不使原生能耗额外失效。
