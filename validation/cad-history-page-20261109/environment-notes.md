环境及首次检查记录：
- 首次 Ruff 检出测试未使用的 json 导入（F401）；移除后全项目 Ruff 通过。未影响此前 8 项测试逻辑。
- 首次通过预想路径执行 npm.cmd，文件不存在，测试/构建未启动；改用已存在 Node 直接执行 package.json 等价命令。
- 第一次 Vite 构建 MODULE_NOT_FOUND，见 frontend-build.log；隔离树没有 node_modules。
- 缓存顶层 package-lock.json 不存在，首次整体哈希核对拒绝复用，未建立 junction。随后逐一核对 node_modules/.package-lock.json 中 16 个已安装包的版本、resolved 和 integrity 与项目锁相同，再建立 junction；构建成功见 frontend-build-fixed.log。只验证安装元数据，不宣称重新核验每个包字节。CI 使用独立 npm ci。
- Node v24.22.1。Starlette/httpx 弃用警告与 Three.js 大 chunk 警告保留。没有改包版本、下载模型或开启浏览器。
