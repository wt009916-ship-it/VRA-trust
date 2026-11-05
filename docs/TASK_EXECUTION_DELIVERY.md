# 任务执行限额与原生计算监督：交付记录（2026-11-05）

本批建立持久化任务准入、取消与退出、原生进程资源回执，以及日志/输出/归档预算。不是完整安全沙箱，也不是生产长期负载验收。开发复评暂维持70/100；不启动扩大训练或整体前端改版。

## 实际调用链

API鉴权/CSRF → Store事务准入 → Domain主队列或Agent/Search启动器 → runtime共享原生执行槽 → 私有ASCII临时目录 → 独立监督进程设置OS限制 → EnergyPlus → 限额日志与输出检查 → 完整归档 → 原SQL/ERR核验 → manifest和同源结果。结果不再由未经监督的 subprocess.run 直接生成。

队列全局16/项目4；Agent2/Search1。SQLite BEGIN IMMEDIATE在计数与写入之间排除竞态。后台线程构造/启动、首写/末写失败均释放内存槽位；无法持久化最终状态的记录保持未确认，启动恢复时处理，不伪造成功。退出时停止接收、请求在途任务停止，并等待已登记线程结束。

POST /api/runs/{id}/cancel沿用项目归属和CSRF。排队任务立即失败且未执行；运行任务先保持running+CANCEL_REQUESTED，执行结束后才转失败。取消与成功同时发生时，已记录的取消优先，数值不发布。已结束任务不追溯取消。UI提供取消排队/停止仿真，并明确等待状态；最后一刻已结束时不声称取消成功。

## 原生监督与真实性

Windows：监督器先绑定Job Object，CPU300用户秒、私有提交内存4GiB（进程及Job）、最多监督器+引擎两个进程、关闭Job杀子进程。设置进程数时使用PRESERVE_JOB_TIME，避免重新设置时追加已用CPU时间。监督器用基础Python解释器直接运行，避开venv启动转发器，以确保父进程掌握的是Job持有进程。Windows映射内存仍不受此额度完整覆盖。

Linux：进程组回收，单进程地址空间4GiB、CPU300秒、单文件min(输出限额,64MiB)、禁core dump；更严格的继承上限优先。不等于cgroup树级累计资源额度，主动脱离会话/第三方服务启动行为不在隔离保证内。

stdout/stderr各1MiB写入上限；输出默认256MiB/1024文件，约50ms检查，拒绝链接/特殊文件；执行结束后完整有界复制，不将截断SQL当成成功结果。失败最多保留明确标注的64KiB ERR诊断。历史run目录拒绝覆盖。回执缺失/版本不符合/未完成均拒绝成功；引擎是否启动无法证明时calls=null，不写成0。--version调用单独留证，不计入年度模拟调用数。Search将尝试预算与有证据的实际引擎调用分开。

共同原生执行槽覆盖同一runtime的普通仿真与反例搜索。归档准入计算runs/searches的实际文件，默认2GiB和20000文件；预留最坏输入、输出和日志空间并保留256MiB磁盘余量。不删除旧证据。该槽是进程内串行机制，服务跨进程互斥依赖既有RuntimeLease；单独运行core的调用者必须自行保证互斥。

## 发现、复现与修复

|编号/严重度|功能与问题|复现步骤|预期/实际|证据|修复与余项|
|---|---|---|---|---|---|
|TASK-01 高|Search首写DB失败泄漏容量|SQLite触发器拒绝search首记录，再检查槽位|预期释放；旧版未释放|baseline-failures.log、test_task_capacity|启动器统一拥有槽位；持久化事务拒绝时释放|
|TASK-02 高|Agent/Search线程无法启动仍running并占槽|注入Thread.start失败；扩展构造失败|预期failed并释放；旧版running/泄漏|baseline-failures.log、native-expanded.log|构造与start共同保护、失败修订与finally释放|
|TASK-03 高|Search末写失败阻止释放|触发器拒绝revision>1|预期释放且不伪报成功；旧版泄漏|baseline-failures.log；后续测试改由公开start驱动|释放由外层finally保证，未知记录等待恢复|
|TASK-04 高|仿真排队无持久化容量限额/无取消|并发12个独立Store提交，或API超过设定额度|预期原子限额；旧版无上限/无取消接口|test_task_capacity，真实UI取消回执|事务全局/项目计数；429；取消保留历史|
|TASK-05 高|原生日志与finally copytree无累计预算|子进程持续写日志/输出/多文件|预期拒绝且不发布数值；旧版无此边界|test_execution、native-first/second/expanded.log|有界日志、周期扫描、有界归档；硬磁盘配额未实现|
|TASK-06 中|首次实现重新设CPU导致回读差异|独立Windows进程install(256MiB,5,65536)|预期5秒；实际50156250而非50000000个100ns|native-first.log、本批开发记录|PRESERVE_JOB_TIME；回读与实际CPU耗尽测试|
|TASK-07 中|旧物理证据不能用于当前测试|完整pytest读取旧reference_comparison|预期失效；2测试失败拒绝复用|backend-first.log，prior-reference_comparison.json|保留原run，生成全新三方案索引；未更改旧hash|
|TASK-08 中|取消与结束竞争可能误导UI|任务已终态后取消返回succeeded|预期说明未取消；初版统一提示已取消|源码修订与浏览器/接口验收|按真实返回状态显示，不撤销已完成结果|
|TASK-09 中|core复用目录可能覆盖证据|向已有manifest的目录再次运行|预期拒绝，旧版可重写result/manifest|test_existing_run_evidence_is_never_overwritten|执行前拒绝已有输入/输出/结果证据目录|

失败日志、阶段测试及最终哈希见TASK_EXECUTION_EVIDENCE.json（最终验收后生成）。本批最初26项中6失败，修复后26通过；扩展58专项通过；首次全量507通过、2旧证据失效失败、4跳过、6子测试通过。最终全量与Linux结果以证据索引为准，不将阶段数字冒充最终数字。

## 已知边界

无文件系统/网络沙箱、无Windows映射内存完整约束、无Linux树级累计CPU/内存隔离、无硬磁盘配额。轮询期间可短暂超限，磁盘空间预检可被其他进程消耗。数据库、HTTP上传临时文件、预览、备份、其他模块输出与失败元数据未全部纳入此归档额度。未做生产长稳、外部压力或服务器/第二台电脑部署。无真实Provider/实楼/专业签署；参考数值仅证明本地参考链路。

## 官方接口依据

- [Microsoft Job Object基本限制](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information)：CPU时限追加语义与保留时限标志。
- [Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)：子进程继承和关闭Job行为。
- [Python 3.12 resource](https://docs.python.org/3.12/library/resource.html)、[subprocess](https://docs.python.org/3.12/library/subprocess.html)：进程及资源接口。以实际平台试验为验收依据。

## 最终本机验收

510 passed、4 skipped、6 subtests passed，374.30秒；32前端测试与lint/build通过（保留Three.js大分块警告）。scripts/verify_task_budgets.py完成20项真实引擎核查，baseline/R1/R2分别57193.23/55715.19/55592.10 kWh，独立Decimal读取SQL计算EUI与载能合计。另一次实际取消和再次完整年度运行通过。

浏览器项目project_045f48b25ec549169cf8a285bde335f2，取消run_62577c81b033…后数值为空，新建run_f946a91180ac…成功且数值一致。四个相应监督器/引擎PID退出通过内核句柄检查。新项目四份原件先核对当前公开输入哈希；旧项目哈希不同而保留，未替它强行确认。原工程Warning仍为待工程师复核。

|未关闭问题|复现/观察依据|预期与实际|严重度|修复方向|
|---|---|---|---|---|
|TASK-L01 原生输出非硬额度|test_execution连续写输出与50ms循环源码；Windows无FSIZE|预期硬额度阻止写入；目前事后监测可超量再终止|高|部署文件系统/容器磁盘额度；测试瞬时写入和故障回收|
|TASK-L02 配额覆盖不完整|源码追踪扫描范围仅原件、runs/searches；未做耗尽磁盘试验|预期全runtime可预算；当前其他来源不计入本批额度|高|统一分类型存储预算和保留策略，不能删除旧证据掩盖问题|
|RES-01/02 完整隔离未完成|既有WORKER_RESOURCE_DELIVERY的映射反例；本批明确无文件/网络沙箱|预期非必要访问被拒绝且树级额度成立；目前未满足|高|受限执行身份、最小文件授权、网络隔离、树级预算及平台对抗实测|

Linux和最终合并状态由证据索引及本地release-receipt记录，不将本机Windows结果代替Linux或生产验收。

首轮Linux双工作流均504 passed、10 skipped、6 subtests passed（157.13/166.23秒），含真实受限子进程测试；不含未安装的EnergyPlus实际年度运行。随后增加两项取消归属/停服生命周期测试，本机任务专项17通过；随后修正运行中调用次数默认值，最终head由远程六项检查再次确认。

TASK-10（中，run view）：claim后读取running任务，旧默认值显示engine_calls_executed=0，无法表示已经启动但尚无完成回执的情况。预期为未确认/null；修复显式区分queued/排队取消的0和其他无回执状态的null。tests/test_task_capacity的API测试同时检查两种状态；final-view-regression.log记录API/任务/Agent相关回归。Windows全量510来自该显示字段修正之前；修正不改变物理核心，真实参考和浏览器产物仍有效，最终完整回归由最终head的Linux CI再次覆盖。

最终调用次数修正后的本机API/任务/Agent专项68通过，89.98秒；见final-view-regression.log。
