# 原生工作目录崩溃恢复

服务在启动工作线程之前，检查本 OS 账号、当前临时目录下的版本化原生资源登记目录。正常结束会回收任务副本和 Windows AppContainer；非正常退出后由下一次启动恢复。此处只处理原生计算与解析的临时资源，不删除项目上传原件、历史运行或业务数据库。

## 所有权与活动判断

登记目录为 `vra-native-v1-<账号摘要>`，每个条目使用随机 UUID；目录和账本先按当前账号私有权限创建。账本绑定条目、数据目录和租约文件的设备/文件身份，Windows profile 还绑定派生 SID、精确名称、存储路径及创建后取得的文件身份。禁止把旧 `vra-private-*` 或任意同前缀 profile 自动收编为本版本资产。

Windows 使用不共享的文件句柄，Linux 使用 `flock` 排他锁；它们是实际内核对象，不是 PID 文件或超时时间戳。任务所需租约只复制给可信监督器，并在监督器中核对文件身份；原生解析器和引擎不继承租约。API 已退出但监督器仍活时，另一个恢复进程必须保留该条目。[Windows 文件共享语义](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)、[Linux flock 语义](https://man7.org/linux/man-pages/man2/flock.2.html)说明了句柄/文件描述符关闭与锁释放的关系。

分配时先写入并同步账本，再创建数据目录并补记身份。回收前写入 `cleaning` 状态；回收资源后先删除账本、最后删除租约文件，保证中途退出留下的状态能再次核对。磁盘断电、存储硬件故障和任意网络文件系统的持久性未验收，不能把进程退出测试等同于断电可靠性保证。

## 启动拒绝与维护

无法证明所有权时，服务拒绝启动或当前操作失败，保留相关文件：包括账本损坏或丢失但已有数据、文件身份变化、软链接/junction、未知条目、特殊文件及清点超限。不要通过删除账本、重写身份或放开权限消除失败。

维护人员应先保存日志和私有目录副本，在同一账号下核对原有账本、文件身份和系统权限；确认没有活动任务后，才处理明确归属的故障条目。本版本不提供“按名称前缀清空临时目录”功能。旧版本无账本的遗留目录需要单独人工核对，自动恢复不会扫描它们。

登记最多 256 个条目，恢复清点每个数据树最多 80000 个节点，注册锁等待上限 15 秒；这些是防止无界工作量的限制，不是 OS 磁盘硬配额。账本超过 8192 字节拒绝读取。空登记目录及 `registry.lock` 会保留供后续使用，不属于未回收的客户资料。

Windows 删除 profile 前检查精确 SID/路径/身份和目录结构，调用系统 API 后仍检查存储目录已经消失。系统 API 失败或部分清理时保留账本；如果系统映射丢失但目录仍存在，将保守拒绝继续删除，需要维护核对。该部分异常状态尚无完整故障注入覆盖。[Microsoft 删除 profile 的限制](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-deleteappcontainerprofile)。

若某次启动看到活动租约，会跳过该条目；它随后变为孤儿时，在后续恢复检查/服务启动再回收。本实现没有后台定时清扫。管理员、恶意同 OS 账号进程、网络共享临时目录和磁盘损坏不在本机私有目录隔离保证内。

本批服务验收在确认原生进程已经退出后重启；监督器关闭租约与 OS 最终终止原生任务之间的立即重启竞态未完整验收。若系统仍持有文件或 profile，恢复可能失败并保留账本，需要在确认原生任务终止后复核；不能自动认定为可删的无主资料。

## 重复验收

安装开发依赖后，从仓库运行以下命令，每次提供一个尚不存在的输出目录。脚本只创建全新的隔离数据库、随机内存口令和合成/公开参考资料，绑定随机本机端口。它会强杀自己创建的测试服务，不连接现有业务服务。

```text
python -m pytest tests/test_native_ownership.py tests/test_execution_lifetime.py -q
python scripts/verify_service_recovery.py <新目录>/engine
python scripts/verify_service_recovery.py <新目录>/cad --parser-kind cad
python scripts/verify_service_recovery.py <新目录>/drawing --parser-kind drawing
python scripts/verify_service_recovery.py <新目录>/standards --parser-kind standards
```

能耗命令需要真实 `ENERGYPLUS_EXE`；Linux 需要非 root、支持现有 Landlock/seccomp 边界的内核和本机文件系统。未满足依赖不会改用模拟成功。验收的临时业务库有账号哈希和会话状态，应留在私有本机输出，不发布到 GitHub；公开证据只选取不含凭据的检查记录、观测和日志。
