# 理想空调显潜热、新风及热回收交付

本批把原来只能查看逐时显热的工程路径，扩展为明确连接的理想空调系统的区内交付、供风处理、新风、热回收四种边界。每种边界分别显示加热/冷却的显热、潜热、总热量及同一时刻汇总峰值。属于原 B03 的限定增量，不是实际设备耗电、设备选型、规范合规或实楼校准。精确产品提交1b965837cb9fe4fb60239859c00f6c3208b69210三CI已成功；候选复评78，正式76分版本不变，详RESCORE_20261108_IDEAL_LOADS.md。

## 应用操作与调用链

1. 项目上传明确9.0版IDF；在IDF证据详情下载“显潜热诊断模型副本”。GET `/api/projects/{project_id}/files/{file_id}/ideal-load-output.idf` 校验会话、归属、格式及预期原文件SHA。副本保持原始全部字节前缀，只追加缺失的26项逐时输出，不改变原文件、不自动登记或替工程师确认。
2. 通过已有上传/证据入口导入并人工审查副本，绑定气象，再运行实际EnergyPlus9.0.1。仍标明假设/导入来源；下载不是准确性认证。
3. `extensions → ideal_loads.register_diagnostics` 提供副本；`core._run_simulation → inspect_ideal_loads → environment_rows` 检查原生SQL、模型连接、时轴及26个变量。记录模型/SQL/解析器/共享时轴模块哈希，`read_validated`复核绑定。
4. `metrics.ideal_loads`供API、运行详情、新前端面板、JSON/HTML报告及PDF05.5节读取。撤证后数值清空、重新运行拒绝；原始文件仍可下载。代码版本变更保守使旧物理运行stale，不改写历史manifest。

## 计算约束

- 单小时平均W积分为kWh：完整小时之和/1000；空气质量kg为kg/s之和×3600。功率峰值取同一小时各系统求和后的最大值，不能加各系统单独峰值。
- 原生理想空调负荷/流量已含Zone及ZoneList倍率，解析器scale_applied固定1；与原Zone Air System Sensible输出的倍率语义不同。保留模型区间映射及倍率元数据。
- 每边界逐时核对显热+潜热=总量；不强制四边界之间成立普遍线性守恒，因为原生新风输出受开机状态和方向截断控制。四种热量不可相加当总耗电。
- 仅支持全部声明系统完整绑定、最多64系统/64分区、完整24小时设计日或8760/8784小时单年度环境。混合HVAC明确列出未纳入设备和未覆盖分区。无理想系统为not_applicable；缺变量/单位错/重复/损坏SQL/时轴缺失/绑定冲突为unavailable且summary=null。
- SQL只读，512MiB文件上限、30秒查询预算、原生物理表及quick_check校验；每次仅保留一个系统逐时数据及汇总。下载源2MiB上限。不是全面资源隔离或长期性能验收。

## 实际验收

证据目录`validation/ideal-load-balance-20261108/`，SHA256在manifest.json；不是只有单元模拟通过。

- 冻结新单区干燥、湿负荷、显式新风、显热/全热回收、冬季及倍率共8条件；独立湿空气焓/水分平衡与真实EnergyPlus逐时输出核对。首7条件217项通过；倍率初始假设错误保留，按固定源代码及实际倍率证据修正独立答案后，该条件31项通过。模型和容差未为过关修改。产品解析另对保留的8份SQL做208项数值核对，属于传播检查，不重复计独立物理证明。
- 双区错峰、各自分区2×分组3倍率：实际同步峰值20468.966830W，独立预期20468.965517W；单独峰值之和27668.966790W。全部24小时总量及4项核对通过。首份测试模型生成错误导致Severe/Fatal，保留原输入/ERR；仅修正表面类型字段及节点名后新冻结运行。
- 最终真实HTTP108项检查、27个响应全部通过。真实年度8760小时、原生26变量逐项峰值与积分、三种报告、PDF文字抽取、原文件保全、撤证失效、401/409均完成。测试账号和数据在隔离C盘，服务关闭；正式原型及业务数据未动。
- 局部后端：首解析/共享时轴78通过；API与关联回归首次1失败56通过6跳过，失败为测试错误地将EquipmentList类型引用算成重复设备；修正断言后9个API专项通过；最终新增双系统2通过。上述集合有重叠，不相加冒充独立测试数。前端190活动+6历史测试通过，语法检查及Vite构建成功，既有Three大包警告仍在。
- 首次年度HTTP脚本因本机缺fitz在已生成PDF后停止，修正测试器用已安装pypdf，保留首次失败及原PDF；后续完成108项。最终版本加入共享供风节点拒绝后才做最终HTTP，停止无变化重复运行。
- 浏览器用户暂缓：未验视觉、真实点击或舒适度，不加UX分。真实建筑、实际设备效率及场地测量未验证。

## 发现及处理

|编号|功能/严重度|复现与实际结果|预期及修复|证据|
|---|---|---|---|---|
|IL-01|独立算例/中|12°C干工况供风在24°C/50%RH下超饱和，冻结前自检失败，未运行引擎|独立工况须满足控制前提；改14°C并新冻结，未改容差|preflight-v1-failure.json及v1/v2脚本|
|IL-02|倍率语义/高|3×2倍率原生理想负荷比初始未倍率答案大6倍，12项不符|源实现确认原生已经倍率；修正独立答案，产品不再次乘，重跑仅失败条件|native-v2/receipt.json、frozen-v3、native-v3-multiplier、sources.json|
|IL-03|API测试器/低|字符串计数把设备定义及EquipmentList引用混为一项，1断言失败|比较副本与原文计数及完整字节前缀，不改产品|api-first.log、api-fixed.log|
|IL-04|报告验收工具/低|年度计算及PDF生成后import fitz失败|提前导入已安装pypdf，读取同份PDF，再完成失效流程|http-first、http-first-script.py、http-complete|
|IL-05|双区测试输入/中|全局替换名称误改Floor/Roof枚举，另有供风节点名冲突，原生Fatal|恢复枚举、每区节点独立命名；产品显式拒绝共享供风节点，冻结新输入同容差|multizone-v1/failure.json及ERR、multizone-v2、two-system.log|

这些问题按发生层区分；IL-02是验证过程中纠正的关键物理语义，不能伪称已上线产品曾发生该倍数错误。未将测试器故障归为应用功能成功，也未隐藏首次失败。

## 可重复验证

安装项目锁定依赖与EnergyPlus9.0.1，设置ENERGYPLUS_EXE。在新目录执行（不能覆盖原证据目录）：

```text
python -B scripts/verify_ideal_load_balance.py --inputs validation/ideal-load-balance-20261108/frozen-v3 --output NEW_NATIVE_OUTPUT
python -B scripts/verify_ideal_load_http.py validation/ideal-load-balance-20261108 NEW_HTTP_OUTPUT
energyplus -d NEW_TWO_ZONE_OUTPUT validation/ideal-load-balance-20261108/multizone-v2/input.idf
python -B -m pytest tests/test_ideal_loads.py tests/test_ideal_output_api.py -q -p no:cacheprovider
```

第一命令重放冻结答案而不重新生成期望；双区frozen.json含先验答案及SHA，可对新SQL调用inspect_ideal_loads并比较。单元测试中的原生SQL投影只用于无引擎CI回归，不能冒充新引擎执行。raw SQL留本机，local-raw-sql-index.json给出路径/大小/哈希；发布的是真实SQL的有限投影、原输入、ERR、执行回执及HTTP输出，不发布运行库或凭据。

方法来源为固定EnergyPlus9.0.1公开源码（sources.json含下载地址及SHA）与[9.0工程说明](https://bigladdersoftware.com/epx/docs/9-0/engineering-reference/ideal-loads-air-system.html)。独立式h=1004.84T+w(2500940+1858.95T)，水分输入使用汽相焓而非汽化潜热，控制体、送风温湿度及混合/回收独立推导见冻结脚本；不是从运行结果拟合常数。

## 验收后补充观察

原生年度SQL存在125小时“供风加热、区内潜热冷却、供风冷却为零”的组合，例3月13日13时分别约15.997W、315.046W、0W，见post-ci/annual-boundary-explanation.json。这是不同控制边界不能简单排序或相加的实际反例，不是完整全年差额分解。

已离线渲染实际PDF第6/7页，中文/数值/单位和限制说明可见；不代替浏览器验收。新增低严重度IL-06：新风冷却的峰值行跨到下一页，而边界标签和能量值留在前页。复现、预期、实际、截图与建议见post-ci/pdf-visual-inspection.json；下一能力批合并修正PDF分组分页，不为这项观察单独重跑全量CI，不把报告阅读体验称为全部通过。
