# 运行与部署边界

当前已有账号会话、CSRF及项目归属校验，但没有完成公网部署安全验收；仅绑定127.0.0.1。用户暂缓服务器及第二台电脑任务，不执行公网部署。

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
确定主机/SSH/域名；复核现有认证、授权和项目级访问控制在生产环境的配置与隔离；添加受信代理/Host 配置与 Caddy/Nginx HTTPS；划分受限仿真 worker；测试并发、超时、任务恢复、磁盘限额、备份恢复、日志脱敏及上传限额。
这些完成前不发布公网服务。既有 local Host/Origin 拒绝规则不是生产安全验收证明。

## 原生解析资源预算

CAD/OCR/规范PDF工作器仅支持Windows与Linux；其他平台或预算安装失败均拒绝解析。Windows Job Object限制私有提交内存/作业用户CPU/单进程，**不覆盖匿名映射**。Linux rlimit限制每进程地址空间/CPU及单文件大小，**不覆盖进程树累计资源或文件网络访问**。预算、真实失败反例与测试见WORKER_RESOURCE_DELIVERY.md。父墙钟超时和这些预算不构成完整恶意文件沙箱。
