# 工程复核与交接验收 · 2026-10-28

本轮验证[工程复核](../../ENGINEERING_REVIEW.md)的实际操作与来源约束，不扩大[复杂建筑计算](../../HIGHRISE_MODELING_ACCEPTANCE.md)的物理适用范围。公开住宅FZK与真实De Zalmhaven结构原件分别产生7/299空间、8/138复核条目；后者仍是缺立面、机电与用途依据的候选模型，不能称完整高楼热模型。

|记录|实际内容|
|---|---|
|[public-workflow.json](public-workflow.json)|原件哈希、实际API导入/处置/导出、接受假设不放行、旧处置失效与409、稳定空间ID版本差异|
|[current-exports.json](current-exports.json)|最终规则下重新导出的快照/交接包哈希核验；两项目仍被Gate拒绝，均未签署|
|[bcf-interoperability.json](bcf-interoperability.json)|独立bcf-client读取8/138主题、148 XML通过官方BCF2.1 XSD；公开Schema来源与哈希|
|[checks.json](checks.json)|完整/针对性测试的先后范围、浏览器操作、执行与Git规范化源码哈希、日志摘要、正式库保留检查|

完整后端为309项及6子测试；此后后台数据库展示元数据集成，相关19项再次通过。前端49项、Ruff、前端检查、契约导出、生产构建通过，npm audit为0。独立复查另实际运行4项针对性用例，不能与完整测试相加当作更多测试覆盖。构建仍提示Three.js大分块。

Playwright实际验证处置必填/保存/待审筛选、FZK问题定位R7、高楼第38层两条问题定位且保留299空间；1440/1024/390宽度无页面横向溢出。BCF仅问题文字，无相机、截图、模型选择或双向同步；未验收商业BIM客户端GUI导入。校验器安装在仓库外隔离目录，没有增加产品依赖。

本轮不新增原生全年仿真。物理核心未改，27份既有年度运行的文件哈希与当前引用已复核有效；不能把这些算作本轮新运行或更多独立建筑。来源文件沿用[既有冻结来源记录](../2026-10-27-complex-modeling/sources.json)，没有重新分发授权未明确的原件。

JSON中的工作流快照与最终导出快照属于不同时间点；复核规则及名称版本变化会产生新哈希，历史不改写。`tested_base_commit`为测试开始前提交，实际工作区实现由源码哈希标识；Git统一LF，所以另外记录`git_lf_source_sha256`。数据库、密码、完整请求轨迹、交接包及原件保存在仓库外，不包含在公开记录中。

复跑代码测试可用 `python -m pytest -q`、`python -m pytest -q tests/test_engineering_review.py tests/test_admin_database.py`，前端目录执行 `npm test`、`npm run lint`、`npm run build`；完整测试需具备项目依赖和文档规定的本机原生工具。商业同题对照仍需合法授权、同一输入及独立工程师参与，不能由测试通过推导市场领先。
