# Phase 1 contract v1.0

账号增量：GET /api/auth/status、POST /api/auth/register、POST /api/auth/login 为公开入口；GET /api/auth/me、POST /api/auth/logout 需要会话。除 health 和三个公开账号入口外，所有业务 API 均须 vra_session Cookie；写请求另须 X-CSRF-Token。注册/登录/me 返回 csrf_token，前端只保存在内存。项目及 run/报告/文件下载按账号归属授权，无权限统一 404，未登录 401，CSRF/跨来源 403。OpenAPI 已标注 cookie 和 CSRF security schemes。

权威定义：backend/schema.py；生成件 shared/schemas/openapi.json、building.json、evidence.json、run.json。执行 python scripts/export_contract.py；CI 检查 schema drift。

- POST/GET /api/projects；GET /api/projects/{id}；PUT /api/projects/{id}/building。
- POST /api/projects/{id}/files：multipart file，20 MB 默认，返回 file_id；GET 对应 file_id 下载源文件。
- POST/GET /api/projects/{id}/evidence；PATCH /evidence/{evidence_id} 人工复核；GET /history。
- GET /api/projects/{id}/gate?scheme_id=baseline；GET /api/projects/{id}/runs。
- POST /api/runs；GET /api/runs/{id}、/result、/evidence、/claims、/artifacts。
- GET /api/runs/{id}/report.json、report.html、report.pdf；同源核验视图。
- POST /api/comparisons；明确仅能耗排序、确定推荐为 null。
- POST /api/reference-projects：显式导入官方输入，data_nature=engineering_reference，状态待审，无历史结果。
- GET /api/factor-profiles、/api/health。

证据/建筑修改带 expected_revision；409 拒绝版本冲突、证据不齐或绑定错误；422 拒绝非法 schema；413 超限。来源文件不能通过 API 覆写，复核历史追加保留。
正式 run 结果必须包含完整 provenance。queued/running/failed/stale 的受影响数值为 null。错误不能触发 demo fallback。
建筑声明只用于核对，不自动改变 IDF。当前接受 IDF 9.0 + SimpleAndTabular 输出；IFC/epJSON 等可作为资料保存但未接通转换计算。
API 具备账号会话及项目归属校验，仍绑定本机；公网部署待验收。自动方案生成、完整优化与通用 decision evaluate 尚未实现。


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
