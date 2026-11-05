# 本地备份与恢复

适用：本机Windows/Linux单个VRA服务，当前数据库结构；不是在线备份、跨机部署或云灾备验收。

备份包含账号密码摘要、项目原件及历史计算结果，**未加密**。只保存到有访问控制的本地目录，不上传GitHub或通过业务API分享。工具排除private目录中的Provider配置/密钥、可再生成exports、目录锁及SQLite临时侧文件；SQLite已提交WAL内容通过backup API合并进快照。Linux新包权限0600；Windows chmod不等于DACL，仍须使用本机受控目录，本批不声称完成Windows ACL验收。

## 创建

1. 正常停止当前服务并等待后台任务结束。升级前的旧服务不认识新目录锁，必须先停止；不要在另一进程直接写数据库或数据文件。
2. 选择已经存在的、位于数据目录之外的备份目录。
3. 在项目根目录、已安装依赖的Python环境运行：

```powershell
python scripts/backup_runtime.py create --source ./runtime --archive ../backups/vra-20261105.zip
```

程序返回整包archive_sha256、文件数、总字节数。把SHA-256另存到受控记录；恢复时需要这份先前记录，不能只相信未知包自行附带的校验值。已存在的目标包拒绝覆盖；执行失败可能保留不完整ZIP，不能当作成功备份。源目录未知条目、链接/重解析点、缺失登记原件或成功运行缺失产物都会拒绝备份，不静默遗漏。

## 验证与恢复

```powershell
python scripts/backup_runtime.py verify --archive ../backups/vra-20261105.zip --sha256 <先前记录的64位SHA256>
python scripts/backup_runtime.py restore --archive ../backups/vra-20261105.zip --sha256 <先前记录的64位SHA256> --target ./runtime-restored-20261105
```

`verify`核对整包、成员清单/哈希、支持的SQLite结构及完整性、登记原件/OCR预览和成功运行manifest绑定。校验不是作者签名，也不能证明工程原始信息真实。

恢复目录必须不存在，连已有空目录也不会覆盖。先建立`.restore-incomplete`标记，所有检查通过后才移除；中途损坏/空间不足/校验失败保留隔离目录和标记，应用拒绝启动该目录。不要手动删除标记来伪装恢复成功，改用新的目标目录重试。

恢复后的变化：

- 账号与项目归属保留，原密码继续使用；全部旧会话撤销，需要重新登录。
- queued/running仿真任务变为failed，不自动重新计算。运行中的Agent/搜索追加失败修订，旧版本仍保留。
- Provider配置和密钥不迁移，默认禁用；主机环境变量不属于备份，须单独管理，不能把“未拷贝密钥”理解为清除了主机环境变量。
- 原始文件、计算产物、输入来源和历史版本指纹逐字节保留；新代码/来源变化仍按原规则失效，不重写旧hash。
- 恢复变更记录在recovery/restore_*.json，下一次备份继续保留。

确认恢复目录和校验结果后，以该目录启动本机服务：

```powershell
$env:VRA_DATA_DIR = (Resolve-Path ./runtime-restored-20261105).Path
./Start.ps1
```

原runtime保留；恢复不是覆盖或自动切换正式数据。本次工具不提供浏览器下载备份入口，避免普通项目账号取得整个实例的数据。

## 限额与适用范围

当前单包上限4 GiB、20000个数据文件、8 MiB清单；只接受本工具生成的ZIP_STORED格式。SQLite备份有30秒预算，源/目标磁盘空间不足则拒绝或留下未发布目录。格式版本vra-cold-backup-1，未知SQLite结构拒绝，不执行包中的迁移/触发器。

目录锁为Windows字节锁或Linux flock，是参与进程之间的协作锁，不防御具有同一账户文件写权限的恶意程序；不支持网络文件系统或多主机共享。文件逐个fsync并保留失败标记，不声称经断电或磁盘损坏演练。运行环境、依赖、EnergyPlus、OCR模型与仓库代码不在runtime备份包内，须按部署文档重新准备匹配版本。
