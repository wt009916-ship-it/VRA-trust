# Current State Audit — 2026-09-23

本报告先于产品代码修改建立。审计对象是三人原包、商业计划书和 20260923 集成候选版；README 和商业计划书中的承诺不作为实现证明。

## 已读资料与范围

- 商业计划书 DOCX：正文及表格共 1345 个非空段落；嵌入图片未逐张判读。产品核心为 Evidence Manifest / Claim DAG / Decision Certificate，资料不完整时可拒答并建议补证。
- 龚希苗 `agent_building2.zip`：排除虚拟环境、缓存后，关键源码与集成版 legacy 的 117 个选定文本文件逐字节一致；归档不等于活动服务。
- 熊思月 `vite-project(2).zip`：审查 Three.js、适配层、首页、JSON、报告、图表、任务状态；26 个选定文件相同，9 个修改，另有新增计算工作台。
- 郭峰辉总包：工程约定、24×4 对照设计、缺陷注入、研究及成果材料。研究设计和预期表格不能当实测研究结果。
- 集成版：递归清点 backend、frontend/src、public、cases、legacy、research、scripts、tests、docs、validation 和 runs；读取原生 SQL、ERR、manifest、result。依赖包和二进制不是逐行人工代码审查对象。
- 原件均保留；本轮活动目录为独立的 `vra-trust/`。原包及历史运行不自动发布至 GitHub。

## 修改前复现

在独立副本执行 `python scripts/verify.py`（2026-09-23 12:53 UTC）：后端 31 项、前端 6 项、Vite 构建均通过。日志先保存在 `validation/`，随后归档至 `validation/baseline/`。
随后执行 `scripts/run_reference.py` 重新调用真实 EnergyPlus；新运行证据与旧运行分目录保存。以执行日志为准，不沿用此前验收日期。

## 模块判断

|模块|状态|代码/证据与判断|处理|
|---|---|---|---|
|旧首页及 KPI|MOCK / NEEDS_REFACTOR|`frontend/src/main.js` 默认加载 dashboard_data.json；参考入口另在 workbench.js|旧体验归档，生产首页改为项目准入|
|真实前后端连接|PARTIAL / REUSABLE|workbench→apiAdapter→service.py 的 runs/compare 接口真实调用|保留解析和适配思想，新增项目 API|
|API|PARTIAL|标准库 HTTP server 有正式路由；无项目、上传、OpenAPI、租户|FastAPI/Pydantic 包装既有内核|
|run_id|DONE（局部）|每个参考 run 独立输入/输出，manifest/result 双向绑定；无 project_id|补项目/证据版本绑定|
|EnergyPlus|DONE（参考链）|core.run_simulation 真 subprocess，超时/非零/ERR失败不降级|复用，导入模型沿用同一核验|
|原生 SQL parser|DONE / REUSABLE|core.parse_sql 校验全年、面积、单位、分能源总和|保留并补异常集成测试|
|页面/JSON/报告同源|PARTIAL|真实工作台与 HTML 报告来自比较结果；旧 PDF 仍走 DOM/示例；费用未入报告|统一 run view 和服务端 PDF|
|Evidence/provenance|PARTIAL|文件 SHA、运行快照、源码/因子失效已有；无完整证据对象、来源定位 UI|建立持久化 Manifest 与人工确认|
|Claim DAG|MISSING / REUSABLE|core.DEPENDENCIES 为固定域映射，非结论级 DAG|第二阶段；第一阶段提供真实依赖视图基础|
|Agent|LEGACY / MOCK|LangGraph 关键词路由；未发现实际 LLM tool-calling；材料/能耗存在硬编码及 fallback|保留源码，禁止接入生产计算|
|优化|LEGACY / MOCK|NSGA-II 调用代理公式，未连接 EnergyPlus；挑中间 Pareto 点不等于用户目标最优|保留，后续以真实工具评估替换代理|
|碳|PARTIAL / REUSABLE|分能源运行 CO2 和因子地区限制有效；完整 LCA、CCER 未实现|保留分界及空值|
|资料输入|MISSING|仅注册案例、导入结果 JSON、人工缺口表；无项目输入层|Phase 1 重点|
|残图识别|MISSING|未找到可运行墙体识别/缺口补全算法|后续 Evidence Acquisition，不能宣称已有|
|三维|PARTIAL / REUSABLE|building.js 按静态几何 JSON 规则生成，非 BIM 或参考 IDF 重建；窗洞表现非真实拓扑开孔|保留旧源码，生产不冒充项目几何|
|材料库|LEGACY / PARTIAL|JSON 数据与构造层可复用；稀土实测优势无证据|字段来源/适用性需补齐|
|研究实验|PARTIAL / MOCK|设计文档有效；旧批处理存在写死的 stale/rerun/FP/FN|不可报告为完成的对照实验|
|GitHub|MISSING（起点）|本地无 Git；目标仓库 wt009916-ship-it/- 尚无远程 ref|初始化并按权限推送|
|云|MISSING|用户已购阿里云但未配置；本机 Docker daemon 不可用|提供部署契约，不能称已上线|

## 明确限制与冲突

参考模型为官方 5ZoneAirCooled 派生，US-CO Golden 天气，927.2 m²；不是南昌真实建筑。基准已有保温，R1/R2 是追加 80/100 mm 假设材料；各两项设备定容 Warning 需复核。不能把能耗最低直接写为最优工程建议，也不能把有限搜索没发现翻转写成稳定性证明。

原后端在导入 runner 失败后仍返回模拟成功、无真实 tool calling、优化代理公式与静态财务/碳值，均与当前产品真实性原则冲突。旧 README 的“完成”、旧实验的常数结果以及项目愿景不等于实现。

## 本轮顺序

0. 保留历史、Git、Demo 隔离、API/Truth 契约和 Repo Skill。
1. 项目 + 结构化输入 + 文件证据 + 人工确认 Gate + 原生仿真 + 一致结果/JSON/PDF + 自动化验收。
2. 后续逐阶段完成 Claim DAG / 选择性重算 / Certificate / Agent / 反例 / 补证 / 空间 / 云；本轮不伪称全部完成。
