# Linux 原生进程停止身份修复 · 2026-11-06

本批基于 PR #27 的 `67ae78914f4341cdf6d0e2100a5d6555def74f3b`，实现提交 `8bbf5ea`。修复进程组清理前过早回收监督器身份的问题。开发复评保持 **71/100**；此次关闭一个已有监督机制的风险，不把同一能力重复加分。证据索引为 PROCESS_IDENTITY_EVIDENCE.json。

## 反例与实际实现

在非 root Linux 上运行实际 `execution.supervise` 和正常结束的合成原生子进程，在 `killpg` 边界拦截信号，仅查询 `waitid`。旧代码的观测为 `unreaped_child_identity=false`：正常轮询 `Popen.poll()` 已回收监督器，随后 `_stop` 仍尝试按它的整数 PID 发送 SIGKILL。测试没有把该信号发往内核，没有制造 PID 复用，也没有观察或宣称实际误杀其他进程。基线见 `validation/process-identity-20261106/baseline.json`。

修复后采用 `waitid(WEXITED | WNOHANG | WNOWAIT)` 观察退出，清理进程组前再次确认子进程尚由当前调用者持有，发送信号后才 `wait()` 回收。正常完成、超时和取消都遵循此顺序。已被 Popen 或外部 waitpid 回收的子进程会明确拒绝组信号。Windows 保持原有进程句柄清理，完成观察仍使用 Popen 的原有行为。

`WNOWAIT` 保留可等待状态，最终 wait 才回收退出子进程资源；仅重复查询一个已释放 PID 不能替代该约束。[Linux wait 文档](https://man7.org/linux/man-pages/man2/waitpid.2.html)、[Python waitid 文档](https://docs.python.org/3.12/library/os.html#os.waitid)。

启动前和停止前还核对 SIGCHLD：Python 层必须是默认处理，内核处理器必须为 SIG_DFL 且没有 SA_NOCLDWAIT。Python `getsignal` 不包含该 flag，因此额外只读调用 `rt_sigaction`，不修改宿主信号设置。使用既有 Linux 隔离范围内的 x86_64/aarch64 64 位内核 ABI；无法核验就拒绝。ABI 常量依据 [x86 系统调用表](https://raw.githubusercontent.com/torvalds/linux/master/arch/x86/entry/syscalls/syscall_64.tbl)、[通用系统调用表](https://raw.githubusercontent.com/torvalds/linux/master/include/uapi/asm-generic/unistd.h)、[信号结构](https://raw.githubusercontent.com/torvalds/linux/master/include/uapi/asm-generic/signal.h)及 [SA_NOCLDWAIT 定义](https://raw.githubusercontent.com/torvalds/linux/master/include/uapi/asm-generic/signal-defs.h)。

同一安全探针在最终代码上观测到 `unreaped_child_identity=true`、`exited=true`；9 项新增测试还实际转发只针对其未回收子进程组的信号，验证正常完成/超时/取消，测试被回收身份拒绝、重复观察不回收、SIG_IGN、自定义处理器和真实 SA_NOCLDWAIT 的启动前拒绝。SA_NOCLDWAIT 测试先用独立子进程验证内核确实自动回收，再核验应用拒绝，不仅检查一个模拟返回值。

## 验证范围

最终134个源文件与实现提交、双平台源码快照逐字节一致。Linux 新建真实参考索引后全量 **578通过、16平台跳过、6子测试通过**，335.24秒；专项57通过、4平台跳过。Windows 相关监督/生命周期/租约专项 **50通过、11平台跳过**，23.47秒；本批没有重新执行 Windows 全量，不能把上一批569项全量记为本批结果。

双平台各25项真实EnergyPlus/SQL/Decimal验证通过，三方案仍为57193.23、55715.19、55592.10 kWh。Linux四条真实HTTP强杀恢复链共50项通过，Windows能耗/CAD两条共25项通过；均确认原件保留、无成功伪结果和零任务资源残留。Linux公开IFC复核295产品/空间、108棱柱和21声明量，公开OCR仍为12个预选标签正确10个、43候选，噪声图误识别保留。32项前端、lint/build、Ruff及契约检查通过，既有大chunk提示保留。

物理身份为 `bf517021437d64cd910e8907c779c9a325ee47ecfd050c14a16f4ef7a8f42ca5`，旧结果保持 stale；不改写历史 manifest。原参考索引和既有81个历史文件再次按SHA核对。真实原生进程和软件模型的验证不构成实楼节能合规或结构安全认可。

## 缺陷及环境记录

|编号|功能/严重性|描述与复现|预期|实际/证据|修复或处理|
|---|---|---|---|---|---|
|EXEC-ID-01|Linux停止/高|运行正常结束的真实监督链，在组信号前查询子身份；旧轮询先 reap 后发组信号|组清理前保留可证明的原监督器身份|基线观测 false；修复观测 true；没有实际误杀实验|WNOWAIT观察、组清理后回收，身份丢失拒绝|
|EXEC-ID-02|宿主兼容性/中|在独立测试进程设置 SIG_IGN、自定义处理器或 SA_NOCLDWAIT 后请求原生任务|不在可自动释放子身份的宿主启动任务|三类配置均在原生启动前拒绝，调用次数为0；对应新增测试|读取Python和内核SIGCHLD配置；不擅改宿主处理器|
|ENV-ID-01|运行空间/中|D盘新目录执行三个实际参考方案|余量不足时明确失败，不伪造计算或清除旧证据|baseline/R1成功，R2失败：Insufficient free space for native staging and archive reserve；`windows-final-engine.log`及失败run记录保留|保持额度，在C盘新建账号私有验收目录重跑完整集合；未删除D盘原件或历史|

## 限制及后续

应用必须独占等待自己的监督器；其他宿主线程不得在任务存活期间执行抢占式 waitpid(-1)、改变 SIGCHLD 或安装原生自动回收策略。已经发生的身份丢失可被拒绝，但不承诺抵御同进程恶意代码在核验与信号之间改变全局状态。测试主机为 x86_64；aarch64 分支只按官方 ABI 实现，未进行 ARM 硬件验收。

本批不关闭毫秒级立即重启、profile API 部分失败、磁盘/映射内存硬额度、生产长稳、真实模型或实楼验收。模型元数据仅完成公开来源和大小/摘要核查，尚未安装或调用模型，更未扩大训练。D盘空间限制已实测，后续大文件须使用有足够余量的新位置并保留权限与来源记录。
