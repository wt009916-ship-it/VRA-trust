# Linux 原生引擎隔离增量

本批承接 PR #22，只扩展真实 EnergyPlus 版本检查和年度模拟的 Linux 执行边界。CAD、OCR、PDF 解析器仍未接入此文件/网络边界，不将资源限额测试冒充完整隔离。最终测试数量、源码身份与原始证据哈希见 LINUX_NATIVE_ISOLATION_EVIDENCE.json；开发复评仍为 70/100。

## 实现与运行条件

`core.native_workspace → native_staging.linux_engine_workspace → execution.supervise → engine_worker → native_linux.launch`。新建私有目录，流式限额复制引擎、同目录运行库和输入，记录字节 SHA256，原件不改。引擎/输入只读，只有指定 output 可写；标准流外不向引擎传递父进程描述符，环境变量由白名单构造。

在专用单线程监督器的子进程中先设置 no_new_privs、Landlock 和 seccomp，再执行 ELF。需要 Linux x86_64/aarch64、Landlock ABI ≥6、libseccomp.so.2 及非 root 服务账号；任何安装/执行/回执失败均拒绝，不退回普通权限。部署镜像显式增加 libseccomp2，但没有据此宣称容器或服务器部署通过。

Landlock 限定文件内容、写入和执行，TCP bind/connect 不授予，并启用 ABI6 的抽象 Unix socket/信号作用域。seccomp 系统调用默认 EPERM，网络 socket 系列、进程创建、命名空间、ptrace、io_uring、BPF、凭据修改等不在允许表。clone3 返回 ENOSYS 以供 glibc 回退；clone 仅允许带 CLONE_THREAD/VM/SIGHAND 的已知线程标志组合。真实多线程计算通过，不能把此限定描述成“完全禁止 clone”。

ELF 本体及当前架构的精确系统动态加载器获得 EXECUTE，库目录仅可读。可信启动阶段通过独立管道回传实际 ABI、seccomp 模式、uid、PID、加载器路径；管道在 exec 前关闭。监督器控制文件不在引擎授权范围，父进程核验回执后才接受完成状态。

既有 CPU、地址空间、单文件限制继续生效；总输出仍每 50ms 检查，不能称硬磁盘配额。新边界禁止新增进程，但没有把既有 `aggregate_tree_budget=false` 改成未经验证的树级预算声明。物理代码哈希包含 Linux 策略和共享复制模块，旧运行按既有规则保守失效，不重写历史 manifest。

## 独立验收设计

本机 WSL Ubuntu 24.04，内核 6.18.33.2-microsoft-standard-WSL2，Landlock ABI7，uid/gid 65534。使用既有 nobody 账号直接 `--exec`，未改账号 shell、系统 Python 或系统权限。Python 3.12.3 的独立 venv、引擎与测试副本位于新建的 `/var/tmp/vra-linux-acceptance-…` 私有目录。

官方 EnergyPlus 9.0.1 bb7ca4f Linux 包：106626518 字节，本地 SHA256 `5018f22c4ce230cadda7deef7ba796af6e3ed80380f7f486b2b3b8c61fc311d9`。上游 API 未给出 digest：这是官方 HTTPS 下载和本地身份记录，不是独立签名认证。解包在新目录执行成员数/展开大小检查及 `filter='data'`，pip 引导 wheel 按 PyPI 摘要校验。首次 GitHub 未认证 API 限额失败保留，不泄露令牌。

- 真实正反控制：外部合成文件普通权限可读；回环 TCP/UDP、IPv4/IPv6 普通进程真实收包；隔离后四路拒绝且接收端没有收到。没有向外部目标攻击或施压。
- 输入可读/不可改，输出可写，外部/控制文件不可读写，chmod/硬链接/软链接/setsid/子进程拒绝；继承 FD 关闭，合成敏感环境变量缺失，8 个线程独立计算正确。
- 直接将进程替换为未授权 `/bin/sh` 被拒绝；已知外部路径的 stat 元数据仍可见，并作为明确限制断言，未隐藏此结果。
- 超时、取消、内存、CPU、输出、非零退出分别真实触发，监督器/引擎退出后再运行成功；缺失授权路径与被移除的隔离回执拒绝。
- 同一最终物理代码分别在 Windows/Linux 重跑公开三方案；从原生 SQL 用 Decimal 独立计算载能合计及 EUI。基准/R1/R2 为 57193.23/55715.19/55592.10 kWh，面积 927.20 m²。实际取消、无数值/无已发布 SQL、恢复年度运行和旧目录不可覆盖另行核查。

这些模型属于公开工程参考，原有两条定容 Warning、气候/材料假设与碳核算缺口仍保留。无因子时碳结果为空；相同数字不证明实楼校准、节能合规或碳资产认证。

## 缺陷、失败证据与处理

所有路径以 `validation/linux-isolation-20261105/` 为根，历史失败不覆盖。表中每项同时列出复现、预期、实际、严重度及建议。

|编号 / 程度|对应功能与描述|复现步骤 / 预期|实际结果与证据|修复或下一步|
|---|---|---|---|---|
|LINUX-01 高，已修复|Linux 引擎原先仅有 rlimit，无文件/网络限制|通过 core 启动原生任务；预期限制无业务需要的访问|旧 PR22 Linux 分支 isolation=None；本批真实正反探针及年度回执确认边界|默认 Landlock+seccomp，条件不足拒绝|
|LINUX-02 高，已修复|ELF 加载器未获执行授权，正式链无法启动|只授权主 ELF，运行版本检查；预期安全且可启动|annual-second.log 失败、调用数0；专项7失败，直接 Popen errno13|仅授权当前架构精确系统加载器；annual-third 成功，最终回归另行留证|
|LINUX-03 中，验收工具已修复|探针误用复制的 venv 解释器，读取私有 pyvenv.cfg 被拒|执行原探针；预期使用受控公共运行库|linux-isolation-third/fourth.log 7失败；stderr 的 init_import_site 权限拒绝|探针改用 base interpreter，显式标准库目录；不扩大产品文件授权|
|LINUX-04 中，验收工具已修复|原测试输出父目录包含安装库符号链接|annual_first.py 把 run 放在安装根下；预期独立输出账本|annual-first/result.json 拒绝 Linked native artifacts，调用数0|运行目录与工具安装分开；保留容量拒绝，不绕过生产门禁|
|LINUX-05 低，验收导出已修复|nobody 对 Windows 挂载目录 copystat 失败|shutil.copytree 导出 Linux 证据；预期完整保留字节|annual-first.log EPERM，先前失败结果已留存|独立新目录按字节导出并核对 SHA，不转移 Linux 所有权/模式|
|LINUX-L01 高，未关闭|解析器仍缺文件/网络边界|检查 CAD/OCR/PDF worker 启动链；预期每条不可信输入链有边界|代码审查确认未使用本模块；全量回归不替代隔离验收|下一子批分离解析运行库/模型并测试原件及网络保护|
|LINUX-L02 高，未关闭|硬存储、主API强杀回收及Windows映射内存缺口|对照 NATIVE-L02/L03、RES/TASK 原反例；预期完整额度/恢复|本批未覆盖，输出仍轮询；不能因禁止进程创建宣称全部资源限制完成|继续硬额度、所有权清单、孤儿恢复与故障演练|
|LINUX-L03 中，限制|路径元数据和公共系统运行库仍可见|对已知外部路径执行 stat；预期如实声明边界|真实测试可见大小，metadata_namespace_isolation=false|不声称文件名/元数据保密或 VM；需要时增加独立部署命名空间验收|
|LINUX-E01 低，环境未明|首次 /tmp 独立 venv 在后续命令中消失|setup_linux.py 成功后 run_tests.py；预期环境持续存在|linux-isolation-first.log FileNotFoundError；原因未确认|保留首次安装/检查日志，改 /var/tmp 新目录；不归因于未证实的系统清理机制|

## 复现与边界

最终本机验收：Linux **523 passed、12 skipped、6 subtests passed，248.52秒**；Windows **522 passed、13 skipped、6 subtests passed，451.27秒**。两平台各25项真实引擎核查通过，32项前端测试及lint/build/契约导出通过。保留Starlette测试客户端弃用提示、故意重复ZIP成员的反例警告及Three.js大分块构建提示。Linux全量在独立源文件副本及自己的原生参考证据上运行，没有借用Windows结果充数；实际跳过项不计通过。

最终物理哈希 `24980c3a62cfba035267af7df98b7775fec71a9958c9049eec31218179f32199`。Windows生成新参考指针前另存prior-windows-*，旧run目录未改。该参考重跑进程沿用显式4 GiB归档预算以容纳保留历史，产品默认额度未更改。Linux失败与后续成功均留在各自目录。

PR #23 首轮远程提交 `f839e729afefc871ad69e9660836653df66ac40f` 六项push/PR检查全部成功。两份Linux后端日志分别为517 passed、18 skipped、6 subtests passed，166.22/120.25秒（job127261687732/127261302773）。远程未安装EnergyPlus，不计真实模拟通过。证据索引追加原日志和提交回执，共505项；补入本段后的最终文档提交仍须六项检查成功才合并，最终head与合并身份在本地release-receipt.json记录。

非 root Linux 服务账号、ABI≥6 和 libseccomp 环境下，安装 `backend/requirements-dev.txt`，设置实际 `ENERGYPLUS_EXE` 及隔离 `VRA_DATA_DIR`，运行 `python -m pytest -q tests/test_linux_isolation.py tests/test_execution.py`。真实参考运行使用 `python scripts/verify_task_budgets.py --output <全新独立目录>`；全量使用 `python -m pytest -q`。已有参考指针必须来自当前源码/当前引擎，否则先另存旧指针并生成新运行，不能修旧哈希。

Windows、root、旧内核会明确跳过 Linux 实际边界测试，这种 skip 不计通过；产品 Linux 执行仍拒绝不满足条件的环境。x86_64 已实测，aarch64 仅实现分支，未有实体或 CI 验收。未进行生产长稳、完整内核攻击面评估、外部服务测试或第二台机器部署。可信服务/同账号管理员被攻陷不在此子进程边界保证内。

## 官方依据

- [Linux Landlock 文档](https://docs.kernel.org/userspace-api/landlock.html)：规则集版本、文件/网络授权和 ABI 作用域；本机实测 ABI7，不按最新文档最高版本冒认能力。
- [Linux Landlock UAPI](https://raw.githubusercontent.com/torvalds/linux/master/include/uapi/linux/landlock.h)：结构体、访问位和系统调用接口。
- [libseccomp 规则 API](https://raw.githubusercontent.com/seccomp/libseccomp/main/doc/man/man3/seccomp_rule_add.3)、[属性 API](https://raw.githubusercontent.com/seccomp/libseccomp/main/doc/man/man3/seccomp_attr_set.3)：参数比较、默认动作、NNP 和 TSYNC。允许表是本项目限定运行策略，不是官方安全认证。
- [EnergyPlus 官方 v9.0.1](https://github.com/NatLabRockies/EnergyPlus/releases/tag/v9.0.1)：实际下载版本；未调用有已知迁移问题的附加 transition 工具。
