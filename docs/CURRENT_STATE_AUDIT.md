当前入口（2026-11-08）：正式44f344e/76分；PR60精确CI成功/候选76.5。DWG候选新增隔离转换与严格解析，真实API验收见CAD_BIM_DELIVERY末节及DWG_EVIDENCE；浏览器因Work关闭本地控制待验，本批不加分。仅CURRENT_WORK_PLAN调度。下方保留历史。

当前入口（2026-11-08）：PR57/59已合并并发布44f344e；混合负载验收完成。新模型故障恢复为独立未发布候选，实际新任务对照与限制见AGENT_READ_RECOVERY_DELIVERY末节，调度仅CURRENT_WORK_PLAN。下方为历史阶段记录。

当前版本索引（2026-11-08）：正式340dfdb；PR59整合候选新增非数值来源复核与澄清出口已完成应用验证，真实模型10题仅5题严格通过、真实澄清续答未验。候选独立版本证据复核75/100，完整CI以最终提交回执为准。详RESCORE_20261108_EVIDENCE_REVIEW末节、AGENT_PHASE_DELIVERY增量；仅CURRENT_WORK_PLAN调度，以下各批文字为历史状态，不再据旧待办重复开发。

2026-11-08 Agent阶段候选：同4B固定新8题由1/8到5/8，P03/P04/P05仍失败；独立计划阶段与受限运维观测计数已实现，72相关后端有通过证据、168前端及真实任务渲染/构建通过。APH-03年字段与APH-04纯状态缺结构化出口是下一批目标；不刷旧题。原24题4B0/24、9B8/24，未换正式模型。正式340dfdb/75分不变，详AGENT_PHASE_DELIVERY。

2026-11-08扫描规范候选：真实选页OCR与原页对照、显式人工转录复核、已有批量检索及来源失效撤引文已接通。42后端、167前端后追加标签回归8项、两官方固定原页及真实浏览器通过；标签误标与SVG高度缺陷已修、失败留存。最终CI另验，75分/正式340dfdb不变，见STANDARD_OCR_DELIVERY与唯一调度CURRENT_WORK_PLAN。

2026-11-08 方案来源状态候选：单/多构件表单保留当前输入、失效/断网/超时禁用、恢复GET及提交前复核、旧请求隔离已实现；165前端及真实浏览器验收通过。完整CI待精确提交核验；75分与正式340dfdb不变。详SCENARIO_SOURCE_DELIVERY.md，调度仍以CURRENT_WORK_PLAN.md为准。

2026-11-08 楼板/板材候选：明确AXIS3挤出参考面、真实洞口逐层切割、多类型材料集合及方案入口已实现。75几何+1真实HTTP、158前端、公开20楼板36层及浏览器通过；共享洞口漏扣已修，失败留存。最终CI待验，评分75，正式原型340dfdb不变；详SLAB_LAYERS_DELIVERY.md，唯一调度CURRENT_WORK_PLAN.md。

2026-11-08 多墙材料方案候选：去重材料实体→声明实体比例/损耗/密度→两套成本与五阶段碳→当前报告已接通。公开冻结算术/真实浏览器/撤证、158前端及专项通过；最终CI待验，本批不发布不加分。详COLLECTION_SCENARIOS_DELIVERY.md；已发布版本为PR56的340dfdb。

2026-11-08多墙材料候选：真实分层几何按材料去重、跨材冲突拒绝、API/报告/界面已实现。38原生+50相关后端、156前端、公开4墙3组及浏览器提交/失效通过；完整CI待精确提交检查，原型与75分不变。见MATERIAL_COLLECTION_DELIVERY.md及CURRENT_WORK_PLAN.md。

2026-11-08符号检测验收：真实几何检测新14参考图及2公开原图已完成；清晰/退化门窗门槛和新增原图局部正例均未通过。未接入应用、未加分，75保持。见DRAWING_SYMBOL_SCREEN.md，调度仅以CURRENT_WORK_PLAN.md为准。

2026-11-08构件识别基线：父提交f9fa47a三项CI已收口。新增14公开/生成参考输入和42次固定Florence-2推理，门窗定位与墙分割未过门槛，未接入应用、未加分，D08仍开放。见DRAWING_COMPONENT_SCREEN.md；调度仅以CURRENT_WORK_PLAN.md为准。

2026-11-08集成候选更新：现有PR57整合55/56/58并连接材料方案Agent；176/144专项与真实浏览器核验完成，真实4B新题严格2/6，额外解释/输入区遮挡仍开放。未发布，75分保持；详SCENARIO_AGENT_INTEGRATION.md及CURRENT_WORK_PLAN.md。

2026-11-08当前状态：已发布原型5209d744（PR53/54），证据复评75；本分支跨图标注关联为未发布候选，78后端/10前端及独立双页PDF浏览器流程通过，CI另验。D07仍部分，D08几何识别未完成；本批不加分。当前安排见CURRENT_WORK_PLAN.md，证据见DRAWING_ASSOCIATIONS_DELIVERY.md；下方历史评分和旧下一步仅为历史。

2026-11-07 CAD当前性更新：新增有界状态接口与20条分页，失效/断网/超时撤下数量、恢复fresh GET、迟到响应隔离、隐藏暂停和并集来源核验已实现。Windows1185/Linux1194各6子测试及118前端通过；首轮备份时间字段兼容失败保留并修复。真实21条分页、390px、旧响应延迟、2条明细与并集同时失效恢复通过；首次全历史加载仍开放。开发复评77保持，发布以回执为准。详[交付](CAD_CURRENT_STATE_DELIVERY.md)、[复评](RESCORE_20261107_CAD_STATE.md)。

2026-11-07选定IFC并集更新：显式2–64构件、体积和/并集/重复扣除、隔离执行、JSON/HTML及来源失效撤下已实现。Windows1182/Linux1191及各6子测试、100前端通过；双平台8基础数值/1边接触拒绝、6扩展及6公开对独立核验。大坐标旋转精度修复，圆柱近似误差约0.011m³保留；浏览器3文件/原件/390px/失效自动撤下通过。Linux首轮进程回收测试竞态已保留修复。开发复评77，下一批先普通CAD全页失效刷新，再材料计量与Agent/长稳；训练/全局视觉后置。详[交付](IFC_SELECTED_UNION_DELIVERY.md)、[交叉验证](IFC_SELECTED_UNION_CROSSCHECK.md)、[复评](RESCORE_20261107_IFC_UNION.md)。发布以回执为准。

2026-11-07 IFC开洞更新：修复全覆盖洞口错误返回毛体积，空网格保持未知；重复/多宿主/孤立开洞关系拒绝交付几何量并保留实体定位。Windows1152/Linux1161通过，各6子测试；96前端通过。双平台8合成案例含6数值与2拒绝，公开模型109个独立量核对；真实无头浏览器3文件、原件哈希/匿名401/390px通过，GUI启动及局部标题遮挡仍开放。跨构件净量未实现，评分76保持。详[交付](IFC_OPENINGS_DELIVERY.md)、[交叉验证](IFC_OPENINGS_CROSSCHECK.md)、[复评](RESCORE_20261107_IFC_OPENINGS.md)。发布以本批release回执为准；训练及整体视觉后置。

2026-11-07设计气象来源更新：DDY原件/声明版本/人工复核、显式设计日映射、逐字段对照、撤证失效及JSON/HTML报告已实现。双平台各5站90设计日、2365原始字段独立一致；Windows1145/Linux1154通过，各6子测试，94前端通过。浏览器50字段、迟到刷新修复、撤证自动清空、匿名/跨账号/CSRF通过，截图仍超时。物理哈希与174业务记录/3任务不改；评分76保持，下一批复杂IFC净量及Agent对抗，训练/整体视觉后置。详[交付](DESIGN_INPUTS_DELIVERY.md)、[交叉验证](DESIGN_INPUTS_CROSSCHECK.md)、[复评](RESCORE_20261107_DESIGN_INPUTS.md)。发布以本批release回执为准。

2026-11-07自由漂移更新：新增分区温度切换、双峰值日曲线及逐时表；双平台同输入8例各6达0.02K、2粗步长超限，温度/负荷序列跨平台差0。92前端、66后端专项及构建/语法通过；浏览器真实年度6区8760小时、288温度值与API一致、390px及撤证清空通过，普通点击/截图稳定性超时保留。后端68源码与原业务记录不改。复评76保持；发布以本批release回执为准。接下来设计资料适用性、复杂IFC净量及一般Agent注入；训练/整体视觉后置。详[交付](FREEFLOAT_THERMAL_DELIVERY.md)、[交叉验证](FREEFLOAT_THERMAL_CROSSCHECK.md)、[复评](RESCORE_20261107_FREEFLOAT.md)。

2026-11-07逐时热工更新：新增原生逐时温度/显热交付、相同时刻全楼峰值、峰值日曲线及同源JSON/HTML/PDF，未请求/缺失/不完整保持unavailable。Windows1119/Linux1128通过，各6子测试，89前端通过；每平台11新动态模型9达解析误差限、2粗步长超限，失败保留。冻结同一输入后动态统计跨平台差0；全年R1/R2制冷峰值微小差仍未达到1e-6 W严格一致性判据。真实浏览器6区/8760小时、导出、匿名/跨账号拒绝、撤证清空及空手动角度零POST通过；截图与普通点击稳定等待超时，视觉待验收。复评76保持；发布以本批release回执为准。下一批自由漂移室温及独立动态基准、设计资料适用性；净量/复杂图纸/一般注入/实楼及生产验收仍开放，不扩大训练、整体视觉后置。详[交付](HOURLY_THERMAL_DELIVERY.md)、[交叉验证](HOURLY_THERMAL_CROSSCHECK.md)、[复评](RESCORE_20261107_HOURLY_THERMAL.md)。

2026-11-07图纸几何更新：真实隔离OCR处理版本、原件/派生件校验、正逆坐标、用户声明尺度区间和条件长度JSON已实现。双平台各12场景限定检查通过，公开OCR仅7/8、旋转后6/8；过滤删除81像素弱线，语义修复未实现。Windows1083/Linux1092及各6子测试、85前端通过。浏览器先复现越界后旧3m残留，修复后输入/失败/迟到响应撤下通过；损坏派生件stale/null与原件保护通过。截图接口与桌面审批均超时，视觉验收待验证。精确Git构建资源与浏览器一致；复评76保持，发布以release回执为准。下一批动态热工独立基准与设计资料适用性，净量/复杂图纸/一般注入/实楼及生产验收仍开放。不扩大训练，整体视觉后置。详[交付](DRAWING_GEOMETRY_DELIVERY.md)、[交叉验证](DRAWING_GEOMETRY_CROSSCHECK.md)、[证据](DRAWING_GEOMETRY_EVIDENCE.json)、[复评](RESCORE_20261107_DRAWING_GEOMETRY.md)。

2026-11-07设计负荷更新：真实ZoneSizes/设计日解析、来源绑定、API/PDF/ZIP与Agent原生结果卡已交付。双平台各7个新稳态模型/28数值检查，最大差0.003272W；最终Windows1050通过/25跳过、Linux1059通过/16跳过，各6子测试；前端82通过。37真实模型任务105请求逐轮保留，最终有效四题两模型均读取两页，但4B失效恢复失败、原文仍有数值错配，Agent分不增加。两轮浏览器、当前失效重检及原件保护留证；最终Git前端资源与验收字节相同。复评76（独立热工+1），发布状态以release回执为准。下一批图纸来源保全/倾斜噪声/尺度冲突及独立金标准，继续动态热工与设计资料；RS-07/RS-09、一般注入、净工程量、DWG/转换、实楼/专家和生产验收仍开放。详[交付](DESIGN_LOADS_DELIVERY.md)、[交叉验证](DESIGN_LOADS_CROSSCHECK.md)、[证据](DESIGN_LOADS_EVIDENCE.json)、[复评](RESCORE_20261107_DESIGN_LOADS.md)。95+未达，不扩大训练，整体视觉后置。

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
