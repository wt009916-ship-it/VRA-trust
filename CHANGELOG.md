# 版本记录

当前为经功能分支和PR交付的工程预览，没有将Git提交包装成已签署的商业发行版。这里保留面向功能的演进导航；详细检查数、历史失败和修复过程见[实现日志](docs/IMPLEMENTATION_STATUS.md)。

## 未发布 · 产品入口与工程化复盘

- 增加老旧图纸增强、自动补接诊断、原图人工补接与新任务修订；独立工程构件/室内网格查看；四管制中央冷热源、水泵、盘管及设计JSON导入。可用范围和真实失败见[操作说明](docs/INCOMPLETE_DRAWINGS_AND_SYSTEMS.md)与[实测](docs/benchmarks/2026-10-28-drawing-systems/README.md)。
- 有界收紧几何公差、保留原空间及同平面窗面积预算；真实高楼仍有整模阻断。修复项目加载中切换工作视图被异步结果覆盖的竞态。

- 根据[新一轮竞品核对](docs/competitive/2026-10-28/competitors-report.md)收敛产品侧重点：增加工程复核、逐字段模型差异、版本绑定处置及同题输入/BCF交接，实际流程见[使用与验收](docs/ENGINEERING_REVIEW.md)。不将AI、BCF或校准宣称为独家能力。

- 复杂建模增加墙板空间恢复、闭合斜面、建筑/楼层组织、源外窗与逐空间PTHP铭牌/曲线，预算和适用边界见[操作说明](docs/COMPLEX_MODELING.md)。
- 源坐标/接触面网格一致化和旧引擎兼容修复；16类控制形态、2公开参考整模完成实际全年计算，真实高楼299候选仍有缺证阻断。原始失败与[本轮验收](docs/HIGHRISE_MODELING_ACCEPTANCE.md)分别保留。
- 前端采用polygon-clipping进行悬挑/错层楼面布尔运算；Vite升级8.1.6，依赖许可与清单同步。

- README改为产品介绍、真实界面、适用范围和开始使用；新增操作指南、文档中心及开发集成说明。
- 增加[工程就绪度评估](docs/PRODUCT_READINESS.md)，按工程输入、校准、材料、报告、智能体和发行定义后续验收门槛。
- 按用户要求扩大独立建筑输入测试，具体范围与结果见[多样本验收](docs/MULTI_PROJECT_ACCEPTANCE.md)。
- 真实新样本发现Honeybee可接受但EnergyPlus 9.0.1会终止的细小面/窗，补充实际序列化坐标的兼容性预检和定位；保留原失败，不删除几何放行。

## 2026-10-26 · 模型工作区与身份安全

- 常驻3D/2D、空间树、属性面板和校验/运行/版本区；保存、重登、版本和跨标签稳定性改进。
- TOTP、恢复码、OIDC和验证邮箱恢复，独立后台集中维护身份及邮件连接；本机负载和真实服务隔离联调。
- 首层热网格数值修复、Qwen调用预算/重试与说明失败处理；保留旧失败和来源性质。
- 验收：[界面与账号](docs/UI_ACCOUNT_HARDENING.md)、[身份与负载](docs/IDENTITY_SECURITY_ACCEPTANCE.md)、[热模型与Qwen](docs/THERMAL_QWEN_REPAIR.md)。

## 2026-10-23—25 · 资料优先与工程流程

- 批量收件箱、OCR/原图校正、资料修订、独立管理后台和内嵌数据库；项目中心、持久任务、草稿恢复与备份演练。
- 图纸标定、DXF扩展、IFC分层/带孔与重建诊断、独立几何审计、限定热泵和逐时运行输入。
- 验收：[资料与后台](docs/PROJECT_INTAKE_ADMIN.md)、[OCR](docs/DOCUMENT_OCR.md)、[图纸与热模型](docs/DRAWING_THERMAL_ACCEPTANCE.md)、[恢复与范围](docs/COVERAGE_RELIABILITY_OPERATIONS.md)。

## 2026-10-20—21 · 多格式建模与天气

- 解析候选、持久人工复核、空间到IDF、真实引擎、项目Token及MCP；EPW质量与NASA日气象分析。
- 使用公开IFC、五份EPW、原生CLI和开源Agent框架实际对照，失败与不充分证据保留。
- 验收：[建模工作区](docs/BUILDING_WORKBENCH.md)、[天气](docs/WEATHER_WORKSPACE.md)、[公开对照](docs/EMPIRICAL_BENCHMARK_RESULTS.md)。

## 2026-09 · 可追溯决策基础

- 项目证据、准入、原生SQL/ERR核验、同源报告、证据失效、碳因子独立重算与有限域反例。
- 材料卡、限定材料层方案比较、有来源初始造价和补证待办；参考模型与实测项目分开。
- 验收：[初始交付](docs/ROUND1_DELIVERY.md)、[Trust/Agent](docs/TRUST_AGENT_SPATIAL_DELIVERY.md)、[材料与决策](docs/CORE_DECISION_UPGRADE.md)。
