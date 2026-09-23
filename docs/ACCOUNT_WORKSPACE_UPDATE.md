# 账号与工作区改版 · 2026-09-23

按用户要求补齐真实用户登录，将长页工程面板改为接近 Codex 的工作区交互：左侧项目导航、中央任务区、独立资料/仿真/报告视图、按需展开的右侧详情。保留自有品牌。

## 账号

- 首次启动创建账号，后续支持注册、登录、退出与 12 小时会话。没有默认密码，没有测试账号写入正式 runtime。
- 首个账号在同一事务中接管既有无主项目；后续账号仅看到自己的项目。项目、文件、证据、运行、比较与报告下载均检查归属。
- 密码使用随机盐和 scrypt（N=131072、r=8、p=1）；会话 token 放在 HttpOnly / SameSite=Strict Cookie 中，数据库只保存 token 哈希。
- 写请求校验 CSRF token，拒绝跨 Origin / cross-site 请求；注册及登录限流持久化。
- HTTPS 部署须设置 VRA_COOKIE_SECURE=true；当前依旧只监听 localhost。本轮不是公网部署验收。
- 尚无邮件找回、邮箱验证、修改密码、团队共享/MFA，不是完整企业 IAM。

设计依据：[OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)、[Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)、[CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)。

## 工作区

- 浅色默认、深色可切换，侧栏可折叠；Ctrl/Cmd+K 搜索项目、Ctrl/Cmd+N 新建。
- 首页填写项目名称并进入建档表单；参考资料显式导入。
- 项目页分为工作台、资料、仿真、报告与依据；右侧按需查看建筑声明、准入、签署和证据索引。
- 中央输入支持受限项目操作：检查资料、导入资料、打开仿真和报告。未知指令明确反馈，不冒充 LLM 自由对话。
- 旧能耗核验、人工确认、版本失效、证据追溯和同源报告继续使用。

## 实际验收

- 70 项后端测试 + 6 subtests，含 9 项账号/权限测试；1 条 Starlette/httpx 弃用警告仍存在。
- 13 项前端测试，含名称注入转义和用户名 HTML pattern；语法检查和构建通过。
- 34 项带登录的真实 API Golden Path 检查通过。baseline/R1/R2 为 57193.23 / 55715.19 / 55592.10 kWh，仅官方参考算例。
- 浏览器在 validation/ui-auth-review 隔离库验证登录、参考导入、确认、真实 baseline（run_03a05c94ef07418eb0692f37a92467b5）、工作视图、深浅主题、详情、Ctrl+K 搜索过滤、退出登录。
- 浏览器自动化曾因过期元素定位超时，恢复后快捷键复查成功。
- 正式 runtime 保留旧项目/证据；正式账号由用户创建。Golden Path 改用独立数据库，不再污染正式库。

## 文件与边界

新增 backend/auth.py、frontend/src/layout.js、tests/test_auth.py；修改 backend/api.py、前端主入口/API/CSS、测试、真实 Golden Path、前端检查脚本、OpenAPI、环境示例与说明。

工程指纹当前覆盖整个 backend，加入认证会使旧运行保守失效；原始输出没有改写。重新计算产生新版本，不能重写历史哈希使其有效。节点级版本与选择性重算仍属后续阶段。

静态前端可公开获取，私有 API 和所有下载需要后端会话及项目授权。旧 backend/service.py 是不带账号体系的历史服务，禁止作为新工作区启动入口。
