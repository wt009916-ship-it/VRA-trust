# 任务容量与计算输出配置

启动前设置；配置错误会拒绝接受相关操作。正整数，不用0表示无限。新建run重试，不覆盖历史目录。

|环境变量|默认|用途|
|---|---:|---|
|VRA_ACTIVE_RUNS|16|全局queued+running，最大256|
|VRA_PROJECT_ACTIVE_RUNS|4|单项目queued+running，最大256|
|VRA_ACTIVE_AGENTS|2|最新running Agent，最大256|
|VRA_ACTIVE_SEARCHES|1|最新running反例搜索，最大256|
|VRA_EXECUTION_OUTPUT_MB|256|单次原生输出MiB，最大1024|
|VRA_EXECUTION_LOG_MB|1|每路stdout/stderr MiB，最大16；版本查询独立16KiB|
|VRA_EXECUTION_OUTPUT_FILES|1024|单次输出份数，最大10000|
|VRA_EXECUTION_ARCHIVE_MB|2048|runs+searches实际归档MiB|
|VRA_STORAGE_RESERVE_MB|256|与原件存储共用的磁盘保留MiB|

归档总文件上限固定20000。默认原生CPU300秒、内存4GiB；Windows内存仅私有提交，Linux地址空间仅单进程。默认墙钟300秒；内部调用最大3600秒，但不放宽CPU上限。一次原生执行，其他调用等待最多300秒；等待可响应关闭/取消。

保守空间预留=单次输出+512MiB输入+4路日志+1MiB元数据，默认773MiB；空闲磁盘须≥256MiB+2×预留。即使模型较小，也可能因保守预留而提前拒绝。已有归档不会自动清除；先停服做验证过的加密备份，再由运维制定保留方案。不要直接改数据库状态、旧manifest或文件hash解决容量问题。

429表示任务容量满。运行列表可取消排队或停止仿真；“正在取消”不代表已经终止。终止后任务失败、无可用工程数值。意外断电/持久化失败后的running记录由启动恢复标失败，需要显式新建任务。停服等待受现有Provider/工具超时约束，未证明任意插件可即时停止。

本机制不是完整安全沙箱。运行来源不明的可执行文件不在功能范围；API/Agent无任意命令执行工具。生产仍需受限服务账号、文件/网络隔离、系统磁盘额度及长稳验收。

验收：python -m pytest tests/test_execution.py tests/test_task_capacity.py -q；真实参考验证：python scripts/verify_task_budgets.py --output validation/新的独立目录。后者需已安装并配置真实EnergyPlus，不提供模拟回退。
