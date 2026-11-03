# MFA、企业登录、邮件恢复与负载验收 · 2026-10-26

本轮补齐本地账号的身份安全流程和后台连接配置。真实 Keycloak 与 Mailpit 联调、浏览器页面测试及本机生产构建负载测试均已执行。用户的企业 IdP、SMTP 和独立生产环境配置尚待补充；不把这些隔离结果写成企业生产验收。

## 使用入口

- 前台右上角「账号设置」→「双重验证」「恢复邮箱」「企业登录」。先设置自己的认证器，再安全保存只显示一次的恢复码。
- 独立后台 `/admin#services` →「服务与身份连接」→「登录与恢复连接」。仅首个管理员可读写；保存必须再次验证当前密码，已启用 MFA 时还须第二因子。
- 邮件服务启用后，登录页「忘记密码？」可以申请恢复邮件。只向已绑定并确认的地址投递，界面不泄露邮箱是否存在。
- 正式账号、原密码哈希与历史项目不会因部署自动改变。生产 MFA、企业身份和邮箱均由账号主人显式绑定，不使用验收账号代替正式账号。

## 已实现及拒绝边界

**MFA** 使用 PyOTP 标准 TOTP（6 位、30 秒、允许前后一个时间步），加密保存绑定密钥，十分钟绑定有效期并绑定当前会话。严格保存已用计数器，旧验证码不能重放；10 个 80 位随机恢复码仅保留哈希且只能原子消费一次。密码正确只生成五分钟挑战，不签发业务会话；挑战最多尝试五次。启用、关闭、重发恢复码均撤销旧会话和项目 Token。关闭或重发须本地密码与第二因子。

**SSO** 使用 Authlib 的 OIDC Authorization Code + PKCE S256，校验一次性 state、独立浏览器关联 Cookie、nonce、签名、issuer、audience、时间、azp 和存在时的 at_hash。仅允许 RS256/ES256；网络不跟随未审核重定向。元数据端点须属于 issuer 的源或管理员显式允许的额外 HTTPS 源。按 issuer + subject 显式绑定，不按邮箱自动合并、不自动生成成员或管理员。启用本地 MFA 的账号通过 SSO 后仍须验证。解除绑定须本地密码和第二因子，撤销旧会话/Token 并换发本地会话。这里实现的是 OIDC，不包含 SAML、SCIM、IdP 全局退出、通行密钥或 IdP 强制策略管理。

**邮件恢复** 使用 email-validator 验证地址，30 分钟随机一次性链接；数据库保存 token 哈希与当时的密码版本。确认新邮箱前旧地址仍有效，更换后通知旧地址；验证邮箱只能绑定一个账号。重置密码须当前有效邮箱、有效链接，以及已启用时的 MFA。旧密码、旧会话和项目 Token 随重置失效，不自动登录，不绕过 MFA。发信使用加密持久队列，最多五次有界重试；队列和线程状态可从后台读取。该队列采用可重试投递，进程在 SMTP 已接受但本地尚未记账时中断可能重复投递，不保证 exactly-once。

**密钥与传输**：Windows 使用当前系统账号 DPAPI；Linux 必须由运维注入持久的 `VRA_IDENTITY_KEY`（Fernet），缺失时安全功能拒绝使用明文回退。备份恢复也须保留对应密钥或 Windows 系统账号。正式公共地址、OIDC 地址须 HTTPS；SMTP 默认 STARTTLS/证书验证，也支持隐式 TLS。只有回环联调允许 HTTP/明文 SMTP。凭据、TOTP 密钥、恢复码、重置链接和 OIDC code 不放进前端持久缓存、公开诊断或 Git。Uvicorn 回调访问日志移除整个查询串；公网反向代理也须另行配置日志脱敏。

## 真实联调与发现的缺陷

隔离实例使用正式 Vite 构建和同一 FastAPI 代码，监听 8890；真实 Keycloak 26.8.1（开发模式）监听 8891，Mailpit 1.32.0 的 SMTP/API 为 8892/8893。二进制从官方发布取得并校验 SHA256，未提交仓库。Keycloak、Mailpit 仅用于验收，不是已配置好的生产身份和邮件设施。

1. 真实邮箱绑定与 SMTP 投递、验证链接消费通过。
2. 真实 Keycloak 显式绑定、SSO 登录成功；启用 MFA 后，业务 API 在第二因子前返回 401，之后的会话 assurance 为 `oidc+otp`。本地密码登录对应 `pwd+otp`。未绑定企业身份被拒绝，业务 API 仍 401。
3. 认证器绑定用浏览器 WebCrypto 独立 HMAC-SHA1 算法生成验证码通过；10 个恢复码实际生成，恢复码登录通过。协议测试另外验证原子消费、计数器防重放、过期、错误次数、关闭和重新生成。
4. 真实邮件找回通过：同一标签页打开链接、地址栏移除 token、输入新密码与 MFA、返回登录、旧密码 401、新密码仍要求 MFA；使用过的链接再次检查返回 400。
5. 修复同一标签页找回链接缺少路由处理，以及旧 hashchange 事件误刷新的两次实际失败；旧失败记录保留在隔离验收目录。
6. 修复通用 Fetch Metadata 防护误拒外部 IdP 顶层 GET 回调；只放行此精确路径，state/关联 Cookie/签名检查仍执行。隔离 Keycloak 为同站不同端口；跨站拒绝边界另外用协议测试覆盖，未冒充外部企业 IdP 实测。
7. 修复管理员密码正确、第二因子错误时未计失败次数；解除 SSO 绑定也撤销既有登录和 Token。已登录后的敏感操作验证错误返回 403，保留当前会话，不触发通用 401 重新登录；该状态修正后 52 项身份/后台专项再次通过。

## 系统密码管理器：仍有未通过项

真实安装的 Chrome 156.0.8078.47、Edge 155.0.4283.62 在独立配置下通过标准字段、实际登录、刷新会话、无页面异常检查。这些检查不等于系统密码库通过。

用户在第一轮手动验收反馈「一款或两款未出现保存／自动填充」，已记录为失败。随后修改成功登录为完整文档导航，不再仅在页面内替换视图；避免记住账号逻辑覆盖浏览器已有填写。修复后两浏览器网页登录复测通过，原生保存/重开自动填充/更新密码尚须再次手动确认；不宣称已通过。

电脑控制授权曾超时；技能禁止自动操作密码管理器和 OS 认证对话框。没有修改浏览器安全设置、读取个人密码库、自动点击保存或绕过 Windows Hello。没有把 `navigator.credentials.store` 的完成或 JS 写入字段当作原生验收。

表单规则参考 [Chromium 官方密码表单指引](https://new.chromium.org/developers/design-documents/create-amazing-password-forms/) 和 [web.dev 登录表单指引](https://web.dev/articles/sign-in-form-best-practices)。本应用支持粘贴和标准 username/current-password/new-password/one-time-code；密码不写入 localStorage。Firefox、Safari、第三方密码管理器均未列入本轮通过范围。

## 本机生产构建负载结果

硬件：Windows 11、Intel Core Ultra 7 255HX、20 个逻辑处理器；单 Uvicorn worker、SQLite WAL、正式 Vite 构建、回环网络。同机测试端和服务端，第一轮业务负载期间还运行了后台回归测试。无外网 TLS、代理、独立数据库或多实例，不是生产容量承诺。

输入：buildingSMART 社区公开原始 Duplex IFC，固定上游提交和 [原始样本目录](https://github.com/buildingsmart-community/Community-Sample-Test-Files/tree/7ddf57a201f88a0c213d5322b02ed15e94a60a40/IFC%202.3.0.1%20%28IFC%202x3%29/Duplex%20Apartment)，SHA256 `b347a2c8aa8fff6db896a4417a9c50c22ac0ccd7c5cfc22b99b8d29336c606ed`。21 个空间，复制到新建的 22 用户隔离库；不复制原账号、私钥或运行，不改原库和历史物理结果。半数会话带 MFA assurance。源几何保留，热工参数仍沿用显式参考假设，不是实测建筑性能。

|负载|结果|运行前阈值|
|---|---:|---:|
|120 秒，工作区 5→10→20 VU，加 2 个几何校验 VU|4,024 HTTP 请求；4,086 检查全部通过|业务失败率 <1%|
|项目/工作区/模型/运行/账号安全读取|p95 655.91 ms|p95 <1,500 ms|
|实际模型保存|156 次成功；p95 1,184.20 ms|成功 >20 次，p95 <2,500 ms|
|热几何与独立审计|p95 3,289.80 ms|p95 <10,000 ms|
|业务失败|0|<1%|
|20 并发、100 次错误密码突发|2 次 401、98 次 429；无 5xx、无错误会话|只接受明确拒绝；5xx=0|
|突发期间健康接口|100 次成功，p95 5.14 ms|p95 <2,000 ms|

429 是密码计算容量保护或速率限制生效，不能统计成 98 次成功登录。压测未请求并行 EnergyPlus 年计算、外部 LLM、SMTP 高吞吐或整栋复杂 IFC 批量解析。这些结果不替代长时间浸泡、故障切换、多机/公网容量和生产目标 SLA 测试。

可复跑脚本：`scripts/prepare_load.py`（新目录、源文件哈希验证）、`scripts/load_workbench.js`、`scripts/load_auth.js`。k6 2.3.0 原始 JSON 的公开无凭据副本见 `docs/benchmarks/2026-10-26-identity/`。阈值和执行器按 [k6 官方文档](https://grafana.com/docs/k6/latest/using-k6/thresholds/) 预设，不在测量后降低阈值。

## 生产接入仍需的信息

管理员在后台填写正式公共 HTTPS 地址、IdP issuer、机密客户端 ID/Secret、必要的额外端点源、SMTP 主机/端口/加密方式/发件地址；密钥仅在本机后台或部署秘密管理器提供，不在聊天中收集。IdP 注册精确回调 `https://<应用域名>/api/auth/sso/callback`，启用 PKCE S256。公网部署须另设 Secure Cookie、受信 Host/反向代理和日志脱敏；当前服务仍为本机部署，不应直接公网暴露。

随后用真实企业普通成员和管理员各完成绑定、登录、MFA、找回、禁用和撤销的联调，再对独立预生产环境执行容量与恢复验收。当前尚未获得这些配置，不宣称该阶段已完成。

本轮运行时依赖：PyOTP 2.10.0（MIT）、Authlib 1.9.1（BSD-3-Clause）、qrcode 8.2（BSD）、email-validator 2.3.0（Unlicense）；版本锁定在 requirements。实现参考 [PyOTP](https://github.com/pyauth/pyotp)、[Authlib](https://docs.authlib.org/en/stable/oauth2/client/http/index.html)、[OWASP MFA](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html) 和 [OWASP 密码恢复](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)，不构成合规认证。
