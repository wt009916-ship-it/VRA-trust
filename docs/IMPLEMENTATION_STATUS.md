# 2026-11-06 真实本地模型与工具闭环

新增loopback本地模型模式与管理员配置；固定Qwen3-4B/llama.cpp原生HTTP推理、实际应用工具、20题最终/新题留证。修复日期参数哈希及工具定义冗余，新增运行列表与纠错指引。Linux599+6子测试/16跳过；Windows首次全量588通过/2个跨平台参考夹具失败/25跳过，更正夹具后的6项相关测试通过，未重跑全量；33前端通过。解释错误、任务未完成及能力边界混淆保留，开发复评73。详LOCAL_MODEL_DELIVERY.md、LOCAL_MODEL_EVIDENCE.json及RESCORE_20261106_LOCAL_MODEL.md。下一步结构化产物与解释一致性，不扩大训练。

# 2026-11-06 Linux停止过程身份保留

先实际观测旧代码reap后仍尝试组信号，再以WNOWAIT保留监督器直到组清理；身份丢失、SIGCHLD非默认/SA_NOCLDWAIT拒绝。Linux578后端+6子测试、16跳过，Windows50监督专项/11跳过；双平台各25真实E+核查、Linux四条/Windows两条服务恢复通过。D盘真实空间拒绝保留，C盘新私有目录重跑；未降额度。复评71不变，详PROCESS_IDENTITY_DELIVERY.md和PROCESS_IDENTITY_EVIDENCE.json；下一步真实本地模型工具调用。

# 2026-11-06 原生资源所有权与服务恢复

双平台真实 ASGI 强杀先复现残留，再接入私有所有权账本、继承活动租约、精确身份/Profile 核验与启动回收。Windows/Linux 各 569 后端+6子测试、16明确平台跳过，四条真实服务链各50项检查通过；公开IFC/OCR和25项E+验证回归。旧81文件及索引保持原字节，开发复评71；硬额度/长稳/真实模型/实楼仍待验收。详NATIVE_RECOVERY_DELIVERY.md、NATIVE_RECOVERY_EVIDENCE.json及RESCORE_20261106_RECOVERY.md。

# 2026-11-06 原生进程父死亡约束

双平台真实复现调用者强杀后监督器/引擎仍活；新增Windows私有存活管道、原生stdin独立NUL、Linux双代PDEATHSIG及严格回执。进程链强杀/恢复专项通过，完整统计见PARENT_LIFETIME_EVIDENCE.json。新物理参考在独立目录重跑，旧索引失效和容量拒绝保留。完整API强杀的私有目录/profile回收仍未完成；评分70保持，详PARENT_LIFETIME_DELIVERY.md及RESCORE_20261106_LIFETIME.md。

# 2026-11-05 解析缓存核验调度

Windows大缓存至多8线程读取全部文件SHA，原安装/完整清单检查和失败拒绝保留。六轮实际隔离DXF对照中首次复用中位26.85→7.79秒，18个独立答案通过；双平台各84解析专项通过、2明确跳过，公开IFC/OCR复验通过。小样本长尾与硬额度/强杀缺口仍在；本轮浏览器会话过期、凭据恢复待补充授权，界面未计通过。复评70，详PARSER_CACHE_DELIVERY.md及证据索引。

# 2026-11-05 CAD/PDF/OCR 原生解析隔离

三条活动解析链接入每任务 LPAC / 非root Landlock+seccomp、只读输入副本及可信监督回执；公共运行库缓存逐次核验，客户资料不共享。Windows528/Linux530后端加各6子测试、32前端及公开IFC/OCR、真实浏览器上传/提取通过；原失败保留。缓存warm准备仍慢、硬额度与强杀回收未关闭，评分保持70。详PARSER_ISOLATION_DELIVERY.md和PARSER_ISOLATION_EVIDENCE.json；最终远程头的检查另行留证。

# 2026-11-05 Linux EnergyPlus Landlock/seccomp 隔离

Linux 版本检查和年度模拟接入非 root、Landlock ABI≥6、seccomp 默认拒绝及只读输入副本；缺条件不退回普通权限。实际 WSL/ABI7 三方案与 SQL Decimal、取消恢复通过，523 后端+6子测试通过、12明确跳过。双平台最终数量和源码身份见 LINUX_NATIVE_ISOLATION_EVIDENCE.json。评分仍70，解析器隔离、硬额度/强杀回收、实楼/Provider验收继续保留缺口；详 LINUX_NATIVE_ISOLATION_DELIVERY.md。

# 2026-11-05 Windows EnergyPlus LPAC 隔离

Windows版本检查和年度模拟已默认接入LPAC、挂起令牌/能力/访问核验、只读副本、标准流限定继承、环境过滤及输出/profile联合监测。522后端+6子测试、32前端、25项真实E+核查及实际浏览器运行通过。原失败与容量拒绝保留；Linux/解析器隔离和硬额度仍未完成，评分维持70。详NATIVE_ISOLATION_DELIVERY.md及NATIVE_ISOLATION_EVIDENCE.json；远程最终提交检查另行留证。

# 2026-11-05 任务执行限额与原生计算监督

持久化仿真/Agent/Search限额、故障释放、仿真取消、Windows Job/Linux rlimit监督和有界原生输出已接入。真实三方案、20项引擎核查及浏览器取消/恢复已执行；最终全量与跨平台结果见TASK_EXECUTION_EVIDENCE.json。旧证据失效记录保留，复评维持70。完整沙箱/生产长稳仍待验收，详TASK_EXECUTION_DELIVERY.md。

# 2026-11-05 累计原件配额与事务导入

新增项目/共享原件字节与份数、事务计费、磁盘余量预检、失败回滚及参考项目整体登记。24并发接受8/拒绝16、18项恢复核查；479后端+6子测试、32前端及实际浏览器重试/超限通过。评分保持70，原生输出和长期负载仍未验收。详STORAGE_QUOTAS_DELIVERY.md及证据索引。

# 2026-11-05 加密备份与访问保护

CLI默认AES-256-GCM认证加密，口令不持久化；新建临时与恢复目录在明文写入前限制权限并回读。Windows受限令牌真实拒读、独立密码API互操作及35项真实工程恢复检查通过。原生隔离/配额/生产灾备仍待验收，开发复评70。详ENCRYPTED_BACKUP_DELIVERY.md、ENCRYPTED_BACKUP_EVIDENCE.json及更新后的BACKUP_RECOVERY_GUIDE.md。

# 2026-11-05 本地停服备份恢复

新增目录锁、SQLite/WAL一致快照、严格归档校验、新目录恢复、会话撤销和未完成任务失败记录。真实EnergyPlus/CAD/OCR原件及历史完成31项恢复演练，旧证据失效不被恢复抹除。备份加密/Windows DACL/生产灾备和累计配额仍未验收，开发复评保持69。详BACKUP_RECOVERY_DELIVERY.md及BACKUP_RECOVERY_EVIDENCE.json。

# 2026-11-05 解析器资源预算与恢复

三个原生工作器在导入前设置OS预算，资源身份绑定结果并拒绝无回执输出；388后端通过、1平台跳过、6子测试，公开IFC/OCR真实重跑。Windows匿名映射缺口实测保留，Linux树级/文件网络隔离未完成；本轮Edge首页403导致UI受阻。评分维持69，详WORKER_RESOURCE_DELIVERY.md及RESCORE_20261105_RESOURCES.md。

# 2026-11-05 图纸OCR与人工复核

新增离线PNG/JPEG/PDF页文字候选、位置叠框、原件与模型身份、人工更正及修订历史。7张独立合成图与公开Kinnear旧图实测；公开预选12处正确10处，0.99224高分误识别明确保留。修复像素取整预算、缺依赖异常、复核选择/版本显示及依赖公告风险。开发复评69，完整图纸修复和原生资源沙箱仍未完成；不启动扩大训练。详DRAWING_OCR_DELIVERY.md及RESCORE_20261105_OCR.md。

# 2026-11-05 IFC声明量与近似几何

新增类型/实例来源、声明工程量显式单位、空间关系与有界原生三角化。独立核对公开Duplex 295产品/空间关系、108矩形拉伸体和21声明面积；修复浏览器发现的空间分解关系遗漏。25项新专项及26前端通过，最终全量结果见IFC_GEOMETRY_EVIDENCE.json。开发复评68分；净工程量/完整拓扑/硬内存隔离/OCR仍未完成，不启动扩大训练。详IFC_GEOMETRY_DELIVERY.md及RESCORE_20261105_IFC.md。

# 2026-11-05 DXF块展开与几何测量

新增嵌套块/阵列/OCS/非均匀变换、限定长度/简单边界面积、源实例路径和等比例XY预览。修复大坐标短线精度、近闭合误判及公开椭圆舍入回归，保留失败记录。最终319后端+6子测试、24前端、公开LibreCAD符号12实体独立交叉核验及浏览器验收通过。评分维持67，详DXF_GEOMETRY_DELIVERY.md及DXF_GEOMETRY_EVIDENCE.json。IFC几何、OCR、净工程量和实楼适用性仍未完成；训练和整体前端改版继续后置。

# 2026-11-05 设备运维规则限定闭环

新增明确时钟/单位CSV核查、范围/差值/变化率、工况与缺测覆盖、原行追溯、历史失效、同源报告及Agent只读工具。修复十进制阈值相等误报；两份LBNL首周仿真切片与独立算法一致（0/6事件），不等于现场诊断验证。最终299后端+6子测试、22前端及真实浏览器验收通过。开发复评67分，详OPERATIONS_DELIVERY.md和RESCORE_20261105_OPERATIONS.md。训练与整体前端改版仍后置。

# 2026-11-05 施工进度限定闭环

新增FS关键路径/时差、显式剩余工期情景、声明资源重叠检查、来源失效与同源报告、Agent只读工具。25项施工专项（含64种独立路径网络）及真实浏览器验收通过；本批修复极小资源需求精度问题。开发复评66分，详CONSTRUCTION_SCHEDULE_DELIVERY.md及RESCORE_20261105_SCHEDULE.md。现场安全、资源自动调平和设备运维仍未验收。

# 2026-11-05 材料工程量与成本限定闭环

显式数量/损耗/密度/报价、同范围替换比较、来源失效及JSON/HTML报告已完成本地验收；修复热工和生命周期已撤回证据仍可新建结果的问题。全量242后端+6子测试，报告修复后专项68项、前端19项通过。浏览器基准4651.85与独立答案一致；当前评分维持65，尚未进入扩大训练。详MATERIAL_COST_DELIVERY.md及证据索引。

# 2026-11-05 梁分析限定闭环

新增显式单位/来源的简支与悬臂线弹性梁分析、不可覆盖记录/失效/报告、Agent只读工具；Fraction及独立有限元验证，214项后端+6子测试、19项前端及限定浏览器验收通过。修复极近支座精度、曲线尺寸和梁草稿丢失。详ENGINEERING_PROGRESS.md；当前增量复评65分，详RESCORE_20261105.md。结构安全、规范合规及实楼仍未评估。

# 2026-11-04 CAD/BIM限定读取

新增真实DXF/IFC只读解析、单位/类型/属性/空间包含关系、原件保留、版本失效、进程超时和容量限制。详CAD_BIM_DELIVERY.md。按原八维标准增量复评62/100，详RESCORE_20261104.md；尚未达到用户要求的95分以上，扩大数据训练和整体前端视觉改版继续后置。

# 2026-11-04 Agent任务协议增量

限定任务目标的完成核验、3轮可追溯摘要、只读工具最多2次纠错、参数归一化重复写入防护、严格工具参数/Provider响应、上下文预算及历史任务界面已实现。132项后端、6子测试、13前端通过；34项真实EnergyPlus专项通过（含Agent当前结果核验与撤证失效）。详 [Agent增量验收](AGENT_TASK_CONTRACT_DELIVERY.md)。固定Provider协议夹具不代表在线模型验收，真实Key联调仍待完成。热工PR #5已通过远程六项检查并合并。

# 2026-11-04 热工与因子来源增量

原型新增逐层R/U、显式单位、缺参拒算、历史失效、构造比较、同源JSON/HTML报告与碳因子来源复核。最终120后端测试、6子测试、13前端测试通过，31真实EnergyPlus专项通过。详 [本批验收](THERMAL_EVIDENCE_DELIVERY.md)。用户已确认继续公开参考数据；实楼、真实Provider及其余专业模块仍待验收。PR #4已经远程CI通过并合并，下方GitHub阻塞为历史状态。

# 2026-11-04 独立盲测后的第一批修复

公开版Provider裁剪缺口已在本修复分支恢复。最终101后端测试、13前端测试、31真实专项检查通过；npm公告扫描0。详 [本批验收](AUDIT_P0_DELIVERY.md) 和 [后续路线](ACCEPTANCE_ROADMAP.md)。在线Provider、实楼校准和全面专业能力仍未验收；下方为历史记录，不能替代本批证据。

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
