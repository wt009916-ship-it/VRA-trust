# 梁、进度与设备规则的真实 Agent 交付

本批把已有三类专业计算器接入“用户明确参数 → 实际保存新记录 → 读取当前记录 → 核验字段/限制 → 同源报告”的 Agent 流程。不是新增结构安全认证、自动施工安排或设备故障确诊。公开预训练 Qwen3-4B 实际本机推理，没有训练、脚本冒充模型回答或放宽预算。开发复评见 RESCORE_20261106_ENGINEERING.md，证据摘要见 AGENT_ENGINEERING_EVIDENCE.json。

## 实现与适用范围

|功能|实际调用链|边界|
|---|---|---|
|梁分析|Chat.calculation_plans → EngineeringPlan/BeamInput → calculation_execute → Engineering.save → beam_analysis_read → professional_deliver|矩形等截面、恒定 EI、小挠度线弹性；模型不适用时不交付设计数值，不是承载力/结构安全结论|
|施工进度|SchedulePlan/ScheduleInput → Schedules.save → schedule_read → professional_deliver|FS 依赖、连续经过日、显式进度情景；关键任务集合不是唯一串行路径，不自动资源调平或保证实际工期|
|设备规则|OperationPlan/AnalysisInput → 当前项目真实 CSV file_id → Operations.save → operations_read → professional_deliver|明确单位、时钟、窗口与阈值；各规则事件可能重叠，不是独立故障数；缺测不当作健康，不能控制设备|
|只读专业目标|inspect_engineering / inspect_schedule / inspect_operations → 对应 list/read → 当前产物|默认最新记录、显式目标、历史重检；不授予写权限|
|限制说明|当前 read → professional_limit → 当前 hash/status 重检|与数值工具分开；只核验限制，显示 limits_verified，整体问题仍为 partial|

参数仍由用户显式提供，最多两份冻结计划，不允许模型自行修改；文件、证据、项目修订和输入快照绑定，来源变更拒绝执行。完整模型循环仍为最多 5 轮、15 事件、2 次可恢复纠错。模型自由文字保留于审计，不冒充核验结果。三个专业的物理/进度/规则计算器和 EnergyPlus 核心未为本批修改。

数值事实新增 static_load_case、elapsed_days、observed_window 期间口径，保存来源字段、单位及当前 hash。设备缺测时有效计数可以交付，但只能显示 fields_verified（所列字段已核对，结果仍不完整），不能显示完整分析通过。仅说明限制时仍呈现真实边界卡片，不出现空的数值卡片。

## 独立输入与交叉验证

所有本批输入均为独立合成数据，非实楼、实测设备或规范认证基准。输入、输出、原始事件和行号保存在 validation/agent-engineering-20261106；维护测试为 tests/test_agent_engineering.py。

|批次|独立输入|独立答案及实际核对|
|---|---|---|
|初次梁|简支 5 m，250×400 mm，E=32 GPa，满跨 6 kN/m|反力 15000 N；最大弯矩 18750 N·m；挠度用 Fraction 独立计算 5qL⁴/(384EI)|
|初次工序|A=2.5，B=4.25（A 后滞后 0.5），C=1.25（A 后），D=0.75（B/C 后）|工期 8 day；关键任务 A/B/D|
|初次设备|7 个每分钟温度样本 20/23/24/21/25/26/20°C，阈值 22°C，持续至少 60 s|2 事件，CSV 行 3–4、6–7，各 60 s|
|新梁留出|悬臂 3.6 m，200×300 mm，E=28 GPa，距固定端 2.4 m 的 7.5 kN 点载荷|反力 7500 N；最大弯矩 18000 N·m；端挠度独立式 Pa²(3L−a)/(6EI)|
|新工序留出|A/B/C/D/E/F 六任务，双关键支路、滞后、零时长节点；第 2 日的显式完成/剩余状态|计划 4.7 day；关键集合 A/B/C/D/F；情景完工日 5.8，偏差 1.1 day|
|新设备留出|8 个华氏温度样本；1 个空单元、1 处超限时间间隔；25°C 阈值|样本 8，缺失/无效单元 1，时间缺口 1，2 事件（行 3–4、7–8），未知样本 1；不能判为完整分析|
|最终新梁|悬臂 4.8 m，180×300 mm，E=26 GPa，满跨 3.2 kN/m|反力 15360 N；最大弯矩 36864 N·m；端挠度独立式 qL⁴/(8EI)|
|最终新工序|A=0.8、B=1.6（A 后滞后 0.3）、独立 C=2.1、D=0.4（B/C 后）、E=0.7（D 后滞后 0.2）|计划 4 day；关键集合 A/B/D/E|
|最终新设备|6 个每两分钟双温度样本；温差 0/1/3/4/1/0°C；阈值 2°C，最短 120 s|1 事件，CSV 行 4–5，120 s，无缺测|

26 项新增后端测试覆盖上述数值、记录创建、同源报告、历史失效、跨项目拒绝、文件篡改绑定、错误单位/期间/认证字段、深梁范围、缺参、资源冲突、规则重叠、两计划预算、限制协议和部分计数状态。针对性组合测试和最终双平台全量的准确数量/耗时以证据索引为准。

## 真实模型与浏览器证据

固定 Qwen/Qwen3-4B-GGUF，revision bc640142c66e1fdd12af0bd68f40445458f3869b；模型 SHA-256 7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5。llama.cpp b12110 / cd959bae99ff4bed22bef2604f45241c09bbb8c8，8192 上下文，单并行槽，4 CPU 线程，GPU offload 99，reasoning off。服务只绑定回环、随机令牌仅在内存、未授权请求实际 401，结束后停止。

|证据目录|实际任务数|结果与含义|
|---|---:|---|
|live-first|6|五个常规/名称注入任务完成；深梁数值被挡住，但模型伪造数值“状态”字段后未形成正式限制说明。旧检查只看无不安全数值，8/8 不能解释为完整交付通过|
|live-recheck|6|首次将可选限制字段混入数值协议后，严格检查仅 4/8 通过；模型混用两个分支，正确计算也交付失败。原始失败保留|
|live-recheck-v2|6|分离 professional_limit 后，8/8 预定检查通过，含正式限制说明；这是同题修复回归，不是独立盲测准确率|
|live-holdout|3|固定新输入、新问题首次执行 3/3 通过；未按答案调低容差；设备结果明确部分核验|
|live-contract-final|6|全量发现契约不一致后改为独立 NumericDelivery，六题回归 8/8 检查通过|
|live-holdout-final|3|上述契约修改后的同题复测仅 2/3；悬臂梁误用中文标签作为字段键且未恢复，原始失败保留|
|live-keys-final / live-holdout-keys-final|6+3|工具列出当前可用机器键后，分别 8/8 检查及 3/3 同题通过；不是新的盲测|
|live-fresh-final|3|固定新的均布悬臂、五任务网络及双温度差规则，首次 3/3；与已参与调试的旧留出题分开记录|
|live-lint-smoke|3|只删除三行未使用导入后重验上述三题；仅作为最终源码冒烟，不计新盲测|
|浏览器|4+3+4|原界面验收、契约修复后的三个已完成任务、最终四任务分开。中间设备流程在上传成功后停滞、尚未发起模型任务，不计通过；修复重建窗口后再验，真实提交和报告同源打开|

合计 45 次实际 API 模型任务及 11 次浏览器模型任务，不能把调试、复测和留出混算成“盲测 100%”。各六题批次的 stdout 在深梁专用条件替换前打印通用 completion=false；最终 receipt 中的专用限制条件才是该用例结论，原 stdout 未重写。首次 Windows 全量 703 通过、1 失败：工具 JSON schema 被临时改写，与服务器 ToolArgs 不一致；原 tests/test_local_model.py 一致性断言未放宽，改为独立强类型后相关 104 项通过，再执行完整回归。

浏览器还验证了启用/禁用本机模型后无需刷新页面即可更新执行模式标签，以及新建项目后立即打开设置的竞态修复。密码为新隔离账户在内存随机生成，没有恢复旧账号凭据或创建正式用户。截图 output/playwright/engineering-agent-*.png 已人工查看；仍存在小字号、低层次、长导航和技术字段较多问题，不能据此宣称整体前端已优化好。

## 缺陷与处置

|编号 / 严重度|对应功能、问题描述|复现步骤|预期 / 实际|证据|修复建议与状态|
|---|---|---|---|---|---|
|ENGA-01 / 中|模型不适用时缺少可核验限制交付|在 live-first 使用 5 m 梁、1000 mm 高度，要求说明不适用|预期正式说明限制；实际两次把“梁分析状态”伪造成数值事实，最终未完成。没有放行工程数值|live-first/live-results.json 的 outside_beam_screen|已以 professional_limit 修复；当前 hash/status 强校验，最终真实复测与浏览器通过|
|ENGA-02 / 中|可选限制字段污染数值工具契约|在首次修复版执行 live-recheck 的有效梁/工序/名称注入任务|预期数值交付；实际同时提交 statements 与 limitation_status 被拒，严格检查 4/8|live-recheck/live-results.json|已拆成两个工具；不放宽互斥校验。保留原失败，复测及新题通过|
|ENGA-03 / 中|缺测但存在有效计数时，进度状态不能准确表达部分核验|用新设备留出数据交付样本和事件计数|预期字段可核对、分析不完整；旧路径仅在完整时 verified，否则 saved_unverified，不能区分部分字段交付|tests/test_agent_engineering.py 的 holdout operation；browser-operation-task.json|已新增 fields_verified；整体 partial、不推荐/不诊断|
|ENGA-05 / 中|数值工具描述与服务器强类型契约不一致|完整运行 tests/test_local_model.py 的 reachable constraints 测试|预期全部可达约束一致；实际手工移除限制字段并添加 minItems，导致首 Windows 全量失败|final/windows-full.log；contract-fix-focused.log|已定义独立 NumericDelivery，移除手工改写；原断言保留|
|ENGA-06 / 中|模型误把中文标签当机器字段，恢复不充分|live-holdout-final 悬臂梁问题|预期 exact fact key；实际两次提交中文字段名后未交付，计算记录保留但不放行数值|live-holdout-final/live-results.json|已在工具中列出当前事实键，并在未知键错误中返回合法键；数值/单位校验不放宽，新输入另测|
|ENGA-07 / 低|集中工具分派后残留未使用导入|执行 CI 同款 ruff check|预期静态检查通过；实际 agent.py 的 Engineering/Schedules/Operations 三行报 F401|backend-lint.log；backend-lint-final.log；import-cleanup-proof.json|已仅移除三行，服务仍由 agent_inspections 导入，其余字节精确一致；不放宽 lint 规则|
|CAP-UI-02 / 中|保存配置后执行模式仍提示未配置|打开开发者设置，启用本机模型并保存，返回工作台|预期即时更新；旧界面须重新加载。新界面启用/禁用均即时刷新|frontend/tests/agent-mode-status.test.js；browser-config-race-receipt.json|已增加保存后刷新、请求序号避免旧响应覆盖；读取失败显示待核实，不声称连通|
|ENGA-UI-01 / 中|项目保存后的迟到加载关闭刚打开的设置|保存新项目，保存表单一消失就点击开发者设置|预期设置保持打开；首次浏览器等待 90 s 超时，快照已回到工作台|browser-current.json；browser_race.cjs；browser-config-race-receipt.json|已把表单退出放到项目加载完成后；真实快操作回归通过|
|ENGA-UI-02 / 中|资料登记后页面重建与连续参数操作存在竞态|完成 CSV 上传与证据登记，立即在 Agent 参数区操作|预期下一操作保持有效并发起任务；中间复验 files/evidence 均 201，未出现第四次 agent POST，脚本等待响应被人工终止。没有抓到具体被覆盖控件，因果判断基于代码窗口而非已捕获完整轨迹|browser-release/harness-stall.json；browser-runtime-release/api.log；browser-ui-final/browser-operation-submitted.json|已先完成 selectProject 再退出导入表单；后续实际上传、提交202、模型交付和报告通过。辅助脚本增加提交超时/失败快照；中间停滞不计通过|
|ENGA-04 / 中 / 开放|计算参数仍需技术性 JSON|在 Agent 参数区提交六类计划|预期专业用户可高效选择现有表单/资料生成计划；当前需手工 JSON，file_id 也需显式提供|frontend/src/agent-calculations.js；浏览器实际操作脚本与截图|后续增加可审阅的专业表单/草稿转计划；不能用模型猜参替代来源|
|SEM-07、CAP-02/03 / 高 / 开放|自由解释、混合能力覆盖及一般提示词注入仍未全面解决|复用前批认证/设备混合问题与其他文件/历史入口|本批单个名称注入通过，不证明所有入口安全或完整复杂任务覆盖|AGENT_CAPABILITIES_DELIVERY.md 及其原始失败证据|继续固定未见题、不同预训练模型对比和多来源注入检验，不用隐藏原始错误冒充模型正确理解|

## 复现与发布

使用 Python 3.12、backend/requirements-dev.txt 和原有平台引擎/解析器依赖；先运行 `python -m pytest tests/test_agent_engineering.py -q`。全量从独立源码副本运行 `python -m pytest -q -rs`，Windows/Linux 不并行与实际模型重任务；前端执行 `npm test`、`npm run lint`、`npm run build` 和根目录 `node scripts/check_frontend.mjs`。OpenAPI 由 scripts/export_contract.py 在隔离 VRA_DATA_DIR 导出，API 合约检查随 CI 验证。

真实模型脚本在 validation/agent-engineering-20261106，需本机已核验运行库/模型及原平台参考文件。它们保留原输入输出；新复测应创建新目录，不覆盖日志。浏览器脚本使用真实 Chrome 和应用 UI，没有伪造网络响应。原物理 hash、81 个旧文件、原 reference_comparison.json 及复制参考的哈希校验见证据索引。

原始运行日志、截图和隔离数据按仓库规则留在本机，不随源码上传；GitHub 提交维护测试、报告和逐文件 SHA-256 索引。第三方如需复核原始本机结果，仍需取得该证据包；公开 CI 日志及源码测试不能替代取得原始模型记录。

辅助环境失败另记 TEST-ENGA-01：Windows 默认 GBK 读取带中文的 UTF-8 浏览器脚本，准备阶段报 UnicodeDecodeError；v2 明确使用 utf-8-sig 后继续。harness-environment.json 是从工具执行记录整理的摘要，不冒充原始进程日志，也不计作应用或模型任务成功。

TEST-ENGA-02：WSL 初次通过 `--` 调用 nobody 的禁止登录 shell，被拒绝且未启动测试；改用 `--exec` 直接运行已有解释器，仍为 nobody，不改账户权限。见 linux-launch-environment.json。

索引构建首次因 Windows 反斜杠路径未匹配三行导入清理的例外而拒绝；统一路径表示后通过，旧/新 hash 和精确删除三行的字节证明保持强校验，不放宽其他源码一致性要求。

## 最终版本与回归

Windows 704 通过、25 跳过、6 子测试通过，781.09 秒；Linux 713 通过、16 跳过、6 子测试通过，366.89 秒。平台跳过主要是另一操作系统的权限/进程保护，不补推通过。原失败 Windows 703/1 和首次 lint 三项失败均保留。前端 58 通过，lint/构建/语法及最终 OpenAPI 对照通过；保留现有大于 500 kB 构建块警告。

完整功能/界面源码为 `949047199cfeccaa77efdcb32f18a368e9613345`；最终 `90a83d76a75a49db35a000ad9f604e42266a1ffc` 只移除三行未使用导入。Windows 全量和最后浏览器四任务基于前者；Linux 全量及最后模型冒烟基于后者。精确差异和各阶段 hash 在证据索引，不能声称 Windows 与最终源码完全逐字节一致。168 个发布相关文件中其余 167 个一致，agent.py 除这三行外的字节一致；最终 CI 必须基于最终 PR head 再验。

本批未完成复杂整栋 CAD/图纸修复、完整规范/节能合规、实楼校准或独立专家验收。接下来优先比较更强公开预训练模型的任务覆盖与恢复能力，再补复杂文件和气候/设计日基准。扩大训练与整体视觉改版仍按用户指定次序后置。
