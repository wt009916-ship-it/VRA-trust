# 公开来源及使用边界

原件保存在本机隔离附件目录，未提交仓库。取得日期2026-10-29；原件URL、固定提交、字节数、SHA-256在私有附件manifest及本目录results.json摘要中记录。以下是本轮实际使用或查证的来源，不代表各源均经过完整工程验收。

|来源|用途|版本及边界|
|---|---|---|
|[Vanderbilt作者文档](https://iahmed.me/EngineeringScienceBuilding/datasets/v1/dataset.html)、[公开历史源](https://github.com/hazrmard/EngineeringScienceBuilding/tree/0ffc3c8234ecca50606cfd9ed1e1d464f998b832)|两台实际冷机及各自辅助设备工况、单位转换链|历史CSV是来源方预处理记录；未找到明确仓库再分发许可，不在Git分发原件；原始流量单位尚待核对|
|[IFC-Bench作者数据集](https://huggingface.co/datasets/sylvainhellin/ifc-bench)|作者问答、模型卡、许可与源IFC语义清点|固定9ba471a3e38b353a81a1dc9ecb4aa56d2ce0a7fa；问答声明CC-BY-4.0，各模型MIT/GPL/CC-BY等分别保留；不把幻想模型计作真实工程，不自动推断商业训练权利|
|[KAAN公开源仓库](https://github.com/datarefinerylab/kaandataset)|四个实际委托设计项目的楼层WKT与来源标签|固定8c21b118bfdba7832ff5adcaa99b5544b65221d5；仓库BSD-3-Clause声明不自动解释为所有委托资料的商业微调许可；待核实|
|[RP1043再发布数据](https://figshare.com/articles/dataset/Chiller_operation_data_set/28435232/1)|下载51MB包，检查11000.xlsx字段|属于实验台；不是现场冷站；所检子集缺同步流量/冷量/明确时间，不计完整校准通过|
|[Honda/HRI现场数据](https://datadryad.org/dataset/doi:10.5061/dryad.73n5tb363)|核实实际建筑三冷机、计量口径和处理过程|元数据可读，公开下载链返回403/401，未绕过访问控制；没有取得原数据并通过校准，不计已测|
|[Izmir太阳能制冷作者数据](https://zenodo.org/records/18798441)|取得公开运行CSV及字段说明|太阳能/吸收式边界，未提供单冷机电输入；Q_solar不自动等同吸收机热输入，不用于冒充电冷站校准|
|[MLStructFP作者仓库](https://github.com/MLSTRUCT/MLStructFP)|核实真实图纸数据取得条件|完整数据需作者表单，未代用户提交或发信；未把摘要中的954图/165工程当作已获得或已验证|

这批资料没有提供15个工程、20种形态、每功能10个真实场景的完整交叉真值矩阵。重复专业模型、楼层、同站设备、实验台和计算生成数据分别记录。
