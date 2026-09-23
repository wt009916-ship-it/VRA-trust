# Phase 1 contract v1.0

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
API 是本机单用户边界，无公网鉴权。Agent/chat、general decision evaluate、自动方案生成、优化、反例和主动补证估值 API 尚未实现。
