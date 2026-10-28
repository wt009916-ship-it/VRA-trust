# 文档中心

这里按产品使用、工程验证和开发维护组织资料。历史文档保留当时的失败与限制，最新状态以 [实现记录](IMPLEMENTATION_STATUS.md) 和对应的新验收证据为准。

## 使用产品

|资料|用途|
|---|---|
|[开始使用](QUICKSTART.md)|安装、初始化、资料清单、首个项目与常见阻断|
|[工程化路线](PRODUCT_READINESS.md)|目标用户、现有差距、试点与交付门槛|
|[建模工作区](BUILDING_WORKBENCH.md)|导入、空间复核、发布和 API/MCP；历史范围见文中日期|
|[复杂建筑输入](COMPLEX_MODELING.md)|斜面、墙板重建、建筑/楼层、源窗、绝对设备参数及显式近似|
|[工程复核与交接](ENGINEERING_REVIEW.md)|按源标识核对缺口与假设、参数变化、版本处置和BCF/输入协议交接|
|[竞品对标与取舍](competitive/2026-10-28/competitors-report.md)|国内与国际当前产品能力、价格/验证缺口及差异化方向|
|[图纸与热模型](DRAWING_THERMAL_ACCEPTANCE.md)|图页标定、候选识别、设备情景和适用限制|
|[气候与天气](WEATHER_WORKSPACE.md)|EPW 质量、NASA 日数据及两者用途|
|[材料与决策](CORE_DECISION_UPGRADE.md)|材料卡、证据、方案比较和造价口径|
|[后台数据库](ADMIN_DATABASE_CONSOLE.md)|成员、记录、修订、备份与权限|
|[身份安全](IDENTITY_SECURITY_ACCEPTANCE.md)|MFA、OIDC、邮件恢复及未通过项|

## 验证与适用范围

|证据|已测范围|阅读重点|
|---|---|---|
|[工程交接验收](benchmarks/2026-10-28-engineering-review/README.md)|FZK/真实高楼台账、版本失效、独立BCF读取与XSD、浏览器|不解除Gate，不把登记材料或账单当作实证；未作商业软件同题运行|
|[复杂建筑复测](HIGHRISE_MODELING_ACCEPTANCE.md)|16类控制形态、FZK/KIT整模、299高楼候选、设备/恢复|控制几何全通过；2公开参考整模全年成功；完整高楼仍有阻断|
|[前轮多样本与高楼](MULTI_PROJECT_ACCEPTANCE.md)|6份新增公开IFC、1控制场景、台北101格式准入|保留2026-10-26整模失败与3份局部成功，最新覆盖见上行|
|[公开输入与开源工具对照](EMPIRICAL_BENCHMARK_RESULTS.md)|五份 EPW、原生引擎、公开 IFC 与开源 Agent 框架|保留早期失败；不能推导商业软件领先|
|[图纸与热模型验收](DRAWING_THERMAL_ACCEPTANCE.md)|公开图页、Duplex、全年情景|几何误差、简化、设备范围与依赖许可|
|[复杂边界与 Qwen 修复](THERMAL_QWEN_REPAIR.md)|四组限定全年情景、真实模型调用、故障恢复|最新热网格结果；天气/用途仍是假设|
|[界面与账号验收](UI_ACCOUNT_HARDENING.md)|保存、重登、版本、真实界面与移动布局|原生密码库仍须单独验收|
|[身份与负载验收](IDENTITY_SECURITY_ACCEPTANCE.md)|Keycloak/Mailpit、双浏览器页面、本机 k6 负载|正式企业服务、密码库和独立生产环境仍未验收|
|[建模与恢复演练](COVERAGE_RELIABILITY_OPERATIONS.md)|分层解析、持久任务、备份恢复|原件/旧结果保留，异机灾备仍有条件|

## 开发与维护

- [开发与集成](DEVELOPMENT.md)：技术结构、检查命令、API/MCP 和数据边界。
- [API 契约](API_CONTRACT.md) 与 [机器可读 Schema](../shared/schemas/)。
- [部署说明](DEPLOYMENT.md)：本机入口、单进程约束、待验收的容器/公网配置。
- [计算重放](REPLAY.md) 与 [公开模型来源](OPEN_MODELS.md)。
- [版本记录](../CHANGELOG.md)：面向版本的功能导航。
- [实现与验收日志](IMPLEMENTATION_STATUS.md)：按时间保留开发记录，不作为操作手册。
- [最初审计](CURRENT_STATE_AUDIT.md)：旧代码与原始资料的历史起点。
