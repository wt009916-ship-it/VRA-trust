# 本地停服备份恢复限定验收

基线8edc11021653309608edc38afafb90c9dfeac43b；2026-11-05。实现代码：backend/backup.py、runtime_lock.py、应用生命周期与三类后台execute守卫；入口scripts/backup_runtime.py。使用方法见BACKUP_RECOVERY_GUIDE.md。

## 能力与真实调用链

CLI create → 独占维护锁 → SQLite写事务冻结及独立连接backup快照 → 全部登记数据目录清单/源码产物检查 → 逐文件存入ZIP_STORED → 前后源清单核对 → 整包验证。应用初始化/服务生命周期及EnergyPlus、Agent、反例搜索后台操作持有同一目录锁；仍运行则备份拒绝，进程退出OS释放锁。

CLI restore → 对同一个打开文件检查先前记录的整包SHA → 严格成员路径/类型/数量/总大小/清单检查 → 独占新目录与未完成标记 → 分块复制并逐个哈希核对 → 再次复核整包 → SQLite结构/完整性/原件及成功运行manifest核对 → 撤销会话/标记未完成任务 → 写独立恢复记录 → 发布。现有目录和原备份包不覆盖。恢复不自动启用Provider，不自动运行历史任务，不改写工程指纹。

## 验证范围

专项tests/test_backup.py覆盖真实ZIP、账号和项目隔离、CAD原生解析、OCR/预览/人工复核历史、旧会话拒绝、来源/解析版本失效、WAL提交、两轮恢复历史、子进程实际持锁及崩溃释放、后台任务在HTTP生命周期结束后仍保持互斥、恢复中断、路径穿越/驱动器/保留名/大小写别名/重复条目/压缩包/符号链接/错误整包hash/缺失成员/恶意SQLite触发器/伪成功缺产物/校验后改写拒绝。详细计数以BACKUP_RECOVERY_EVIDENCE.json为准。

scripts/verify_backup_recovery.py使用全新的隔离账号/目录，真实执行官方五区参考EnergyPlus、独立5000mm DXF线段、中文OCR及人工复核；随后关闭应用、备份恢复、以原账号重新登录、重新取API/JSON/PDF，撤回输入再做第二轮备份恢复。最终31项检查通过；一个正式计数的最终演练实际调用EnergyPlus1次，所有重跑分别保留，未冒充零额外调用。

最终参考结果为年度57193.23 kWh、面积927.2 m²、EUI 61.68381147540984 kWh/(m²·a)。34个备份数据文件（其中1个数据库）、33个原件/运行/预览文件逐字节一致；备份总数据约28.5 MB。恢复前后run API完全相同；报告仅新的generated_at导出时间不同，其他字段相同。原生SQL、PDF、来源/人工复核历史和再次恢复后的stale拒绝均有证据。这是公开参考模型，不是实楼验收。

本轮没有新增前端页面，不用上一批受阻的浏览器结果为本批背书；维护CLI和实际API闭环是当前入口验收。Linux行为待本PR真实CI，不从Windows结果推断。

## 缺陷及失败保留

|编号/严重度|功能和问题|复现、预期与实际|证据|修复/后续|
|---|---|---|---|---|
|BKP-01 高，已补强|没有可核验的一致备份恢复|原有仅建议手工拷贝；应恢复数据库+原件+结果全链，现停服锁+SQLite快照+全包核验+新目录恢复|33个专项用例与真实31检查演练|原目录保留，持续扩展容量/故障矩阵|
|BKP-02 高，已补强|校验与解包若分两次开路径可读到不同文件|文件校验后改写；预期拒绝，现同一打开文件并再次整包核对，不发布恢复目录|test_archive_changed_after_member_checks_cannot_publish|保留整包外部校验；不宣称能抵御同账户恶意程序|
|BKP-03 中，已补强|旧会话及未完成任务随数据恢复|恢复包含session和running任务的实例；应失效旧登录且不自动计算，现401与failed/追加修订|会话、任务和两轮恢复测试|继续生产级调度恢复验收|
|BKP-04 测试问题，已修|历史摘要与完整记录混比|首轮1失败35通过；数据库行与API摘要不是同一结构；分别核对后通过|backup-first-tests.log、backup-second-tests.log|保留失败日志；后续夹具隐藏会话repr，首轮含隔离会话的日志只在本机保留不发布|
|BKP-05 测试问题，已修|报告新的导出时间导致全JSON比较失败|首次真实演练在report比较失败；复核只generated_at不同，其余内容一致|native-drill/checks.json、report-failure-analysis.json|只排除新导出时间，保留所有工程/证据字段比较；新目录重跑|
|BKP-L01 高，未验收|加密和Windows备份DACL|包内包含账号摘要及项目资料；现未加密，Windows chmod不等于ACL|backup.py manifest encrypted=false、指南|后续补本地加密/密钥恢复与真实ACL验证；不得公开分发包|
|BKP-L02 高，未验收|生产级灾备/并发长稳/磁盘配额|当前验证单机协作停服恢复；跨主机、网络盘、物理断电、累计配额未测试|当前范围与测试清单|继续配额/容量/故障演练；服务器及第二台电脑仍按用户指示暂缓|

## 评分与后续

维持69/100。原“安全与保护”的生产恢复子项还需要访问控制/加密与更完整故障环境，不能把单机开发恢复扩大为生产灾备通过。工程计算、实楼、Provider、完整图纸修复、OS沙箱缺口不因此得分；下一子批累计存储配额与备份保护。扩大训练及整体前端重构继续后置。

实现依据：[SQLite backup API](https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Connection.backup)、[Windows msvcrt字节锁](https://docs.python.org/3.12/library/msvcrt.html#msvcrt.locking)、[Linux flock](https://docs.python.org/3.12/library/fcntl.html#fcntl.flock)。实际行为以本批独立进程/恢复证据为准。
