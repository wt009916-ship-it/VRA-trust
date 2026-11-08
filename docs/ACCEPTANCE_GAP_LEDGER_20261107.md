# 原始验收需求与当前证据总账

2026-11-08，已发布340dfdb（PR56）；整合候选PR59基于PR57，尚未发布。旧版75与本次候选证据复核分开，依据RESCORE_20261108_EVIDENCE_REVIEW.md。原v1逐字归档；不是改写历史通过/失败。CURRENT_WORK_PLAN.md仍为唯一调度入口。

本表逐条区分“限定通过”“部分”“未通过”“未实现”“待验证”。**限定通过只覆盖写明边界，不代表完整工程设计、法规认证或全部输入域通过。** 判定依据既有实际日志、独立答案与代码路径，本轮没有重跑所有场景；测试文件存在本身不等于执行通过。历史证据定位回执另列，失效的旧dist不作原件证明。

原始A–J共77条、原十项对抗共10条，合计87条全部保留。数量统计只帮助调度，不能换算为成功率或分数。各批已冻结的容差不更改；未出现新的变更/失败不重复全量回归。

PR55运输联动已整合进PR57/59候选，未进入正式原型；已有独立五阶段生命周期计算不重复算新功能。规范过期与版本冲突已有实测，不能再排成“尚未开发”。

## A 热工

证据入口：[THERMAL_EVIDENCE_DELIVERY.md](THERMAL_EVIDENCE_DELIVERY.md)；[test_thermal.py](../tests/test_thermal.py)

|ID|原场景|当前判定|已验证边界及未完成部分|
|---|---|---|---|
|A01|单层热阻|限定通过|显式厚度/导热/修正系数独立Decimal对照；仅一维均匀干层。|
|A02|多层热阻|限定通过|逐层与总R、表面热阻明确；未加入非均匀热桥。|
|A03|传热系数|限定通过|U=1/R总，单位与未知值已核对；不输出合规结论。|
|A04|导热变化|限定通过|显式导热与修正系数改变R/U；不自动预测老化/含湿。|
|A05|材料组合节能比较|部分；未发布材料改模增量|明确表面/材性/层序派生IDF及真实年度比较已验证；新参考任务U降幅27.614808%、年度节能1.609718%，不混用。普通室外围护限定；浏览器及工程功能等效待验，见MATERIAL_MODEL_BRIDGE_DELIVERY。|
|A06|缺失数据|限定通过|厚度/导热/表面热阻缺失保留null及缺口。|
|A07|单位错误|限定通过|显式mm/cm/m、W/mW换算，错量纲及同名材料冲突拒绝。|
|A08|极端参数|限定通过|负厚、零导热、布尔、字符串、非有限及超域参数拒绝。|

## B 能耗节能

证据入口：[DESIGN_LOADS_DELIVERY.md](DESIGN_LOADS_DELIVERY.md)；[HOURLY_THERMAL_CROSSCHECK.md](HOURLY_THERMAL_CROSSCHECK.md)；[DESIGN_INPUTS_DELIVERY.md](DESIGN_INPUTS_DELIVERY.md)；[WEATHER_QUALITY_DELIVERY.md](WEATHER_QUALITY_DELIVERY.md)；[test_design_loads.py](../tests/test_design_loads.py)；[test_hourly_thermal.py](../tests/test_hourly_thermal.py)

|ID|原场景|当前判定|已验证边界及未完成部分|
|---|---|---|---|
|B01|基础信息|限定通过|面积等严格输入、版本与来源绑定；未知参数不自动猜测。|
|B02|围护结构识别|部分|IDF/IFC明确格式读取；退化图纸到完整热工模型未验收。|
|B03|采暖制冷负荷|部分|原生设计日/逐时显热及独立稳态/动态基准；潜热、系统和设备定容未完整验收。|
|B04|改造比较|部分；未发布材料改模增量|从热工记录明确映射四墙、不可变派生模型、原生年度运行和同源比较已有实际证据；工程功能等效、特殊构造、实楼校准及浏览器待验，见MATERIAL_MODEL_BRIDGE_DELIVERY。|
|B05|能耗预测|部分|真实引擎年度模拟；实楼账单/测量校准待外部资料，不能声称预测精度已知。|
|B06|节能率|限定通过|有有效同口径基准时计算；零分母/失效拒绝，限定于模拟情景。|
|B07|气候变化|部分|天气质量、设计日来源/多站核验；极端及广泛当地适用性未完整验收。|

## C 碳与资产

证据入口：[LIFECYCLE_PROGRESS.md](LIFECYCLE_PROGRESS.md)；[MATERIAL_WORKFLOW_PROGRESS.md](MATERIAL_WORKFLOW_PROGRESS.md)；[test_lifecycle.py](../tests/test_lifecycle.py)；[test_material_scenarios.py](../tests/test_material_scenarios.py)

|ID|原场景|当前判定|已验证边界及未完成部分|
|---|---|---|---|
|C01|生产阶段|限定通过|清单数量×来源因子；PR54材料来源数量已接入，人工映射/因子仍是声明。|
|C02|运输阶段|部分；44f344e有增量|已发布生命周期手工活动算术通过；采购质量/包装质量→吨公里联动已整合PR57/59，多墙两方案有独立Decimal及浏览器证据，已发布44f344e。实际物流活动与因子真实性仍需依据，见COLLECTION_SCENARIOS_DELIVERY。|
|C03|施工阶段|限定通过|声明活动量/单位/因子算术可复核；不自动提取施工实耗。|
|C04|运行阶段|限定通过|运行年量按期间累计；CO2与CO2e口径分列，不推断未来实际能耗。|
|C05|全生命周期|部分|五阶段边界/活动清单可算；完整清单覆盖、替换周期、真实因子及规范方法核证未完成。|
|C06|材料替换|部分|同边界成本/生产碳比较；结构、耐火、耐久、热工功能等效未核证。|
|C07|因子缺失版本冲突|限定通过|缺因子不汇总，同ID版本/单位/来源冲突拒绝；来源文字不等于真实已核证。|
|C08|来源过程追溯|限定通过|文件/证据/项目/计算器快照、版本、撤回失效及历史保留；不输出认证碳资产。|

## D 退化图纸

证据入口：[DRAWING_OCR_DELIVERY.md](DRAWING_OCR_DELIVERY.md)；[DRAWING_GEOMETRY_DELIVERY.md](DRAWING_GEOMETRY_DELIVERY.md)；[DRAWING_GEOMETRY_CROSSCHECK.md](DRAWING_GEOMETRY_CROSSCHECK.md)；[test_drawings.py](../tests/test_drawings.py)；[test_drawing_geometry.py](../tests/test_drawing_geometry.py)

|ID|原场景|当前判定|已验证边界及未完成部分|
|---|---|---|---|
|D01|低分辨率|部分|真实OCR有候选和原件；限定公开文字7/8，不能称整图可靠。|
|D02|模糊平面图|部分|处理/OCR已运行；模糊结构与完整尺寸识别未达标。|
|D03|墙线缺失|未实现|未实现工程语义补线；中值过滤曾删81像素细线，不冒称修复。|
|D04|尺寸缺失|未实现|不能恢复原图未载尺寸；人工尺度/条件长度不等于补全。|
|D05|文字重叠污损|部分|候选/复核与有限滤波存在；可靠分离、识别精度及置信度校准未验收。|
|D06|倾斜噪声|限定通过|有限角度纠偏、正逆坐标、显式滤波差异和原件保留；无语义保真保证。|
|D07|多图关联|部分；44f344e已发布|已实现有来源的有限编号/明确尺寸跨页关联、冲突复核与失效撤回；78后端及独立双页真实OCR/浏览器证据见DRAWING_ASSOCIATIONS_DELIVERY。尚不验证几何实体同一性、未命名尺寸或广泛图纸语义，不能据旧描述重做接口。|
|D08|构件识别分类|未实现|OCR文字框不是墙门窗或结构构件识别；完整工程分类未实现。|

## E CAD/BIM

证据入口：[CAD_BIM_DELIVERY.md](CAD_BIM_DELIVERY.md)；[IFC_OPENINGS_DELIVERY.md](IFC_OPENINGS_DELIVERY.md)；[IFC_SELECTED_UNION_CROSSCHECK.md](IFC_SELECTED_UNION_CROSSCHECK.md)；[MATERIAL_WORKFLOW_PROGRESS.md](MATERIAL_WORKFLOW_PROGRESS.md)；[test_cad.py](../tests/test_cad.py)；[test_ifc_union.py](../tests/test_ifc_union.py)；[test_ifc_materials.py](../tests/test_ifc_materials.py)

|ID|原场景|当前判定|已验证边界及未完成部分|
|---|---|---|---|
|E01|DWG/DXF|部分；未发布DWG候选|DXF已有证据；新增Windows隔离DWG→DXF严格解析3真实API成功/2拒绝。转换损失和R14限制保留，浏览器待验，不能写全部通过。|
|E02|IFC读取|限定通过|公开及合成IFC真实解析；不保证所有IFC版本/表达均支持。|
|E03|属性提取|限定通过|实体、容器、材质关系及明确属性提取；源文件缺失不补造。|
|E04|数量统计|部分；44f344e有增量|实体计数、限定扣洞/并集；44f344e含多墙同材料去重及AXIS3楼板/屋面板分层与洞口实例处理，见MATERIAL_COLLECTION及SLAB_LAYERS交付。材料包络不等于采购净量，全模型及专业计量规则未完成。|
|E05|空间关系|部分|容器/宿主/开洞及选定几何相交；复杂邻接/空间推理未完整覆盖。|
|E06|分类|部分|IFC源类型与已有属性分类；自动专业语义归类未证明。|
|E07|文件格式转换|部分；未发布候选|限定DWG→DXF、转换告警、原件保持与来源失效下载门禁已实测；不是无损或多格式互转。见CAD_BIM_DELIVERY末节。|
|E08|模型完整性|部分|损坏、关系冲突、单位/原件/派生失效检查；完整模型规则覆盖未验收。|

## F 规范

证据入口：[STANDARDS_DELIVERY.md](STANDARDS_DELIVERY.md)；[standards.py](../backend/standards.py)；[test_standards.py](../tests/test_standards.py)

|ID|原场景|当前判定|已验证边界及未完成部分|
|---|---|---|---|
|F01|需求检索|部分；未发布语义候选|固定公开模型自然需求检索已实际贯通；新12题前三位10/12→12/12、首位9/12→10/12。仍需人工核对候选，未证明全库覆盖、库外识别或适用性判断；见SEMANTIC_STANDARDS_DELIVERY。|
|F02|条款定位|限定通过|准确条款号、PDF页和来源定位；跨页表格/复杂分条未覆盖。|
|F03|名称版本|限定通过|名称/代码/版次/声明有效期及审核日期保留；不自动确认今日规范状态。|
|F04|条文引用|限定通过；候选扩展来源|文字层原文校验；候选另有扫描原页实际OCR候选、位置/分数及人工修订复核，两个固定官方页及浏览器证据见STANDARD_OCR_DELIVERY。引用区分来源性质，不把人工修订认证为原文字层或当前规范适用性。|
|F05|多规范交叉检索|部分；候选有增量|2026-11-07历史自由文本多标识409保留；2026-11-08核对f9fa47a已有结构化targets批量查询，见STANDARD_BATCH_DELIVERY。扫描原页复核入库已补，见STANDARD_OCR_DELIVERY；不据旧描述重复开发，不等于语义多规范裁决。|
|F06|过期版本冲突|限定通过|已实现未生效、过期、复核日期过旧与同时有效版本冲突拒绝；无需重复开发。|
|F07|错误问题纠正|部分|代码/版次/条号矛盾拒绝、不编造未找到条文；开放专业错误推理纠正未证明。|

## G 结构工程

证据入口：[PROFESSIONAL_AGENT_DELIVERY.md](PROFESSIONAL_AGENT_DELIVERY.md)；[AGENT_ENGINEERING_DELIVERY.md](AGENT_ENGINEERING_DELIVERY.md)；[test_engineering.py](../tests/test_engineering.py)

|ID|原场景|当前判定|已验证边界及未完成部分|
|---|---|---|---|
|G01|荷载参数识别|部分|显式荷载输入/单位/范围校验；从自由图纸或长文本自动完整识别未验收。|
|G02|构件信息提取|部分|手工梁参数及源文件绑定；BIM到结构分析参数的可靠自动衔接未完成。|
|G03|简单工程计算|限定通过|简支/悬臂线弹性梁、集中/均布/局部荷载、解析与独立FEM对照。|
|G04|参数异常|限定通过|支承、区间、单位、缺属性及极小荷载域检查；安全状态保持未评定。|
|G05|过程追溯|限定通过|输入/来源/版本/表达式及报告可查，撤证失效、原记录保留。|
|G06|结果交叉验证|限定通过|Fraction闭式解与独立离散方法，预定误差限；不等同结构安全审查。|

## H 造价材料

证据入口：[MATERIAL_COST_DELIVERY.md](MATERIAL_COST_DELIVERY.md)；[MATERIAL_WORKFLOW_PROGRESS.md](MATERIAL_WORKFLOW_PROGRESS.md)；[MATERIAL_SCENARIOS_EVIDENCE.json](MATERIAL_SCENARIOS_EVIDENCE.json)；[test_material_cost.py](../tests/test_material_cost.py)；[test_material_scenarios.py](../tests/test_material_scenarios.py)

|ID|原场景|当前判定|已验证边界及未完成部分|
|---|---|---|---|
|H01|工程量识别|部分；44f344e有增量|单墙外，44f344e已有公开四墙分材去重、20楼板36层及墙板混合计量的独立答案/API/浏览器证据。仍为限定分层包络，梁柱/设备、复杂全模型专业净量未完成，见MATERIAL_COLLECTION、SLAB_LAYERS交付。|
|H02|材料统计|部分|几何层量经明确实体率/密度/损耗映射；实物规格及未建模附件不自动推断。|
|H03|成本估算|限定通过|数量/单位/换算/含来源日期币种价格和舍入可复核；不是核证市场报价。|
|H04|材料替换方案|部分；44f344e有增量|候选把单/多构件来源量、显式实体率/密度/损耗接到两方案材料成本及五阶段声明碳；同源报告、公开参考与独立算术通过，已发布44f344e。结构/耐火/耐久/热工功能等效仍未核证，见COLLECTION_SCENARIOS_DELIVERY。|
|H05|缺失数据|限定通过|价格/密度/实体率/损耗未知不得生成完整比较；冲突拒绝。|
|H06|结果导出|限定通过|实际UI整链打开同源HTML与JSON；失效后撤下旧量/金额/碳。|

## I 施工运维

证据入口：[CONSTRUCTION_SCHEDULE_DELIVERY.md](CONSTRUCTION_SCHEDULE_DELIVERY.md)；[OPERATIONS_DELIVERY.md](OPERATIONS_DELIVERY.md)；[test_construction.py](../tests/test_construction.py)；[test_operations.py](../tests/test_operations.py)

|ID|原场景|当前判定|已验证边界及未完成部分|
|---|---|---|---|
|I01|施工方案辅助|未实现|未交付经过专业验证的可施工方案生成；工序DAG不替代施工方案。|
|I02|工序安排|限定通过|显式FS依赖/间隔、拓扑/关键路径；工作日历与自动资源调平未实现。|
|I03|施工进度|限定通过|显式状态与剩余工期情景、独立路径穷举/手算；缺资料不预测确定完工日。|
|I04|风险识别|部分|环路、进度矛盾、资源超配可查；现场施工安全风险未全面识别。|
|I05|设备运行数据|限定通过|CSV原件、测点/时间/单位/质量及来源，公开仿真数据真实运行。|
|I06|异常状态|限定通过|显式范围/差值/变化率及持续事件；不是训练出的通用故障诊断器。|
|I07|维修建议|部分|缺口/核查提示；现场根因确诊、维修工单和维修后复验未完成。|

## J AI Agent

证据入口：[LOCAL_MODEL_EVIDENCE.json](LOCAL_MODEL_EVIDENCE.json)；[AGENT_OUTPUTS_DELIVERY.md](AGENT_OUTPUTS_DELIVERY.md)；[AGENT_ENGINEERING_DELIVERY.md](AGENT_ENGINEERING_DELIVERY.md)；[AGENT_REQUEST_SCOPE_DELIVERY.md](AGENT_REQUEST_SCOPE_DELIVERY.md)；[test_agent_outputs.py](../tests/test_agent_outputs.py)；[test_agent_read_recovery.py](../tests/test_agent_read_recovery.py)

|ID|原场景|当前判定|已验证边界及未完成部分|
|---|---|---|---|
|J01|多轮对话|部分|真实模型多轮工具交付有记录；小样本开发集不代表开放连续对话可靠。|
|J02|复杂任务拆解|未通过；候选有增量|旧F01失败保留；PR56已修同源累积，f9fa47a应用执行器已真实查询施工目录，不能据旧失败重复开发。当前阶段分离新8题1/8→5/8，3题仍失败；非数值/澄清出口已实现，新10题4B仍仅5/10，真实澄清续答未验；不能据旧失败重做接口，见AGENT_PHASE_DELIVERY。|
|J03|工具自主选择|部分|真实模型选择过工具；冻结参数和授权范围有界，计划仍intent_verified=false。|
|J04|工具失败恢复|部分|存在实际错误ID→列表→重读成功；stale/重复交付等复杂恢复仍失败。|
|J05|多工具串联|部分|有限工程计算/读写/报告实际完成；一般复合覆盖与真正多智能体协作未验收。|
|J06|上传与理解|部分|文件工具/源记录可读；未证明开放图纸语义与跨文件任务完整理解。|
|J07|长文本|待验证|有长度/预算限制，但不等于长文本完整理解；无独立广泛留出结果。|
|J08|上下文记忆|部分|会话及来源快照存在；长期语义记忆/冲突消解未全面验收。|
|J09|幻觉识别|部分|来源绑定卡片和应用解释可控；模型自由文本错误不能靠隐藏它算已解决。|
|J10|不确定性表达|部分|incomplete/未知/失效和能力限制可见；模型原意理解仍未验证。|
|J11|错误输入|部分|结构化输入拒绝、工具异常有证据；自由文字矛盾和开放误导仍未完整覆盖。|
|J12|越权与注入|部分|认证/项目范围/若干名称注入通过；一般跨来源提示注入和全部历史路径未通过。|

## X 原十项对抗

证据入口：[test_thermal.py](../tests/test_thermal.py)；[test_api.py](../tests/test_api.py)；[test_lifecycle.py](../tests/test_lifecycle.py)；[test_drawing_geometry.py](../tests/test_drawing_geometry.py)；[test_standards.py](../tests/test_standards.py)；[test_cad.py](../tests/test_cad.py)；[AGENT_OUTPUTS_DELIVERY.md](AGENT_OUTPUTS_DELIVERY.md)

|ID|原场景|当前判定|已验证边界及未完成部分|
|---|---|---|---|
|X01|负墙厚|限定通过|结构化热工输入拒绝，无确定R/U。|
|X02|零导热|限定通过|拒绝零导热，无Infinity。|
|X03|同材料不同单位|部分|热工/成本/生命周期各自换算或拒绝；跨模块自由文本组合未完整验收。|
|X04|面积零求EUI|限定通过|项目面积零拒绝，不以默认面积替代。|
|X05|碳因子无来源|限定通过|契约/缺证限制明确，不授予认证资产；来源真实可信仍需核验。|
|X06|尺寸比例尺矛盾|部分|至少两个人工声明参考区间冲突可拒绝；不是自动读图发现全部矛盾。|
|X07|要求补不存在结构|部分|无语义补图/结构安全认定能力；开放模型诱导仍需独立留出验收。|
|X08|建筑参数矛盾|部分|结构化重复/单位/边界矛盾检查有证据；自由文本混合矛盾未全覆盖。|
|X09|损坏CAD/PDF|限定通过|真实坏文件、解析隔离/限额与恢复已测；不推论任意恶意文件安全。|
|X10|编造不存在条款|部分|确定性索引返回未找到、不造原文；自由LLM原文仍按J项验收。|

## 八维分值与继续执行

专业15/20、计算18/20、Agent9/15、文件6/10、完整度8/10、稳定性8/10、安全8/10、体验3/5，总计75。分值不是上述“限定通过”行数折算；计算闭环新增1分，历史未归属3分不计，依据独立复评说明。

并发持续运行是本机有界验证，未覆盖引擎/LLM/解析混合队列生产长稳；结果单列LOCAL_SOAK_DELIVERY.md。下一开发从明确未过项选择，先写用户能完成的任务与固定验收出口，不能再把泛称“综合验收待完成”当重复开工理由。复杂图纸、Agent自主可靠性、适用性和外部专业验收仍开放。
