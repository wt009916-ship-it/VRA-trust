# 图纸建模、热边界与设备模型实测 · 2026-10-24

本次贯通了公开原始施工 PDF → 本地墙线/OCR 候选 → 原图叠加复核 → 三维空间 → 热边界与分层材料 → 逐时运行/新风 → 原生 EnergyPlus。另用公开 Duplex IFC 测试了实际单速热泵设备耗电。**这些是原始公开资料上的软件与参数情景测试，不是现场能耗校准；还不能承诺任意复杂图纸一键生成完整施工 BIM 或合规热模型。**

机器可读结果、输入和引擎指纹见 [实测摘要](benchmarks/2026-10-24-thermal/results.json)。源文件未修改；测试使用隔离数据库。原始 IFC/PDF、SQL、ERR、IDF、HBJSON、失败运行和截图存于本机验收目录，没有打包进 Git。

## 实际新增能力

|环节|实现与复核要求|
|---|---|
|扫描图/混合 PDF|OpenCV 定向墙线与缺口闭合，RapidOCR 面积文字定位。选页、框选平面、点击尺寸两端并输入已知长度；比例来源必填。候选带原图像素轮廓、标注面积/几何面积误差、闭合距离。未标注区域和排除原因保留，不用 OCR 面积反向调整几何。|
|DXF|ezdxf 展开嵌套 INSERT/MINSERT 和变换，处理 ARC/CIRCLE/ELLIPSE/SPLINE/带圆弧多段线，10 mm 弦误差；非平面、递归和规模超限拒绝。房间图层仍需明确，不声称识别所有家具与墙体语义。|
|不完整 IFC|明确勾选后，仅在闭合 FootPrint、Height、NetFloorArea、NetVolume 同时存在且面积/体积误差 ≤1% 时推导等截面柱体；保存源实体 ID、工程量和推导性质。Box 和默认层高不作为恢复依据。|
|热边界|共面局部配对；显式假设的跨墙厚配对；同一空间边界的共形剖分与双方相同子面。保留原空间及配对距离。未知 IFC 内边界默认拒绝；绝热替代必须明确标为假设。|
|独立几何检查|实际调用 Honeybee 检查平面性、自交、闭合实体、邻接引用和配对面积；拒绝不合格几何。HBJSON 导出明确为几何交换，**不是完整热工 HBJSON**。|
|运行与热模型|墙/屋面/底板分层热容；工作日和周末各 24 小时使用率；非使用温度、新风、显/潜热回收。Honeybee Energy 生成原生 schedules 和 OutdoorAir 对象，最终调用现有 EnergyPlus 核心。|
|设备耗电|显式定容 PTHP：单速空气源热泵、风机、电辅热、逆循环按需除霜。容量/风量/COP/效率/温度阈值/来源必填；保留原生模板、展开对象、定容绑定记录和实际计算输入。没有将理想负荷简单除以 COP。|
|结果|原生 SQL 分项供暖/制冷/风机用电，使用期间未满足温度时数；旧/失败结果不显示有效数值。理想冷热需求与热泵耗电不可混合排名。材料替换与反例搜索保留设备编译标记。|

当前 PTHP 的性能曲线是官方模板默认曲线，非某台厂家机组。新风按设计人数和面积计算：使用时风机连续，其余随负荷启停；理想负荷模式的人数新风随使用率变化，面积新风全天持续。两个模式的运行语义在界面明确说明。PTHP 暂不含新风热回收器，非零回收效率会拒绝保存，不会静默丢弃。

## 未改动的公开输入与结果

### LookHere 施工资料 PDF

[原始 11 页公开 PDF](https://www.lookhere.pro/download/LookHere_Sample-Document_Construction.pdf)，第 6 页。采用图上 8.80 m 尺寸、510 像素标定，裁剪 `[825,285,1360,775]`，缺口闭合 0.8 m，层高 3 m 为明确测试假设。最终单次识别 5.05 秒，仅供本机诊断，非性能承诺。

- 得到 6 个区域，其中 5 个有源面积文字；未标注的楼梯区域也保留。
- 源面积为 7.22、5.49、2.34、19.97、15.8 m²，几何误差绝对值最大约 **7.42%**。这是五处面积核对，不是通用识别准确率。
- 三组均完成 365 天、8760 小时，无 Severe/Fatal；每组 **2 条微小表面警告**，各涉及约 `0.000446611 m²` 面。未删除小面来伪造零警告，仍需工程师审阅。

|明确假设的运行情景|照明/设备电 kWh|供冷需求 kWh|供热需求 kWh|
|---|---:|---:|---:|
|新风 + 60% 显热回收|1,886.59|1,394.02|3,183.72|
|相同新风，无回收|1,886.59|1,418.04|3,738.88|
|无机械新风|1,886.59|1,704.41|2,746.69|

此处 District Heating/Cooling 是冷热需求，不能解释为压缩机耗电或用电账单。

### buildingSMART Duplex IFC

[固定上游提交及样本目录](https://github.com/buildingsmart-community/Community-Sample-Test-Files/tree/7ddf57a201f88a0c213d5322b02ed15e94a60a40/IFC%202.3.0.1%20%28IFC%202x3%29/Duplex%20Apartment)。保留 21/21 空间、25 个高度分段；计入面积 240.59453 m²，屋顶空间保留但明确不计入面积/空调。

三组理想负荷年计算均 **0 Warning / 0 Severe**。供热需求分别为 7,633.86（回收）、9,943.92（无回收）、5,288.29（无机械新风）kWh。

真实热泵采用显式测试参数：制冷 120 W/m²、制热及电辅热各 150 W/m²、风量 6.5 L/(s·m²)、风压 150 Pa，总/电机效率 0.6/0.9，显热比 0.75，制热最低室外温度 −15°C、制冷最低 0°C。两组只改变制冷/制热 COP；第三组在 COP=4 下将容量和风量加倍。三组均运行全年，**0 Warning / 0 Severe**。

|设备情景|总用电 kWh|供暖电 kWh|制冷电 kWh|风机电 kWh|使用期供暖未满足 h|使用期制冷未满足 h|
|---|---:|---:|---:|---:|---:|---:|
|COP 2|20,330.78|6,914.10|3,556.32|1,069.03|215.83|564.17|
|COP 4|15,763.93|4,125.41|1,778.16|1,069.03|215.83|564.17|
|COP 4、容量/风量 ×2|16,793.88|3,943.43|1,957.43|2,101.70|31.50|125.00|

其余电量为照明/室内设备。供暖列包含电辅热，所以不会随 COP 翻倍而正好减半。加大容量改善未满足时数，但风机用电增加，最低用电情景不能直接当作合格选型。没有用这些结果宣称实际建筑节能率。

Duplex 原空间边界仍有未配对/未知边界；该测试显式使用绝热情景、20 mm 几何公差、最大 0.6 m 的跨墙厚配对。不是源 IFC 的完整热属性转换。所有年计算使用 Golden 官方参考天气和假设围护/使用参数，未证明与源建筑所在地和运行情况相符。

### Schependomlaan 的诚实失败

[原始样本](https://github.com/buildingsmart-community/Community-Sample-Test-Files/tree/7ddf57a201f88a0c213d5322b02ed15e94a60a40/IFC%202.3.0.1%20%28IFC%202x3%29/Schependomlaan)，49 MB、100 空间。默认严格模式仍只有 6 个可解析 Body；开启可追溯 FootPrint 重建后提升到 **88 个可解析、12 个受阻**。12 个源 FootPrint×Height 与 NetVolume 相差约 1.626%–26.219%，缺少足够证据恢复斜顶/变化截面。

整个建筑仍拒绝采纳和仿真。没有删除这 12 个空间，也没有把体积除以面积当成真实层高。后续需要补充原软件导出的空间实体或剖面资料；这是输入证据不足，不是可以凭空修成的已知几何。该样本上游说明研究/教学用途，本项目没有再分发原数据。

## 实测发现并修复的问题

- Honeybee 默认房间整理会翻转极小面：审计对象改为保持原几何，明确容差，独立检查不再暗中改面。
- 仅插入共线顶点会被 EnergyPlus 清理，引发邻接顶点数不一致：改为共同三角剖分、逐面面积守恒和闭合检查。
- 日程温度类型重复、新风室外节点缺失：修复生成对象；杜绝只看进程退出码。
- 原生 ExpandObjects 仍生成 `autosize` 风量并导致初始化崩溃：官方展开后将具体设备字段绑定到已输入定值；未绑定 autosize 会拒绝，原始展开/修改前后字段/最终 IDF 全部归档。
- 模板低温制冷报警：新增明确的制冷最低室外温度，保留停机带来的未满足时数；不删除警告文本。
- 原生 SQL 的空白分隔行：明确跳过无行名的分隔，不把缺数据当零。
- 材料方案生成会丢弃设备编译标记：材料替换和导热敏感性派生保留编译来源，另做真实热泵全年测试。

完整后端 200 项 + 6 子测试通过，前端 31 项通过；Ruff、契约导出、语法和生产构建通过。前端 Three.js 分块仍有 >500 kB 构建提示。真实 Edge 完成原图预览/框选/两点标定/候选叠加、逐空间复核、热泵必填拦截、保存、面积同步、IDF 发布；390 与 1440 像素无页面横向溢出。隔离服务重启时产生的两次连接中断已与应用错误区分。

## 开源选择与商业交付边界

- 实际接入 [Honeybee Core](https://github.com/ladybug-tools/honeybee-core) 1.64.79、[Honeybee Energy](https://github.com/ladybug-tools/honeybee-energy) 1.126.6；Ladybug 几何/日程库版本进入编译指纹。
- Honeybee Core/Energy 和 Ladybug Core/Geometry/Polyskel 安装包声明 **AGPL-3.0**。完整许可证已归档 `third_party_notices/python`，版本与许可证哈希在 `DEPENDENCY_INVENTORY.json`。**不能把该组合直接当成已完成闭源商业发行许可审查的产品**；商业发行需要落实相应许可方案或替换组件。本次未擅自给整个仓库重新授权。
- [CubiCasa5k](https://github.com/CubiCasa/CubiCasa5k/blob/master/LICENSE) 的非商业许可不符合直接商用集成目标，没有装其权重或宣称训练了房间模型。[bim2sim](https://github.com/BIM2SIM/bim2sim) 仅作选型研究，没有声称完成接入或同题实测。
- 图纸路径仍偏正交墙线；曲墙、重叠图、未知比例、跨层复杂剖面须补证。窗仍由明确窗墙比假设生成；斜面、完整 HVAC 水系统、厂家变工况曲线、实际假日运行/湿度控制、实测校准、规范报审未完成。

## 复跑

安装 `backend/requirements-dev.txt`，设置真实 EnergyPlus 9.0.1 路径，源数据独立下载并先核验摘要中的 SHA256。每次使用新的输出目录：

```powershell
$env:ENERGYPLUS_EXE='F:/EnergyPlusV9-0-1/energyplus.exe'
.venv/Scripts/python.exe scripts/verify_drawing_thermal.py --source <原始PDF> --output <新目录>
.venv/Scripts/python.exe scripts/verify_drawing_thermal.py --source <原始Duplex_IFC> --output <新目录>
.venv/Scripts/python.exe scripts/verify_drawing_thermal.py --source <原始Duplex_IFC> --output <新目录> --heat-pump
.venv/Scripts/python.exe scripts/verify_drawing_thermal.py --source <原始Duplex_IFC> --output <新目录> --heat-pump --capacity-only
.venv/Scripts/python.exe -m pytest tests/test_drawing_thermal.py -q
```

脚本按固定公开样本设定房间数和图纸标定断言，不是任意项目通用转换命令。输出包含 API 链路、输入哈希、模型版本、原生 SQL/ERR 与全部假设；失败也留档。
