# 建模、开发者 API 与智能体集成版 · 2026-10-20

本次把原来的手工几何展示扩展为实际的“资料解析 → 候选复核 → 空间模型 → IDF → EnergyPlus → 可追溯报告”流程。此链路在简单人工构造样例中通过，尚不具备通用 IFC 自动转换能力。2026-10-20 使用未修改的外部 Duplex 住宅 IFC 实测，21 个空间候选读入后因棱柱化重叠被拒绝，未生成 IDF 或能耗结果；见 [外部样例验收](EXTERNAL_SAMPLE_AUDIT.md)。既有材料决策、证据准入、账号隔离和碳排选择性重算继续使用。

## 已接入的开源组件

|组件|实际用途|上游|
|---|---|---|
|ezdxf 1.4.5|读取 DXF 直线、无圆弧轻量多段线及长度单位|https://github.com/mozman/ezdxf|
|pdfplumber 0.11.10|提取矢量 PDF 的直线端点、矩形、直线路径与文字定位|https://github.com/jsvine/pdfplumber|
|IfcOpenShell 0.9.0.post1|提取 IfcSpace 水平底面，导出实际 IFC4 空间实体|https://github.com/IfcOpenShell/IfcOpenShell|
|Shapely 2.2.0|闭合线环、有效多边形、重叠和邻接检查|https://github.com/shapely/shapely|
|LangGraph 1.2.16 + SQLite checkpoint 3.1.2|持久化识别、人工中断复核、恢复与模型保存流程|https://github.com/langchain-ai/langgraph|
|MCP Python SDK 2.3.0|外部智能体通过标准 stdio MCP 调用项目 API|https://github.com/modelcontextprotocol/python-sdk|
|Three.js 0.185.1|交互三维、房间选择、透视；二维平面作为回退|https://github.com/mrdoob/three.js|
|EnergyPlus 9.0.1|复用真实执行器、原生 SQL/ERR 核验及报告链|https://github.com/NREL/EnergyPlus|

这些组件已被代码实际调用。没有整体合并 Dify、Flowise、OpenHands 或它们的账号系统；外部智能体经 MCP/HTTP 接入，工程权限和结果校验由本项目统一执行。没有加入仅允许非商业使用的图纸模型权重。依赖许可快照见 `third_party_notices` 和 `DEPENDENCY_INVENTORY.json`；IfcOpenShell 及其随附原生组件的许可不能被统一标成 MIT。

## 使用步骤

1. 建立自己的账号与项目。项目地点、面积、用途应来自项目资料。
2. 打开 **建模工作区**，选择 DXF、PDF、IFC 或图片。DXF 优先指定房间边界图层；PDF 指定页码和米/point；图片指定米/原图像素。PDF 视觉通道按 72 dpi 渲染。DWG 先在原软件导出 DXF。
3. 展开持久化任务，检查候选与警告，合并到编辑区。逐间修正顶点、层高、标高、遗漏与来源；可添加房间或复制到上一层。3D 为房间棱柱表达，不是施工级 BIM。
4. 填写热工参数和依据。可逐层输入墙、屋面、底板的厚度、导热系数、密度、比热；U 值由材料层推导。仅填 U 值时使用无热容构造，报告保留该限制。“填入教学假设”仅供演练，不代表真实建筑参数。
5. 写复核说明并确认空间，保存新版本。必要时把模型面积同步到项目声明。已有结果会重新校验版本。
6. 选择 baseline/R1/R2，填写发布复核人及说明，生成 IDF 并登记证据。再在“资料”上传并复核适用于项目的 EPW 天气，准入通过后才能计算。
7. 查看真实排队、运行、失败、失效状态，下载 IFC、IDF、JSON、HTML、PDF 和原始证据。仅排队任务支持取消；运行中任务依照既有超时机制结束。

### 模型版本与方案

编辑模型产生新版本，已发布方案仍绑定其发布时的模型快照。这样可以保留 baseline、编辑 R1 并比较，不能把所有旧方案在草稿变动时一并覆盖。向同一方案重新发布时，旧 IDF 证据成为新版本的拒绝记录，相应旧结果失效；历史文件不改写。重复提交同一发布操作会复用结果。

### 输入边界

- DXF 识别闭合线环，不能自动区分房间、家具、图框、墙厚。块、圆弧、任意三维 CAD 和直接 DWG 解码尚未支持。
- 矢量 PDF 保留直线方向，曲线不会被包围盒冒充。扫描 PDF 需要视觉通道；没有比例就拒绝猜尺寸。
- IFC 需要可提取的 IfcSpace；缺少空间、带孔底面、复杂网格会提示失败或跳过。斜屋面、曲面、墙层、门窗没有自动转译为热模型。
- 单次最多 100 个房间；导入图元数量及上传大小受限。导入过程是有界同步请求，候选和复核节点持久化，尚不是可水平扩容的分布式任务集群。
- 房间需为无孔、无自交的简单多边形，体积不能重叠；部分叠层、错层邻接会拒绝，需先拆分对齐热区。

## 开发者模式

管理员侧栏 **开发者设置** 支持配置兼容 Chat Completions 协议的完整 endpoint、文本模型、视觉模型、API Key，并测试连接。默认保留 DeepSeek 接口；第三方 endpoint 支持 HTTPS，本机调试允许回环 HTTP。模型名不是“选择一个名字即可兼容所有厂商”，目标服务必须支持对应文本工具或视觉协议。

Windows Key 用 DPAPI 保存于私有运行目录；前端不持久保存 Key。切换 endpoint 时必须明确替换或清除已存 Key，避免把旧 Key 发送给其他服务。`DEEPSEEK_API_KEY` 只用于默认 DeepSeek 地址；通用服务可显式提供 `VRA_API_KEY`。

视觉识别还要求每次勾选发送当前图页到配置服务商。返回的是 `AI_INFERRED` 空间候选，必须人工复核。实际服务商 Key 和联网识图尚未验收；自动化测试只证明请求协议、结果校验及拒绝路径。没有 Key 时不会伪造 AI 识别成功。

## 外部 Agent / MCP

项目内 **项目 API / MCP** 可创建 1–90 天项目专属 Token，选择 read、write、compute 权限，支持撤销。原始 Token 只显示一次，服务器仅保存哈希。Token 不授予其他项目或开发者配置权限。浏览器继续使用原有账号会话和 CSRF。

MCP 客户端配置示例（将路径及占位值改为自己的配置，不提交真实 Token）：

```json
{
  "mcpServers": {
    "vra-trust": {
      "command": "D:/your-project/.venv/Scripts/python.exe",
      "args": ["D:/your-project/scripts/run_mcp.py"],
      "env": {
        "VRA_BASE_URL": "http://127.0.0.1:8766",
        "VRA_PROJECT_ID": "project_这里替换为真实项目ID",
        "VRA_API_TOKEN": "这里填写该项目Token"
      }
    }
  }
}
```

提供八个 MCP 工具：读取项目、读取模型、模型准入、证据列表、计算准入、导入任务列表、运行列表、提交仿真。提交要求 `confirm_compute=true`、Token 的 compute 权限和工程准入同时通过。适配器调用 HTTP API，不直接访问数据库。修改/发布模型可通过完整 HTTP API；MCP 当前有意只暴露上述八个工具。内置助手注册表现为 25 个受控工具。

HTTP API 契约在 `/openapi.json` 与 `shared/schemas`。主要新增入口为项目下的 `/model`、`/imports`、`/model/validate`、`/model/publish`、`/model-runs` 和 `/tokens`。

## EnergyPlus 的含义

从模型生成 9.0 IDF；每个房间一个热区，确定相邻墙及对齐楼板的配对边界，生成围护构造、窗、内部负荷、时刻表和 IdealLoads 系统。任务排队后调用实际 `energyplus.exe`，核对退出码、全年覆盖、严重 ERR、SQL 单位/面积与各能源之和，失败不降级为估算。

**本次自动生成模型计算理想冷热需求。District Heating / Cooling 不是热泵耗电。** 当前没有真实 HVAC 设备效率、风机水泵、新风湿度控制、节假日差异、相变潜热或温变物性；土温为用户填写的全年常数。分层材料支持显热热容量，不能据此宣传稀土或相变材料已被验证。

当前执行器限定 EnergyPlus 9.0.1。新版本引擎与转换工具链尚未集成验收。既有导入 IDF 流程保留原模型 HVAC；自动建模流程的简化不能套用到所有导入模型。

## 启动与部署

发布 ZIP 包含已构建前端。安装 Python 3.12 后运行 `Setup.ps1` 安装依赖，再执行：

```powershell
./Start.ps1 -EnergyPlusPath 'F:/EnergyPlusV9-0-1/energyplus.exe' -Port 8766
```

首次创建自己的账号；没有预设正式用户。源码构建前端需 Node 22+；开发验证用 `Setup.ps1 -Development`。`Start.ps1` 可用 `-DataDirectory` 指定持久运行目录。

本轮限定本机单个服务进程（`--workers 1`），同一进程内 EnergyPlus 串行。不能把进程内信号量宣称为跨进程任务锁；不要多个服务实例共享同一运行目录。团队共享、备份恢复演练、并发压力、云部署、第二台电脑、真实项目校准与商业验收仍需后续工作。

## 本轮验收证据

`scripts/verify_building_workbench.py` 在独立目录创建合成两房间 DXF，执行导入、LangGraph 人工复核恢复、IFC 导出、IDF 发布、真实基准/R1 计算、报告下载和旧版本失效。源尺寸 80 m²，材料与运行参数为明确教学假设，天气来自官方 Golden 参考文件。两次最终计算均零 warning。

基准总量 8422.20 kWh，R1 为 8461.85 kWh；两者电量均 4088.00 kWh。基准采暖/制冷需求分别 1327.87/3006.33 kWh，R1 为 818.91/3554.93 kWh。这个算例表明保温情景未必降低全年需求，不是项目节能率或工程性能证明。

真实 stdio MCP 验收验证发现八个工具、项目绑定、工程准入、计算显式请求、只读拒绝和 Token 撤销。旧材料决策实际三次仿真通过 30 项检查；官方参考 baseline/R1/R2 也重新运行成功。测试总数以交付验收清单为准。

复验时先安装开发依赖并设置 `ENERGYPLUS_EXE`。以下命令各自创建隔离数据和随机测试账号；输出路径须为未使用的新路径，保留旧结果：

```powershell
.venv/Scripts/python scripts/verify_building_workbench.py --output validation/building-new
.venv/Scripts/python scripts/verify_mcp_adapter.py --output validation/mcp-new.json
```

MCP 脚本自行启动临时回环 HTTP 服务，验收后关闭，不依赖浏览器登录或固定端口。它不调用 EnergyPlus、不请求外部 Provider。

浏览器已操作过 DXF 上传、候选合并、参数填写、复核保存、三维工作区和 IDF 发布。未完成跨浏览器、移动端、屏幕阅读器或开发者设置全部交互验收；没有据此声明全部界面已验收。
