# 原生解析器资源预算与恢复验收

2026-11-05；基线 b38d4deb1c82cc76ae0f04c203aa56a1e4f0d78b。范围：CAD、图纸OCR、规范PDF三个独立子进程。属于部分加固，不能称为恶意文件安全沙箱；复评维持69/100。

## 实现与边界

worker_limits.py 在工作器命令行入口、原生库导入前设置OS预算。设置/回读/入组失败退出70，不降级执行；父接口要求内部回执后才能保存成功产物。资源策略源码纳入解析器身份，旧记录保留并按原失效机制处理；解析过程中身份改变拒绝保存。回执不是抵御已被攻陷解析器的安全认证。

|工作器|内存预算|CPU预算|父进程墙钟超时|
|---|---:|---:|---:|
|CAD / IFC / DXF|2 GiB|20秒|30秒|
|图纸OCR / PDF页|2 GiB|40秒|60秒|
|规范PDF|512 MiB|20秒|30秒|

|平台|实际约束|明确不覆盖|
|---|---|---|
|Windows|Job Object进程及作业私有提交内存、作业用户CPU、最多1进程、关闭Job终止成员|匿名映射内存、工作集硬上限、单文件/累计磁盘限额、文件和网络访问隔离|
|Linux|每进程RLIMIT_AS、CPU用户+系统时间、单文件64 MiB、禁止core dump|整个进程树累计预算、子进程数量、进程组超时清理、总磁盘配额、文件和网络隔离|
|其他平台|拒绝启动解析器|没有静默无保护回退|

CPU预算不是实时墙钟，Windows由内核周期检查。线程环境限制OMP/OPENBLAS/MKL为2；其本身不是安全边界。

## 可重复验证

使用Python3.12.14，在隔离测试目录执行：

```
python -m pytest tests -q
python tests/worker_limit_probe.py memory
python tests/worker_limit_probe.py cpu
python tests/worker_limit_probe.py child
python tests/worker_limit_probe.py mapping_gap
python scripts/verify_ifc_reference.py validation/ifc-20261105/duplex.ifc <新输出目录>
python scripts/verify_drawing_reference.py validation/drawing-ocr-20261105/kinnear.png <新输出目录>
```

本机最终388 passed、1 skipped、6 subtests、1既有httpx弃用警告，244.23秒。新增20个用例在Windows19通过、1个Linux专属文件限额测试跳过；通过数包含“正确报告映射缺口”的测试，不代表20种攻击全部拦截。Linux在提交1edc5d60c81f813f2000b5e459627db72362525b的push/PR两套真实CI分别86.04/98.38秒，均380通过、9跳过、6子测试；本批20项中18通过、2个Windows专属跳过。其余跳过为既有Windows DPAPI及未生成本地参考产物测试，不能算通过。新增Linux映射拒绝、CPU终止、单文件限制和三个接口恢复均包含在本次真实执行中。日志见证据索引。

独立128 MiB探针：Windows VirtualAlloc提交256 MiB被拒绝（1455）；1秒CPU预算导致退出3221225540，实测墙钟2.859秒而非父10秒timeout；派生子进程不能执行；新正常进程仍成功。反例：匿名mmap 256 MiB成功创建，因此mapped_memory_bounded=false，未宣称触碰全部物理页或整机RAM上限。

三个接口分别注入真正受限且耗尽CPU的子进程，均409、不写成功记录、保留原文件，紧接着真实正常解析成功；零退出但无回执同样拒绝。替换的是测试中的子进程边界，不伪造成功结果。

公开Duplex重新解析：295产品、108矩形拉伸体、21声明面积、295空间关系与独立结果匹配，7.259秒。7种合成OCR及公开Kinnear旧图重新运行，预选12标签匹配10、总43候选；高分误识别仍保留。响应记录本次实际资源回执。以上不等于实楼验证或整图识别准确率。

## 失败保留与缺陷

|编号/严重度|功能与问题|复现/预期/实际|证据|修复或后续|
|---|---|---|---|---|
|RES-01 高，未解决|Windows内存约束不完整|128 MiB下mmap 256 MiB；完整隔离预期拒绝，实际成功|memory-probe.log、windows-probes.json、mapping_gap测试|部署级隔离/整体内存配额后重测；现明确标注私有提交范围，不能宣称完整沙箱|
|RES-02 高，未解决|Linux树级资源与OS访问隔离缺失|阅读_linux及父subprocess.run；期望树级预算/超时回收，现仅每进程rlimit，无文件网络隔离|backend/worker_limits.py及三个服务调用链|受限服务身份/容器或cgroup、进程组清理、访问策略及逃逸测试；部署尚未授权启动|
|RES-03 中，已修|成功进程无资源回执仍可能被采纳|测试替换输出为零退出无回执；预期拒绝，现409、无记录、原件保留|三个missing receipt测试|父层严格检查内部回执；不把它当抗入侵认证|
|RES-04 中，已修|策略变化没有绑定解析身份|改变限制源码；预期旧结果可识别失效，现纳入parser hash且检查前后身份|cad.py/drawings.py/standards.py及全量回归|保留旧文件，不重写历史hash|
|RES-05 测试环境问题，已修|参数ID含大段二进制|首次pytest设置PYTEST_CURRENT_TEST超Windows32767环境长度，2个setup error|first-tests.log|改用cad/drawing/standards短ID；最终重跑通过|
|RES-06 中，待定位|本轮浏览器验收受阻|Edge自动化打开本机首页并reload；预期可到登录页，实际Cross-site request rejected；截图调用亦超时|ui-navigation-observation.json；api.py跨站拒绝逻辑|保留安全规则；独立复核正常地址栏导航与扩展请求差异，本轮UI未通过|

首次专项65通过、1失败、1跳过、2错误：失败是Windows mmap反例，不能改写为通过；上述最终测试将该缺口作为显式边界验证。原失败日志保留。

## 依据与后续

Windows内存预算语义参见[Microsoft Job Object扩展限制](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information)，CPU/活动进程语义参见[基本限制](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information)。Linux接口依据[Python resource](https://docs.python.org/3/library/resource.html)，真实执行证据独立记录。

下一子批优先本地备份/恢复与累计存储限额；完整原生隔离仍为高严重缺口。真实Provider、实楼校准、完整图纸修复、专业复核和生产验收没有因此完成。训练扩容、全局前端视觉重构继续后置。
