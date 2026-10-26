# 多样本与复杂高楼实测

日期：2026-10-26。新增6份不同来源建筑的公开IFC输入、1份作者构造的控制场景，另测1份台北101风模型的文件准入。**本批6份公开IFC整模均未完成全年流程；其中3份的明确最低非空楼层完成了365天、零Warning的假设情景。复杂高楼完整自动热建模尚未通过。**

原始输入、失败运行和完整API轨迹保存在隔离验收目录；本仓库提供[来源/文件哈希](benchmarks/2026-10-26-multi-project/sources.json)、[各轮实际结果](benchmarks/2026-10-26-multi-project/results.json)及[历史案例回归](benchmarks/2026-10-26-multi-project/regression.json)。没有提交原始模型或账号数据库。

## 怎样选样、怎样算通过

先冻结5份之前未用于本项目修复的建筑参考IFC，以及AP14控制场景的来源提交、文件哈希和首轮流程。不同IfcProject/IfcBuilding标识和原件哈希用于排查重复；不能据此证明所有参考文件均为已建成或有实测资料的客户建筑。

首轮对每个原件执行完整空间导入；仅当超过100空间时，追加最低非空楼层。看到首轮失败后，再明确追加一轮诊断：对所有失败的多层文件测试最低非空楼层，不寻找“能过的楼层”。这一后续轮不是盲测，不增加独立建筑数。高楼样本是用户要求后的另一次扩展，最终复核也不是留出集成绩。

- 生产API链：隔离注册/登录 → 原件上传 → 原生清点 → 导入 → 保存人工复核假设 → 严格热边界 → 有条件的假设情景 → 发布 → 实际EnergyPlus → 原生结果/PDF。
- 保留所选范围全部IfcSpace；整模失败不跳过空间。没有修改源IFC、改变文件后缀、用包围盒代替房间或删除热面制造成功。
- 几何公差和邻接补缝均固定为0。先拒绝未知IFC边界；仅严格校验失败时，追加显式绝热的未知边界假设。该假设不等于真实外墙/楼板条件已经恢复。
- 通过项沿用相同的假设办公负荷、构造和官方Golden EPW；全部选中空间假设为空调/计入面积。它们验证软件情景，不是原建筑实际能耗，不比较建筑间节能高低。
- 引擎EnergyPlus 9.0.1，IfcOpenShell 0.9.0.post1。本轮修复以`bf68c28`为基础；高楼最终结果另记录物理编译器及相关源码哈希，避免把未提交时的运行误称为旧提交原样运行。

## 新增IFC的实际结果

|输入|原文件空间/楼层对象|整模结果|最低非空楼层的后续结果|
|---|---:|---|---|
|FZK Haus|7 / 2|6可提取、1斜顶空间受阻，导入409|6/6空间；365天、0Warning、PDF 200|
|Smiley West|140 / 5|超过100空间上限，导入409|30/30空间；365天、0Warning、PDF 200|
|E3D Revit|104 / 4|超过100空间上限，导入409|31/31空间可导入；原首次引擎失败，修复后在发布前预检拒绝，仍未通过全年|
|LiNear Office|86 / 5|75可提取、11受阻，导入409|6/6可导入；2处细小热面被预检阻止，未通过全年|
|KIT Institute|82 / 5|79可提取、3斜面空间受阻，导入409|17/17空间；365天、0Warning、PDF 200|
|De Zalmhaven 高层|0 / 64|上传201；没有IfcSpace，导入409|没有非空空间楼层可选；未计算|
|AP14 Two-Building控制场景|2 / 2|空间可导入；热边界分段不收敛，发布409|1空间范围仍受阻；不是独立客户建筑|

前三个成功楼层的严格边界检查均未直接放行；表中全年成功发生在显式假设情景中。局部楼层不能算整楼成功。该有目的的小样本也不足以估计市场项目的通用成功率。

FZK、Smiley、E3D、Office与AP14来自 [IBPSA BIM工作包](https://github.com/ibpsa/project1-wp-2-2-bim/tree/90ad1ed2fd1f84643ca866ceda5667cb0d0274f9)；KIT输入来自 [IFC-toolkit固定样本](https://github.com/ara3d/IFC-toolkit/blob/9ad378ae8db3203dbedfc6ffc7fb56ded56590ea/test-files/C20-Institute-Var-2.ifc)。文件级商业授权尚未核清，原件不再分发。

## 用户提到的复杂地标

|建筑/输入|实际取得什么|实际验证到哪一步|
|---|---|---|
|台北101|[Dlubal官方教学下载](https://www.dlubal.com/en/downloads-and-information/examples-and-tutorials/models-to-download/002028)，40,303,737字节，RWIND 2的`.rws2`文件|实际上传返回409 `Unsupported file extension`，存储文件0、计算任务0、年度指标null。它是风模型示例，未转换成IFC，不是经过确认的竣工热模型。|
|De Zalmhaven高层|[Esri官方教程](https://learn.arcgis.com/en/projects/geolocate-a-3d-digital-building-model/)的Royal BAM Group建筑IFC，40,250,285字节|原生清点64个楼层对象、2,897个墙体对象、0个IfcSpace；文件上传成功，但无法生成房间热模型，接口明确拒绝。楼层对象数量不等于经现场确认的实际楼层数。|
|广州塔、央视总部|本轮检索未取得来源和使用条件可核实的可下载完整热工BIM|未执行，不列入测试次数或通过率。网上外形模型、论文和参数化教程不能替代工程原件。|

De Zalmhaven使用压缩包中的`DigitalModels/Building_1_HR/ZHA-B-BWK-C-HR-R18.ifc`，没有把地理定位后的Solution版本算成另一栋楼。公开数据条目`1055807d84fe45928fd5cf56cfb42e7e`注明Royal BAM Group，`licenseInfo`为空；不将“可下载”解释成商业再分发许可。

## 本轮真正修了什么

E3D最低楼层原来能通过九项Honeybee检查，但EnergyPlus随后给出25条Severe、39条Warning并在全年开始前终止。细碎三角面和生成窗触及旧引擎限制；这暴露的是发布前检查漏检，不能靠“通过几何检查”宣称可以计算。

核对[EnergyPlus 9.0.1原始源码SurfaceGeometry.cc](https://github.com/NatLabRockies/EnergyPlus/blob/v9.0.1/src/EnergyPlus/SurfaceGeometry.cc)后，增加两项已知致命条件的预检：按实际IDF的6位小数坐标检查面积小于`1e-6 m²`，以及三角面边长小于`0.01 m`。同样检查生成窗；不一律禁止含短边的四边形，因为引擎可能合法去掉冗余顶点。

同一份E3D输入现于发布前定位19处不兼容热面/窗、返回409且不启动引擎。**这是更早、可解释的正确拒绝；复杂网格修复仍未完成。** 没有改未知边界掩盖失败，没有删面，也没有改写旧失败运行。新预检仅覆盖这两条已知规则，不替代完整引擎与物理校验。

## 回归和证据保留

- 完整后端258项、6个子测试通过；前端41项通过；Ruff、前端检查、OpenAPI无漂移及生产构建通过。构建仍有大于500 kB的分块提醒，未宣称前端性能优化完成。
- 对原始中庭控制、Duplex21空间、Esplanades首层50空间、诊所屋顶层6空间重新执行真实全年，四组均365天、0Warning；随后隔离恢复93文件、11上传原件与4份年度结果/报告通过。它们是回归，不算新增建筑。
- 初次高楼测试进程被主机沙箱的Windows `socketpair`限制阻塞于TestClient初始化；已单独诊断并在本机隔离权限下重跑，未计为产品导入失败。结果表仅使用完成的实际API请求。
- 物理编译器变化会使旧物理运行保守标记失效。旧结果、原件、失败ERR与manifest保持，不修改哈希消除失效。

## 怎么复跑

先按来源清单取得自己有权使用的原文件，核对SHA256；将清单中每个`cases`条目补充本机绝对`local_path`，保存在仓库外。无需上传原件到GitHub。

```powershell
$env:ENERGYPLUS_EXE='C:/EnergyPlusV9-0-1/energyplus.exe'
$env:PYTHONUTF8='1'
.venv/Scripts/python.exe scripts/benchmark_new_projects.py --manifest 'D:/acceptance/input-manifest.json' --output 'D:/acceptance/new-run'
.venv/Scripts/python.exe scripts/benchmark_file_admission.py --file 'D:/acceptance/taipei101.rws2' --output 'D:/acceptance/new-admission'
```

建模清单须包含`protocol`、`frozen_at_utc`和`cases`；每项字段与来源JSON一致，另加`local_path`。首轮与后续协议见结果JSON；设置`scope_selection: all_multistorey_after_full_failure`才启用后续多层诊断。输出目录必须全新且在仓库外；完整轨迹可能包含项目资料，只对外分享审核后的摘要。

下一步优先补的是**墙/板/幕墙到可核对空间的重建、斜面与细碎面修模、超过100空间的全楼组织、源窗和真实设备/运行输入**。如果只增加可导入后缀、调高空间上限或继续展示同一栋Duplex，不能证明这些缺口已解决。
