# 本轮文件去向

|原模块|本轮动作|位置与当前性质|
|---|---|---|
|backend/core.py|reuse + adapt|保留原生 SQL、真实引擎、碳计算、失效检查；增加受控输入根与锁定案例快照、复制时哈希检查|
|backend/service.py|preserve|旧标准库接口保留供回归，启动入口改为 api.py；不是双服务混跑|
|frontend/src Three.js/图表/报告/工作台|archive for incremental reuse|frontend/legacy/src；测试仍覆盖旧适配层；未将旧示意几何冒充项目模型|
|前端静态 JSON / samples / geo|isolate|fixtures/demo/frontend-data；修正归档源码中的相对导入路径|
|前端 public 图标|isolate|fixtures/demo/frontend-public|
|cases/reference_5zone|isolate reference input|fixtures/demo/reference_5zone；同步 registry、模型路径、准备脚本|
|原 Agent / optimizer / material / carbon|preserve locally|legacy/backend_submission；mock/代理公式不接活动计算|
|郭峰辉研究/交付|preserve locally|research/original_guo；不公开未整理的研究材料|
|原始运行/失败/验收|preserve locally|runs、validation/baseline；新证据在 runtime/runs 和 validation/phase1|
|新增前端|implement|frontend/src/main.js、api.js、style.css，真实项目/证据/API 入口|
|新增后端|implement|api.py、schema.py、store.py、domain.py、reports.py|
|契约/测试/运行|implement|shared/schemas、tests/test_api.py、test_parser_contract.py、scripts/verify.py/golden_path.py/replay.py|
|工程化上下文|implement|AGENTS.md、.agents/skills/vra-trust、docs、.github/workflows、deployment|

完整文件列表以 Git 提交及 `docs/CHANGED_FILES.txt` 为准。未公开归档仍在本机，并且原始包和上一版集成目录完整保留。

旧 ZIP 发布脚本 package_release.py / freeze_selected.py 已归档至 legacy/release_scripts，旧允许清单不适用于新 runtime；本轮使用 Git 交付，归档脚本不可直接运行。
