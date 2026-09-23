# 公开参考模型来源（2026-09-23 核对）

1. [EnergyPlus v9.0.1 官方 5ZoneAirCooled](https://github.com/NatLabRockies/EnergyPlus/blob/v9.0.1/testfiles/5ZoneAirCooled.idf)：与本机引擎匹配，本轮已使用其派生输入实跑三方案。原版设计日需与 Golden EPW 对齐；本地准备脚本保留转换和材料假设。[官方许可](https://github.com/NatLabRockies/EnergyPlus/blob/v9.0.1/LICENSE.txt)及本地 third_party_notices 随附。
2. [OpenStudio Resources](https://github.com/NatLabRockies/OpenStudio-resources)：包含测试/示范建筑模型和模拟资源；[LICENSE](https://github.com/NatLabRockies/OpenStudio-resources/blob/develop/LICENSE.md)允许附条件再分发，须保留版权及免责声明，不能暗示官方背书。模型通常需 OpenStudio 翻译并匹配 EnergyPlus 版本；本轮未下载执行，不声称兼容已验证。
3. [DOE Commercial Reference Buildings](https://www.energy.gov/cmei/buildings/commercial-reference-buildings)：可用于办公、学校等类型的公开参考研究；先选择建筑年代/气候区并核对文件许可和引擎版本。不是具体业主建筑的实测校准数据。

公开模型能补充软件验收和方法对照，不能替代真实既有建筑图纸、账单、设备参数与运行记录。没有真实现场数据，Golden Path 仍标为 reference，而非真实建筑验证完成。
