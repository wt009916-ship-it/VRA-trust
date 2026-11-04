# 2026-11-04 第一批审计修复验收

基线：公开提交 82774468d598156b62f96ea4d9708160170770ee，原审计46/100。开发副本 work/vra-hardening-20261104，分支 fix/audit-p0。原审计源码/报告未改写；原本 vra-trust 的两处未提交改动也未触碰。此文不是新的独立百分制评分。

## 修改与关闭状态

|编号|改动|验收|剩余边界|
|---|---|---|---|
|D01|恢复首管理员Provider配置/测试API和UI；沿用DPAPI；测试连接不执行工具|原失败2项通过；新增测试验证非管理员403和测试请求不执行变更工具；浏览器保存无Key关闭配置成功|真实Provider联网仍未验收，未使用任何真实Key|
|D02|区分workflow_completed与task_completion；local明确仅准入且无记忆；前端不把流程成功说成专业任务完成|自由文本结构任务回归通过|只修复误导状态，未实现自主规划/记忆|
|D03|IDF必需对象、材料正值；EPW八头、35列、完整有序年度小时检查；编码错误归为INVALID_SOURCE|头文件模型、损坏天气、负λ、重复时刻被拒绝；真实参考输入通过|有限预检，非完整IDD解析或工程适用性认证；只支持声明的全年小时/详细表面工作流|
|D04|建筑、空间、因子、搜索的数字改为StrictFloat/StrictInt|布尔与数字字符串拒绝；正常JSON数值通过|不推断混合单位；数值客户端须按契约发送number|
|D05|碳乘积/合计、能源单位换算和EUI输出有限性验证|乘积和合计溢出、SQL换算溢出回归通过|无完整量纲系统/全业务极端输入穷举|
|D06|SQL按月日小时检查唯一完整日历和每段60分钟，含闰年；parser升级0.3.0|缺失/重复/非法日期/0+120分钟均拒绝；原生年度SQL通过|历史运行因物理代码hash改变保守stale，需新运行；不改旧hash|
|D13|移除活动前端未用echarts/html2canvas/jspdf；Vite在原semver范围更新至8.3.5并锁定传递依赖|npm audit 0；构建、13前端测试、lint通过|仅npm公告库结果；不是全系统安全认证；legacy源码不作为独立应用安装验收|

## 最终证据

- validation/p0/pytest-final-v2.log：101 passed，6 subtests passed，无跳过；有一条Starlette/httpx弃用提示。
- validation/p0/native-final.log：31项专项检查通过；3个参考方案+3个反例搜索真实EnergyPlus；碳重算0次引擎调用、源文件不变。
- validation/p0/reference-final.log：另3个真实参考运行；能耗57193.23/55715.19/55592.10 kWh，与原审计一致。原生SQL和ERR保存在runs及validation/trust-slice。
- validation/p0/frontend-delivery.log：13 passed；build-delivery.log构建成功；frontend-lint.log/ruff-final-v2.log通过。Three.js大块提示仍存在，不把构建通过当性能验收。
- validation/p0/npm-audit-after.json：0 known vulnerabilities（本次查询）。
- validation/p0/provider-restored.png：真实浏览器打开并保存关闭的无Key配置。未请求付费服务。
- shared/schemas/openapi.json已重新导出；JSON Schema本身不能表达Pydantic严格类型全部运行规则，API回归为准。

## 环境与运行

Python3.14.2、Node24.22.1、EnergyPlus9.0.1，复用审计隔离venv。精确Python3.12/Linux/Docker尚待验证。测试数据库全部在validation。早期测试/仿真记录保留；后续校验器hash纳入code_hash后重新运行，最终证据以final命名日志为准，旧运行不得绕过stale。

可以在此副本按README创建.venv后启动。运行数据不随代码提交。本批只形成独立本地修复分支，没有推送GitHub或部署公网。

## 结论

第一批是关闭已复现缺陷和收紧能力声明；未重打总分，更未宣布达到100。下一批先补独立热工计算及因子来源可信状态，再扩Agent任务闭环，随后图纸/BIM与规范。每批必须附独立输入/失败反例/真实输出与阶段报告。
