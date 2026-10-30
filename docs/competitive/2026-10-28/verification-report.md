# Verification Report：VRA-Trust竞品与工程复核
*Skill: startup-competitors | Generated: 2026-10-28*

## Summary

- **Critical issues：0**：本次核对未发现接受假设绕过物理Gate、来源升级为实测、商业性能胜出或市场唯一的明确路径/表述。
- **Outstanding warnings：0**：此前2项产品问题与2项文档问题均已修复并复查。
- **Addressed warnings：4**：已拒绝历史证据误报、全局参数差异过粗、LCA/长期现金流混列、战卡缺口与错误来源入口。
- **Info / 发布核对：已完成**：独立实际运行4个针对性用例；另已逐项核对主线程最终日志、4份公开JSON、来源/日志哈希、引用与脱敏边界，未重新运行全套。

[Data，代码/独立回归置信高；市场覆盖置信中] 按verification-agent协议读取主报告、矩阵、价格、6份战卡、engineering_review.py、review_api.py、review-ui.js、相关权限/存储/测试，并在最新代码复跑4项针对性回归，结果4 passed、10 deselected。没有修改产品代码、登录商业竞品或接触正式项目。此报告不是全量安全审计或客户效果验证。

## Critical issues

无已确认关键问题。当前定位与官方能力核对保持保守：BCF、API、AI、自动建模、校准、审计证据及Pareto均不作为行业独有声明；商业竞品没有合法账号同题实测，因此未编造精度、速度、报价或人工工时优势。

## Addressed warnings

### A1 · 已拒绝历史证据与当前输入分开

[Data] 首轮独立API曾复现：仅登记且拒绝的bill、不被模型引用，其原件损坏仍新增两个当前BLOCKER。最新_snapshot先筛选非rejected活动证据，model.sources单独保留来源校验。独立重跑`test_retired_evidence_source_is_not_a_current_blocker_unless_model_still_uses_it`通过：历史无活动引用不误报；同一原件仍被当前模型引用时继续BLOCKER；历史记录保留。

原首轮复现留在../competitive-20261028/verification-runtime；复核使用新目录verification-recheck-28，不回写原记录。

### A2 · 全局热工/设备/来源变化展开

[Data] 首轮thermal/equipment/sources整体只输出哈希/项数，工程师看不出具体参数。最新model_changes热工递归字段、构造层按位置、设备按zone_id、来源按file_id比较。独立重跑两项参数差异用例通过：thermal.heating_c显示20→21；equipment[R2].cooling_capacity_w显示5000→6000，room_id为R2；新增/移除空间仍依稳定ID而非相似名字。大几何数组保留摘要，文档已明确这一限制。

### A3 · 碳/LCA与长期现金流分开

[Data] 首轮矩阵合并“完整LCA/长期经济性”，容易被读成两维全部已核实。最新改为“生命周期碳模块/集成”与“完整长期经济现金流”两行，后者未知写?；与主报告关于VRA仅运行碳和增量初始造价的限制一致。

### A4 · 战卡缺口与来源入口

[Data] 国际3卡已增加Data Gaps，Honeybee卡不存在的research.md引用已改为竞品主报告入口。国内3卡的“数据缺口”语义相同且有红/黄旗与来源。逐产品版本、SKU、地区与未实跑状态保留。

## Info / 发布核对

1. [Data] 同题输入清单已增加registered_simulation_inputs，由Gate实际selected_evidence映射IDF/EPW角色、证据ID、revision、源文件与hash、性质及复核状态。独立重跑`test_comparison_contract_keeps_selected_evidence_role_and_revision`通过。清单仍明确需人工匹配天气、计量、范围与指标，不把文件清单当自动模型等价性证明。
2. [Data，最终发布核对完成] docs/ENGINEERING_REVIEW.md及docs/benchmarks/2026-10-28-engineering-review/README.md与4份JSON均已生成；本地相对引用有效。实际读取日志确认：完整后端309 passed、6 subtests passed，431.79秒；此后后台元数据集成相关19 passed，69.65秒；前端49 pass、0 fail。公开记录正确区分先后范围，没有将19或独立4项加到完整测试数。正式8767日志核对为健康/前端200、匿名项目/后台数据库401，原1账号/4历史项目版本/0归属行指纹保留，无密码重置或公网部署。
3. [Data，最终证据核对] public-workflow.json与current-exports.json逐项等于其仓库外原记录；bcf-interoperability.json的读取器/Schema结果与原记录一致，8/138主题、148 XML及公开XSD哈希均匹配。checks.json列出的执行源码、Git LF源码和私有日志SHA256逐项匹配当前文件。4份JSON语法有效；本次扫描未发现明文密码/令牌/私钥、私人账户资料、运行目录路径或原包。没有把保留的27份原生年度证据算成本轮新计算；其引用核对记录明确新增年度运行0。

## Verification checklist

- [x] 主报告/矩阵明确官方说明与本项目实跑之别；无商用性能排行榜。
- [x] 市场唯一、API/BCF/AI独家与稀土实测优势未当作事实。
- [x] 数据缺口、红/黄旗、商业SKU/地区/版本边界存在。
- [x] 未发现同厂商两个页面被冒充独立效果验证。
- [x] 价格/许可边界与战卡基本一致。
- [x] 当前/历史证据修复经独立针对性回归复核。
- [x] 参数级差异与稳定ID绑定经独立针对性回归复核。
- [x] 同题输入Gate角色/证据版本映射经独立针对性回归复核。
- [x] ENGINEERING_REVIEW.md已创建，真实性限制与实现匹配。
- [x] 最终完整/晚期专项/前端日志计数与先后范围一致；4 JSON及引用/哈希/脱敏核对完成。

## Data Gaps

[Data] 没有商业软件同版本实跑、可靠中国报价、客户工时/准确度或付费数据。旧手册只能证明能力沿革，不能断言竞品没有完整假设台账/语义差异责任链。独立本轮只实跑4个用例；主线程完整309+6、晚期19及前端49均已读取最终日志确认，没有将读取日志描述为独立重跑或把测试源码提升为运行成绩。

## Red Flags

[Data] 无已确认关键误导或不安全放行问题。仍不能对外称已替代成熟工程软件、具备客户现场校准准确度或可签发工程成果。

## Yellow Flags

[Data] 已完成本轮发布资料核对，但这不扩大到商业软件GUI互通、完整交付签署或客户工时收益。全局保守复核失效是当前设计取舍，不是逐构件选择性物理重算；这些仍须工程师试点。

## Sources

- 本地：docs/competitive/2026-10-28/全部9份Markdown；docs/ENGINEERING_REVIEW.md；backend/engineering_review.py、review_api.py、domain.py、store.py、api.py；frontend/src/review-ui.js；tests/test_engineering_review.py。
- 独立实际执行：../competitive-20261028/verification-recheck-28.log：4 passed、10 deselected（2026-10-28）。
- 最终发布核对：docs/benchmarks/2026-10-28-engineering-review/README.md及4 JSON；仓库外pytest-current-complete.log、pytest-admin-final.log、frontend-production-final.log、formal-checks.json、BCF读取/Schema和原API记录。
- 官方比对：[DesignBuilder版本](https://support.designbuilder.co.uk/support/solutions/articles/103000294299-designbuilder-new-version-feature-list)、[IES BIM](https://www.iesve.com/software/bim)、[iSCAN](https://www.iesve.com/products/iscan)、[OpenStudio校准报告](https://openstudiocoalition.org/getting_started/running_your_simulation/)、[cove许可变更](https://cove.inc/education-resources/)。它们不是本轮商业软件运行成绩。
