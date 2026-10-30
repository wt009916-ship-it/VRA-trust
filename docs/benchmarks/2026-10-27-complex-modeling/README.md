# 复杂建筑验收数据 · 2026-10-27—28

面向复核的脱敏摘要，[验收条件、假设与限制](../../HIGHRISE_MODELING_ACCEPTANCE.md)是这些数据的组成部分。输入原件、私有API轨迹、数据库、IDF和SQL留在仓库外；不再分发未明确取得授权的原包。

|文件|内容|
|---|---|
|[public-whole-building.json](public-whole-building.json)|FZK/KIT冻结来源、整模范围、严格拒绝与显式假设情景、全年/PDF状态|
|[morphology.json](morphology.json)|16类作者控制形态的IFC往返面积/体积、独立几何校验、原生全年结果|
|[remaining-input-failures.json](remaining-input-failures.json)|Smiley、E3D、Office与AP14的整模未通过项；AP14是作者控制输入|
|[highrise.json](highrise.json)|De Zalmhaven实际结构源的299候选、未恢复范围与发布拒绝|
|[controlled-equipment-mass.json](controlled-equipment-mass.json)|控制铭牌/曲线及柱体等效热容的实际全年执行|
|[regression-restore.json](regression-restore.json)|4组既有年度回归和隔离备份恢复|
|[checks.json](checks.json)|测试/构建、浏览器、编译器和源代码哈希|
|[sources.json](sources.json)|沿用原件来源提交、文件哈希及再分发限制|
|[native-evidence.json](native-evidence.json)|27个新全年运行逐项证据哈希及当前物理核心核对|

`tested_base_commit`是测试开始时的既有提交，测试源为当时尚未提交的工作区；请用`source_files_sha256`与`compiler_hash`核对具体实现。后续物理代码变化须创建新运行，不能改写旧manifest。源窗的`unique_source_windows`按IFC源ID去重，`source_opening_fragments`是为剖分/映射保留的片段数量，不能将片段算成更多窗。

本机验收在Windows执行，执行哈希包含文件原有CRLF/LF字节；Git将文本统一为LF。`checks.json`另列`git_lf_source_sha256`，提交前逐项确认源文件除CRLF→LF外完全一致。旧运行保留其实际执行哈希，未为适配Git换行而改写；跨平台重跑仍创建新证据。

这些是迭代修复后的软件验收，不是留出集成绩、客户能耗校准、现场材料实证、竞品排名或生产SLA。控制形态、不同楼层、参数及重复运行均不重复计为独立真实建筑。执行时有并行负载及主机暂停记录，本摘要不据运行时长比较性能。
