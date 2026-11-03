# 运行与部署边界

当前版本已具备账号会话、CSRF、项目归属校验和项目专属 API Token，支持本机多账号使用。部署仍限定单服务进程并绑定 127.0.0.1；这些本地功能不代表公网部署已验收。

## 本地
Python 3.12，Node 22+，EnergyPlus 9.0.1。
运行根目录 Start.ps1；首次按 README 安装依赖并构建前端。
.env.example 是配置说明模板；启动脚本不自动执行 .env 文本。通过 PowerShell 设置环境变量，或使用保留的 config.local.json 配置引擎。
SQLite 和原始资料存于 runtime（Git 忽略），备份须同时包含数据库、files、runs。

## 容器准备
deployment/compose.yml 将 API、前端和单个本地 worker 放在一个应用容器，SQLite 使用持久卷。没有伪造拆分后的 worker/database 服务。
先准备 **Linux** EnergyPlus 9.0.1 并设置 ENERGYPLUS_LINUX_DIR，再执行 docker compose -f deployment/compose.yml config 和 up --build。
Windows energyplus.exe 不能在 Linux 镜像运行。当前 Docker daemon 未启动，镜像构建/运行尚未验收；Compose 配置解析与实际运行是两回事。

## 阿里云 Phase 6 的必做项
确认主机地域、系统、配置及域名后，配置受信代理、正式 Host/Origin 与 Caddy/Nginx HTTPS，并设置 VRA_COOKIE_SECURE=true。现有代码的 Host 白名单只允许本机地址，需要显式适配正式域名，不能仅把监听地址改为 0.0.0.0。

正式开放前还需确定账号注册/邀请方式、计算配额、持久存储与备份，验证并发、超时、任务恢复、磁盘限额、备份恢复、日志脱敏及上传限额。首次管理员须在受控环境初始化。已有登录限流不能替代计算资源配额。

当前 EnergyPlus 信号量只在同一服务进程内生效，保持 --workers 1；跨进程任务分发和共享运行目录尚未验收。自动生成 IDF 的 IdealLoads 范围、外部视觉 Provider 联调及真实项目边界见 BUILDING_WORKBENCH.md。
这些完成前不发布公网服务。既有 local Host/Origin 拒绝规则不是生产安全验收证明。
