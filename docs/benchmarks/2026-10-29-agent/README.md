# 智能体接入、策略修订与真实任务评测

本轮把腾讯TokenHub模型接入现有工程工作台，新增资料检索、计量检查、源构件和工程复核工具。**这是智能体策略与工具调优，没有训练DeepSeek模型权重。** 任务执行通过不等于工程语义全部正确或正式校准通过。

## 服务接入与失败保留

用户实际使用腾讯TokenHub，接口为`https://tokenhub.tencentmaas.com/v1/chat/completions`，模型`deepseek/deepseek-flash`。先前配置成DeepSeek官方接口导致10次401；这些失败保留在[错误平台记录](wrong-provider-results.json)。用户提供腾讯调用样例后，备份加密配置，改为明确指定的腾讯地址、匹配模型，再以最小请求实际通过。原始Key未进入仓库、报告或模型提示。

已核对[腾讯调用说明](https://cloud.tencent.com/document/product/1823/132248)与[模型列表](https://cloud.tencent.com/document/product/1823/130051)。对已确认协议显式关闭思考，以减少纯工具核查中非必要token；不保存隐藏推理。后台预设区分DeepSeek官方与腾讯，真实连接测试完成工具协议往返，工程工具执行0次。

## 任务来源与方法

复用[前轮已核验BDG2原始数据](../2026-10-28-real-engineering/README.md)，原始电表SHA256为`039d909d8981e2d69eaeb366144e6ab7e84fa5e7e216aee42bddd95384a66418`。20栋匿名实测建筑的2016年1月子集，涵盖缺测、整月无读数、全零以及正常序列。不是20个完整建筑几何或15独立工程验收。

数据在隔离数据库副本上运行，正式用户和项目不用于自动验收。固定开发组：按有效行排序取前5栋，再取5栋检查通过者；其余10栋为本次策略修订的留出组。策略不硬编码每栋建筑答案。模型先获得有限初始上下文，再被要求自行调用`measurement_audit`复核。记录区分workflow预设工具与origin=model的自主工具，不能把预读取冒充模型自主调用。

自动检查依据：任务/解释状态、真实模型请求数、模型自主调用名称、工具摘要与已验收原件逐项一致、是否新增计算任务、模型返回token用量。**没有把自动检查当作人工语义准确率。**

|阶段|完成情况|保留的失败或发现|
|---|---|---|
|首轮腾讯真实任务|4/10完成|6个网络/连接超时；有一任务墙钟耗时约2713秒，未据此发布速度或SLA保证|
|修订后开发组|10/10任务完成，20次模型请求，51,635个报告token|人工发现匿名标签August被误当月份，以及对计量比较授权的说明不严谨；继续修订|
|最终策略留出组|另一10栋10/10完成，20次模型请求，55,183个报告token|10栋均自主调用measurement_audit；工具摘要逐项匹配；不签发校准或工程准确率结论|

最终留出组观察到单任务约5.4–7.1秒，仅为本机、该轮网络、当前配置及限定任务的观测，不是生产性能承诺。先前网络失败并未删除或改写。

[首轮真实调用](first-live-results.json) · [开发组逐项结果](development-results.json) · [最终留出组逐项结果](holdout-results.json)。公开摘要省略完整模型答复，完整任务与策略哈希保留在本地；已知语义问题按上表披露。

## 资料与图纸真实验证

Fraunhofer IEA EBC Annex71公开双屋试验建模说明，作者Matthias Kersken与Paul Strachan，2020-04-27，CC BY-SA4.0，[官方来源](https://fordatis.fraunhofer.de/handle/fordatis/161.2?locale=en)。原PDF SHA256 `0cfdc5d5a0a73362b4195ed53c5ca95493c7b2a50c64d10a14403047f73d5180`，实际本地解析61页。

真实浏览器勾选「允许AI读取资料摘录」，提问heating试验设置与校准适用性。模型完成答复，使用5条本次检索引用，涉及PDF页1/3/4/5/31；引用ID全部来自当次工具，没有未知ID。模型指出其为第三方参考实验说明，不能证明当前项目中央系统现场校准。**引用ID校验不等于自动证明每项语义引用正确**，原文仍需工程师复核。[任务答复及引用校验](document-task.json) · [检索来源定位](document-search.json)。该外部文献作为跨项目参考输入，不宣称与NIST属于同栋建筑。

腾讯视觉接口另实际读取1936 HABS再版老图公开裁片，输出`COACH HOUSE`、`STABLE`，与图上文字一致。仅验证视觉接通与该图文字抄录，**不计复杂图纸空间/热建模成功**。[请求范围与返回](vision-probe.json)。

## 功能及回归

- 共29项工具；新增4项只读工具，保留原有计算准入、结构化计划、项目归属与防重复提交。
- 资料摘录须逐任务授权；原件/人工校正/证据版本绑定，拒绝跨项目、哈希变化和已拒绝资料，摘录有长度与页面预算。
- 大型模型发送有显式裁剪，完整工具结果留在任务历史；外部失败仍保存已执行工具结果，状态为部分完成。
- 后台数据库加入智能体任务、计量检查与比较，模型配置加入腾讯/官方预设，Key不回显。
- 初次完整回归345通过、1个四参数工具适配兼容失败；修复后41项相关回归、最终策略11项通过。最终完整后端、前端53项及正式更新结果见[checks.json](checks.json)。
- 真实浏览器完成来源链接、5条引用展示、TokenHub预设、连接测试HTTP200/协议往返/工程动作0；1440/1024/390页面无横向溢出。

## 可复跑

先执行`scripts/verify_public_meter_data.py`得到独立的20栋计量验收目录，再将模型配置保存在本机后台。脚本只复制该隔离数据，Key保持加密保存；当前实测主机为Windows DPAPI。

```powershell
.venv/Scripts/python.exe scripts/evaluate_agent_public_meters.py --dataset-runtime D:/meter-acceptance/runtime --provider-config D:/local-runtime/private/provider.json --output-dir D:/agent-development-new --partition development --cases 10 --execute-provider
.venv/Scripts/python.exe scripts/evaluate_agent_public_meters.py --dataset-runtime D:/meter-acceptance/runtime --provider-config D:/local-runtime/private/provider.json --output-dir D:/agent-holdout-new --partition holdout --cases 10 --execute-provider
```

真实API调用会产生服务商费用。新目录保存策略与代码哈希、逐任务结果、网络失败和token；不重复使用已有输出目录，不把failed/partial改成成功。401/402/403后停止剩余批次。无需公开或提交provider.json。

本轮仍不覆盖自主可靠修复复杂高楼、客户中央冷站校准、未知设备参数恢复、材料现场实证或任意工程的独立交付。BDG2派生数据摘要及Fraunhofer文献派生说明沿用其署名和相同方式共享要求，未改变源代码现有许可状态。
