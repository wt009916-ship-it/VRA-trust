# Windows 原生引擎隔离增量（2026-11-05）

本批将实际 Windows EnergyPlus 的版本检查和年度计算接入 LPAC，保留 Job 资源限制。Linux 和 CAD/OCR/PDF 解析器尚未接入文件/网络沙箱。开发复评维持 **70/100**，不将一个平台的一条链路通过当成全部隔离完成。最终测试数字和文件身份见 NATIVE_ISOLATION_EVIDENCE.json。

## 实际行为

core → 新建私有临时目录及唯一 AppContainer profile → 有界复制引擎/同目录 DLL/IDD（合计最多128 MiB、256文件）和输入（各最多256 MiB）→ 记录副本SHA256 → 只读运行库和输入、独立可写输出 → 监督器先安装 Job → 挂起创建 LPAC → 回读包SID、AppContainer状态、完整能力列表及Job归属 → 正反 AccessCheck → 恢复线程 → 有界stdout/stderr及输出/profile联合监测 → 原SQL/ERR核验 → 独立归档。

没有修改原安装目录、原件或已有项目目录的权限。引擎副本/输入与控制请求、监督回执分目录，受限引擎不能读取或改写控制文件。仅继承明确列出的三个标准流句柄。监督器和引擎采用白名单环境，不继承Provider密钥、代理、PATH或动态加载器覆盖。只授予registryRead能力，不授予网络或COM能力。运行前核对引擎和输入副本；全部暂存运行库文件身份进入manifest。

创建进程的LPAC属性必须设置成功；令牌内核回读和访问检查失败即停止，不降级成普通进程。AccessCheck先确认显式包SID、ALL RESTRICTED APPLICATION PACKAGES的读取正例，再确认ALL APPLICATION PACKAGES、Everyone-only的拒绝反例。受限子进程实际读写测试与此相互补充。Windows 11 build26200实测；其他Windows版本尚未逐一验收。

AppContainer有自己的临时profile存储，因此不能声称只存在一个可写目录。该profile目录与引擎输出一起纳入现有50ms字节/文件监测；正常结束、超时、取消和非零退出后由父进程删除profile并清理本批临时目录。测试核查目录确实消失。进程数继续由监督器Job限制为2（监督器+引擎），第三进程创建被拒绝。API主进程被强杀/掉电后的孤儿目录恢复尚未完成。

## 验收与原始证据

证据位于 validation/native-isolation-20261105，Git只提交代码、报告和哈希索引，不上传临时安装副本、账号库或原生大输出。

- 专项10项：文件外读写、跨任务读取、输入和运行库写入、控制请求读取/写入拒绝；指定输入读取及输出写入成功；普通令牌不能冒充LPAC；合成环境变量不继承；子进程被拒；丢失隔离回执拒绝成功；硬链接来源复制为独立字节；超额来源拒绝；profile内1 MiB实际写入触发64 KiB监测限额；取消/超时/非零退出后的清理和恢复。
- 网络四路分别做非受限进程的IPv4/IPv6 TCP连接与UDP真实收包正例，再由受限进程访问同一回环地址及端口。受限调用均errno13拒绝，接收端无数据。无外部攻击或压力测试。
- scripts/verify_task_budgets.py完成25项真实核查：三方案原SQL Decimal交叉验证、版本与年度调用均有LPAC回执、实际取消不发布数值/SQL、再运行成功、旧目录拒绝覆盖。三方案分别57193.23、55715.19、55592.10 kWh，面积927.20 m²。
- 浏览器原隔离账号实际创建run_9a12c00c0089…，年能耗57193.23、EUI显示61.68；两条Warning继续待复核、碳排空值；旧运行因代码版本变化显示失效。ui-summary.json绑定原manifest并核查四个监督器/引擎PID已退出，截图ui-lpac-success.png。
- 三方案测试历史已有1,302,469,401字节；新增128 MiB运行库预留后单次最坏预留944,766,976字节，触发默认2 GiB门禁。reference-final.log保留拒绝，原参考指针另存prior-*。仅参考重跑进程显式设VRA_EXECUTION_ARCHIVE_MB=4096，恢复后保留默认配置；没有删除旧证据或改写旧manifest。

## 缺陷、失败与未关闭项

|编号 / 严重度|功能与问题|复现步骤|预期结果|实际结果与证据|修复或下一步|
|---|---|---|---|---|---|
|NATIVE-01 高，部分修复|原生引擎拥有普通用户文件/网络权限|用合成外部文件和回环接收器运行原生子进程|无业务需要的访问被OS拒绝|旧版仅Job/rlimit；本批Windows引擎实际拒绝，isolation-expanded.log|Windows默认LPAC；Linux/解析器仍见NATIVE-L01|
|NATIVE-02 高，已修复|引擎监督器继承整个API进程环境|父进程设置合成敏感变量及加载器覆盖，检查子环境|仅保留明确运行项|旧Popen无env过滤（白盒）；新实际子进程变量缺失，test_native_environment及LPAC文件网络测试|统一白名单；原有解析器本来已有过滤，不宣称它们也曾继承整个环境|
|NATIVE-03 中，已修复|直接查询LPAC令牌类46不可用|在build26200对挂起子进程调用GetTokenInformation(46)|可靠验证后才运行|WinError87；isolation-readback.log 4失败、readback-diagnostic.log|改为受支持AccessCheck正反控制；不使用未经证实的私有令牌字段|
|NATIVE-04 中，已修复|额外ChildProcessPolicy影响加载|在现有LPAC启动属性中增加该策略再跑Python/E+|兼容加载且拒绝额外进程|退出3221225794，isolation-accesscheck.log/accesscheck-diagnostic.log；具体系统内部原因未证实|撤回此冗余属性，保留已验证Job两进程上限；实际spawn反例通过|
|NATIVE-05 高，已修复|profile存储不在原输出扫描范围|受限进程向自己profile/AC/Temp写1 MiB，输出目录留空|联合额度能拒绝|新测试在64 KiB预算下实际终止，isolation-expanded.log|profile+output联合监测；仍非硬磁盘配额|
|NATIVE-L01 高，未关闭|Linux及CAD/OCR/PDF缺文件/网络隔离|追踪对应worker启动链，查看平台回执|各受限处理链都有OS边界|这些链路仍只有既有资源限制；本批回归不能代替隔离验收|Linux Landlock/seccomp或受控容器实测；Windows解析器接入分离运行库/模型|
|NATIVE-L02 高，未关闭|完整资源/存储约束仍不足|对照既有映射内存反例、轮询实现和profile写入测试|覆盖所有写入及进程树，不能瞬时越额|Windows映射内存未完整限制；Linux仍非树级；轮询可先超限再终止，registry/profile/其他模块不构成硬磁盘配额|硬额度和树级预算；完整共享存储核算；不得以此次通过关闭RES-01/02、TASK-L01/02|
|NATIVE-L03 中，待验证|主API被强杀/掉电可能残留profile和临时数据|在API退出finally无法执行的条件下检查存储|重启识别并安全回收仅本应用孤儿|本批只验证正常父进程仍存活的任务取消/超时；强杀恢复未验收|持久化所有权清单和启动核查，保留失败证据；不盲删系统Packages或用户目录|

最早独立探针的环境203错误、文件标签5错误和无registryRead时访问拒绝均保留在appcontainer/lpac日志。普通AppContainer可读ALL APPLICATION PACKAGES的合成文件，LPAC+registryRead拒绝；只看socket.send返回成功的早期UDP探针未判通过，随后加入真实接收端对照。上述探针不替代产品集成测试。

## 能力边界与复现

最终本机全量：522 passed、4 skipped、6 subtests passed，426.25秒。前端32项、lint/build及契约导出一致通过；保留Starlette测试客户端弃用提示、损坏ZIP反例的重复项提示，以及Three.js大分块构建警告。Windows专项10项15.96秒；后续全量覆盖同一最终代码。远程Linux和最终提交状态以证据索引及本地release-receipt为准，不将Windows用例跳过计为Linux隔离通过。

LPAC仍可访问Windows授予ALL RESTRICTED APPLICATION PACKAGES或registryRead的系统资源，也可访问自身profile。它不是VM、完整注册表/IPC审计或硬磁盘配额；不防同账号管理员修改程序及证据。未做完整提权/IPC/重解析点攻击面评估、生产长稳或外部服务测试。E+附加脚本/预处理器未纳入运行库，若输入依赖这些资源则应失败，不扩大授权或替换结果。

在已配置的Python3.12环境执行 `python -m pytest -q tests/test_native_isolation.py tests/test_execution.py`。真实工程执行 `python scripts/verify_task_budgets.py --output <全新验收目录>`，需要实际EnergyPlus和项目公开输入。Windows能力用例在Linux明确跳过，不计通过；全量执行 `python -m pytest -q`。无引擎/无服务不补造数值。

## 官方接口依据

- [Microsoft AppContainer/LPAC启动](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)：能力和访问交集、LPAC需显式registryRead等约束。
- [进程创建属性](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute)：安全能力、受限句柄继承；设置成功后仍进行实际验证。
- [AccessCheck](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-accesscheck)、[DuplicateToken](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-duplicatetoken)：用模拟令牌核对描述符授权。本文LPAC正反组合是本项目实现和实测，不称官方认证方案。
- [GetAppContainerFolderPath](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-getappcontainerfolderpath)：查询新profile目录并按API要求释放内存。
