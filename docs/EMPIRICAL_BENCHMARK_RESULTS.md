# 实际对照结果 · 2026-10-21

**结论：限定流程确实可运行；复杂工程自动建模和自由提问助手尚未达到可交付水平。没有证据证明优于广联达、斯维尔或主流商业 AI。** 本轮实际执行了公开工程 IFC、五份气象年、同输入原生仿真和开源智能体框架对照。这里的“实测”指软件实跑；没有建筑现场能耗真值，不能计算预测误差或真实节能率。

起点版本 `f7dd5d09a14b8dc3c20bacec878f312f62f0b48d`；先保存失败，再修复工具定义膨胀。实验范围见[采集前协议](EMPIRICAL_BENCHMARK_PROTOCOL.md)。机器为 Windows、Core Ultra 7 255HX、约 16 GB 内存；LLM 明确使用 CPU 8 线程，未使用 RTX 5060 加速。

## 1. 新公开工程：Schependomlaan 没有通过

来源：[buildingSMART Schependomlaan](https://github.com/buildingsmart-community/Community-Sample-Test-Files/tree/7ddf57a201f88a0c213d5322b02ed15e94a60a40/IFC%202.3.0.1%20%28IFC%202x3%29/Schependomlaan)。上游说明设计模型来自 ROOT 为实际工程制作的 Archicad BIM，许可用于科研/教学；本测试不代表可将数据商业再分发。原文件未改，49,286,967 字节，SHA256：`2c3565ca1904f2aa61adab92024cf3755b2c5b21a498144d3094d7cb58cebec7`。

|实际步骤|实测结果|
|---|---|
|IfcOpenShell 0.9.0.post1 清点|100 空间、934 墙、259 窗、205 门、279 楼板、6 楼层、1,675 空间边界关系|
|默认生产上传接口|HTTP 413；默认 20 MB 限额|
|隔离环境将已有配置 `VRA_MAX_UPLOAD_MB` 设为 64 后|上传 HTTP 201；导入仍 HTTP 409|
|逐空间三维表示诊断|6 个空间有 Body/SweptSolid；94 个只有 Box/FootPrint，无完整空间实体|
|原生三维提取及 VRA 水平分段提取|都只能处理这 6 个空间；产品拒绝将部分空间作为全楼发布|

这不是成功案例。调大上传限额只能解决传输，不能补出缺失的真实几何。不能用包围盒或默认层高冒充完整空间。该输入没有进入能耗计算。IfcOpenShell 是产品共同依赖，这组对照只检查输入与保留情况，不能当成独立几何精度认证。

## 2. 已知样例：Duplex 与原生 EnergyPlus 一致

重新通过正式 API 导入原始 buildingSMART Duplex：21 个空间保留为 25 个水平分段；运行 ID `run_61181583fcdd43d3875bf2ea05db77a0`。然后把该运行的**同一份** IDF 和 EPW 交给 EnergyPlus 9.0.1 CLI 再跑一次，直接查询原生 SQL：

|指标|VRA API|原生 CLI|差值|
|---|---:|---:|---:|
|年总场地能源 kWh|28,043.63|28,043.63|0|
|电力 kWh|12,294.38|12,294.38|0|
|理想供冷需求 kWh|12,411.63|12,411.63|0|
|理想供热需求 kWh|3,337.62|3,337.62|0|
|建筑面积 m²|240.59|240.59|0|
|全年天数|365|365|0|
|Warning / Severe|0 / 0|0 / 0|0|

天然气及 Additional Fuel 也都为 0，共 7 个表格数值定位一致。原生 CLI 本次耗时 22.50 秒；不能与整个 API 工作流耗时直接排名。本轮两次实际引擎执行。保留 IDF、EPW 哈希、SQL、ERR、报告和输入包。

**适用边界仍很大：**这个样例此前已经用于开发，不是新的盲测项目；材料、窗墙比、运行时段、Golden 天气和 0.02 m 几何归并都是明确假设。211 个面按绝热处理，实际门窗没有完整转译；理想冷热需求不能当热泵耗电。此结果仅证明封装一致，不证明真实建筑精度。原始失败与后续修复见[外部样例审计](EXTERNAL_SAMPLE_AUDIT.md)。

## 3. 天气：VRA / Ladybug / pvlib 三方实际读取

使用 EnergyPlus 9.0.1 安装包随附的五份原始 EPW；Ladybug Core **0.44.62**、pvlib **0.16.1**。每个解析器每份文件运行三次，共 45 次正常文件读取；独立输入仍只有五个。另有 9 次异常副本读取。

|站点|小时数|VRA 年均温 °C|年 GHI kWh/m²|
|---|---:|---:|---:|
|San Francisco|8,760|13.794|1,716.434|
|Golden|8,760|9.761|1,619.948|
|Tampa|8,760|22.290|1,811.211|
|Chicago|8,760|9.988|1,406.646|
|Sterling / Dulles|8,760|12.671|1,481.122|

- VRA 与 pvlib 的 **43,800 个逐时温度和 43,800 个 GHI 均逐值相同**。
- Ladybug 会将瞬时温度的最后一小时移到首位。未对齐时最大差异达到 13°C；依据其实际安装的 `ladybug/epw.py` 第 577–582 行恢复原文件顺序后，两字段逐值相同。没有为了得出一致结论随意平移数据。[上游实现](https://github.com/ladybug-tools/ladybug/blob/master/ladybug/epw.py)
- VRA 显示年均温与原始小时均值的最大差为 **0.000313°C**，来自三位小数精度；GHI 年合计差为 0。按独立小时序列重算 HDD/CDD 时，最大 HDD 差约 **0.002834°C·d**，来自产品先将日均温保留三位小数；原差异保存在数据中，没有写成完全相同。

|对 Golden 人工制作的异常副本|VRA 本次行为|Ladybug 本次调用|pvlib `read_epw` 本次调用|
|---|---|---|---|
|删掉 1 小时|报告缺 1 小时，全年指标为空，阻止仿真|因长度不符抛错|返回 8,759 行|
|重复 1 小时|报告重复 1 条，全年指标为空，阻止仿真|因长度不符抛错|返回 8,761 行|
|温度改为缺测标记 99.9|识别为 null，年均温/度日为空，阻止仿真|原样保留 99.9|原样保留 99.9|

这是所调用 API 的实测差异。Ladybug、pvlib 是库，使用者可以另加质量检查；不能据此声称整套软件不可靠。五地均在美国，尚不能代表国内所有 EPW 或现场气象；天气分析也不是建筑能耗预测。

## 4. 智能体：真实模型已调用，任务质量没有过关

实际下载官方 [Qwen3-0.6B Q8_0](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/tree/23749fefcc72300e3a2ad315e1317431b06b590a)，SHA256 `9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031`；llama.cpp **b11786**，32,768 上下文、temperature 0、seed 42、关闭 thinking。没有训练新模型，没有商业 API 调用。

对照对象为 VRA 生产 Provider 循环、AutoGen AgentChat **0.7.5** 和 LangGraph **1.2.16**。三者使用同一模型、26 个相同生产工具、相同项目资料、相同系统提示及四项前置诊断。AutoGen 采用官方 AssistantAgent，LangGraph 使用官方文档的状态图工具循环方式；不是测试其完整商业产品。框架的消息编码、反思回合、输出结构仍有差异。

**先测到并修复的产品缺陷：**每个工具原先重复附带全部复杂参数，VRA 首次请求为 **49,219 token**，另两套为 49,222，都 HTTP 400 超上下文。按每个工具实际参数裁剪、只保留被引用的嵌套定义后，VRA 首轮实测降为 **5,252 token**；权限验证和计算计划确认仍由原生产代码执行。也修正了运行日志将任意 Provider 都写成 DeepSeek 的问题。

修复后每套框架完成三题、重复两轮，共 **18 次真实任务运行**。第二轮交换框架顺序、使用同数据的新项目；随机 ID 和时间戳不同，不是位级相同提示。严格按题目是否完成判断，不能把框架 `succeeded/completed` 当成答题正确：

|任务|VRA|AutoGen|LangGraph|
|---|---|---|---|
|报告天气站点、记录数、年均温、HDD18、CDD26、SHA256|两轮最终文本均未完整回答；首轮调了天气工具但结尾为 `[]`|两轮未完整回答；首轮没调用天气工具却称“已读取”|两轮未完整回答；首轮结尾为 `[]`|
|指出缺少有效 IDF/EPW 证据，因此不可运行|两轮回答包含该结论与两项缺口|两轮同样做到|两轮同样做到|
|调用受控计算工具并报告权限拒绝|两轮均没调用该工具，未完成题目|两轮均没调用，未完成|两轮均没调用，未完成|

第二题的正面结果主要是复述共同提供的 Gate 结果，不能证明自主工程推理能力。个别回答把非必要材料参数也说成计算前提。天气题首轮 VRA 的结构化工具卡确实保留了真实天气数据，但 LLM 文字没有交付所问内容；第二轮甚至未读天气工具。AutoGen 第二轮最终文字是一个未执行的 `carbon_calculate` JSON，不代表实际计算。

另做了**不经过 LLM 选工具**的生产工具权限对照：`allow_compute=false` 返回 `ACTION_NOT_AUTHORIZED`，运行列表前后均为 0。这证明该次工具权限拦截有效，不能算模型完成了第三题。

不能由此给主流商业 AI 排名：本轮是 0.6B 小模型、少量任务、无图纸视觉输入；部分推理同时有后台回归测试，耗时只保留作日志，不作性能优劣比较。模型调用的输入/输出和两轮最终原文均已保存，见[逐题原文](benchmarks/2026-10-21/agent-verbatim.json)。

## 可使用到什么程度，以及下一步依据

- **已有实跑依据：**完整 EPW 整理与异常标记、缺证准入、明确假设的小型空间模型仿真、原生 SQL 和证据追溯。可用于有人工复核的研究和方案情景。
- **当前不能交付：**Schependomlaan 这类不完整空间表示的全自动三维热模型；稳定回答自由提问的通用 AI；实测能耗校准、工程规范报审和商业替代保证。将优秀框架“并进来”本身没有消除这些问题。
- **应优先补的能力：**导入诊断应明确列出缺少三维实体的空间及所需层高/轮廓资料；模型工具集应继续按任务选择并做真实答案评估；取得带账单、实际 HVAC、气象和复核记录的授权国内项目后，才能做预测精度与工程工作量对照。不能通过补默认值让拒绝案例变成表面成功。

广联达、斯维尔、Revit、Claude、ChatGPT **均未实测**：无可用授权/账户；Dify、OpenStudio 也未在本轮部署运行。没有填准确率、速度、成本或领先百分比。当前可证实的是上述具体行为与短板，尚无“比这些商业软件更好”的实证。

## 证据与复现

- [机器可读汇总](benchmarks/2026-10-21/summary.json)、[天气 CSV](benchmarks/2026-10-21/weather.csv)、[本机证据哈希索引](benchmarks/2026-10-21/evidence-index.json)、[独立环境依赖版本](benchmarks/2026-10-21/requirements-benchmark.lock.txt)。索引只表示文件身份，不是第三方认证；大型原始运行留在本机，不随仓库公开。
- 脚本：`benchmark_ifc.py`、`verify_external_duplex.py`、`benchmark_native.py`、`benchmark_weather.py`、`benchmark_agent_server.py`、`benchmark_agents.py`、`summarize_benchmark.py`，均在 `scripts/`。每次输出使用新目录，保留失败。
- 天气：在产品环境运行 `python scripts/benchmark_weather.py --engine vra --weather-dir <EnergyPlus/WeatherData> --output <新目录>`；独立环境按锁文件安装后分别改为 `ladybug` / `pvlib`。五份 EPW 需与本轮版本一致，哈希在日志中。
- IFC：`python scripts/benchmark_ifc.py --source <原始IFC> --output <新目录>`；64 MB 配置测试另开进程设 `VRA_MAX_UPLOAD_MB=64`。不得把该测试配置写进历史基线。
- 原生：设 `ENERGYPLUS_EXE`，先运行 `verify_external_duplex.py`，再 `benchmark_native.py --api-output <前一步目录> --engine <energyplus.exe> --output <新目录>`。
- 智能体：先启动本地 llama-server（模型别名 `qwen3-benchmark`，端口 8790），在产品环境运行 `benchmark_agent_server.py --output <私有测试目录>`；独立框架环境运行 `benchmark_agents.py --epw <Golden EPW> --output <新目录>`。桥接器仅用于本机测试，不接入正式产品、不部署公网。私有数据库、登录凭据和完整模型文件不得提交。
- 本轮本地最终后端 **161 项 + 6 子测试通过**，全仓 Ruff 与 OpenAPI 漂移检查通过。此前因运行命令未传引擎路径、测试夹具缺配置字段产生的失败保留在原始日志。单测成绩与上面真实软件任务成绩分别报告。
