# 中央水系统输入

将[明确假设的风冷/燃气示例](air-cooled-scenario.json)下载为JSON，在「建模工作区 → 热工 → 中央冷热源、水泵与风机盘管」导入。示例仅用于软件演练，冬夏设计日为作者情景，不是源建筑当地设计条件、厂家选型或已安装设备。

导入只预填中央参数并绑定项目上传文件；仍需复核空间、运行档案、天气、围护结构、容量与适用性后保存和发布。不能与PTHP同时启用，新风热回收须为0。未知参数不要用此示例替代工程资料。

容量`null`明确表示原生设计日自动选型。末端盘管和水流量也按设计日选型；没有恢复原机电容量。水冷时须将`condenser`改为`WaterCooled`并提供`condenser_pump_head_pa`，原生展开增加冷却塔和冷却水泵。锅炉可选`NaturalGas`或`Electricity`，分能源SQL结果随之改变。

`design_days`支持2–8条，须同时有冬夏；编辑器保留全部条目。温度°C、容量W、压头Pa，风速m/s、风向角度。湿球不得高于干球；风机总效率不能高于电机效率。完整边界以[ModelDraft Schema](../../shared/schemas/building-model.json)的`CentralSystem`/`DesignDay`定义为准。

`basis=documented_design`必须由API绑定本项目原件ID和哈希。上传时不用自行填写`source_file_id`/`source_file_hash`，服务器会绑定；保存时仍再次核对。通用参考设备曲线始终是假设，不能因为有JSON就变成厂家性能证据。

当前原生四管制拓扑不包含源MEP连接自动转换、管长热损、详细水力平衡、高楼分区供压、VRF或任意系统。见[使用方法](../../docs/INCOMPLETE_DRAWINGS_AND_SYSTEMS.md)及[实际运行、舒适性与失败](../../docs/benchmarks/2026-10-28-drawing-systems/README.md)。
