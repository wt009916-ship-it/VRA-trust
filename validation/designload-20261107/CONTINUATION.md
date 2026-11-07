# 下一次继续执行的位置（不是通过证据）

候选本地提交900e0a4bd426309f70151dba9c69347519a336d3，分支feature/design-loads-20261107；工作树干净。尚未推送、PR或合并，评分75保持。

全量检查由统一exec会话60912执行，命令先full_windows_v1.py，再WSL非root full_linux_v1.py。最后一次工具轮询仍存活，Windows新三方案参考已完成、全量正在运行；必须先重新轮询此会话或核验真实进程，不凭本文件认定仍在运行，不重复启动。日志windows-full-v1.log、linux-full-v1.log；脚本在原生/回归失败时停止，需记录和排查，不能覆盖x模式原始日志。

Windows冻结源码：integration-source-v1.json，C:/Users/18483/AppData/Local/Temp/vra-designload-integration-7611268929bb466bbf00ba3839a64210/source。
Linux冻结源码：linux-source-v1.json，/var/tmp/vra-linux-acceptance-ybic05cy/designload-v1-c2674f49058b4ac4b18c1ea2e0f4a278/source。
新增portable analytic脚本没有纳入早期Windows快照，但其原生7例已经在当前完全相同的物理源码上单独运行，完整脚本已进入Linux快照和候选提交；不要向旧冻结目录补写脚本。

已完成：Windows/Linux各7合成原生×4数值检查、各1认证API原生全年、各111相关回归；此前原始probe1+matrix5另列。前端80和构建通过，Ruff全库通过。真实浏览器另1次原生全年，10行单位逐项检查，7页PDF，ZIP28文件hash，原型文件保留及撤回复核失效通过；页面异常0。原生3类合成边界warning仍保留。大文件C/WSL，D仅约11MB余量，禁止往D复制SQL、ZIP或大日志。

浏览器driver84366和隔离API93431会话均已正常结束；API子进程80020由隔离测试helper terminate，不能称正常服务关机。Get-NetTCPConnection证实18774没有监听，80020不存在。浏览器未恢复旧账号凭据，新隔离随机密码只在内存。
浏览器资料output/playwright/designload-20261107，源码副本browser-prepared-v1.json；下载在该root/downloads。没有harness-errors.json（若后续出现需如实保留）。实际截图loads-desktop.png和loads-mobile.png已生成，桌面图已人工查看；移动尺寸记录page=viewport=390、region宽352，未自动判全部可访问性。

候选物理hash811cc91edfdfbed58f78d4b69bb52cbfde20a51b22fdcc68545a2b868d29d6ab；解析器SHA ce823df8d3adb62aec3e0fefd5a286226f4154046df95603893c81f3350c904d。双平台summary均包含真实值。历史manifest和reference_comparison未改写。

后续：等全量实际完成→核验代码/原件/历史/全部证据→写正式交付、版本化复评和证据索引→按既有授权推送PR/六检查/合并→更新本机原型并验证数据不变。新增独立设计日稳态能力可评估工程计算子项，但不得提前加分或冒充当地设计/实楼校准。用户95+目标保持活动。

原型18772仍为上一批PR44服务（launcher40380，需再次核验子PID及无任务再停止）。原型库validation/thermal-20261104/ui-runtime/vra.sqlite3原始174条records及3条jobs摘要见climate-20261107/runtime-before.json。后续更新时考虑将应用从可修改工作树切换到独立冻结发布目录，避免开发改动影响运行中版本检测；不能改动原型数据或未完成任务。

工具命令注意：PowerShell的rg文件通配必须用目录+`-g '*.py'`，不要传`backend/*.py`；脚本run_reference日志每行会带完整metrics，勿直接打印长行，可读取摘要文件。此前只读探索有找不到文件/Windows通配错误，均非产品失败；不要宣称全任务所有工具零错误。
