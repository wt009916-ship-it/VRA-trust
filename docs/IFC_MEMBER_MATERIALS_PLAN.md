# 梁柱材料计量开发与验收计划

2026-11-15。基于PR78/0fe30cd，原八维/87项95+目标不变；计划不加分。

去重核查：现有 ifc_beam_profiles 提取截面送梁分析，不交付材料量；ifc_layer_quantities 与 ifc_material_collection 仅支持墙/板，H01/H02范围仍缺梁柱。本批复用原生几何、材料关联和现有成本/碳工作流，不重做梁挠度内核。

交付链：实际IFC梁/柱→明确有效材料关联→原生开洞后实体网格核验→材料包络量→混选墙板梁柱、按材料实体去重→已有明确密度/损耗/报价/因子的两方案计算及失效报告。

先覆盖单一材料：直接材料或材料轮廓集；轮廓关联须与实际Body扫掠轮廓匹配，复合不同材料不按面积或厚度臆分。保留原始声明、关系ID、覆盖来源与几何结果。缺少、冲突、非均匀多材料或无可核验网格时不汇总。数量仍为模型包络，钢筋、连接件、施工计量规则和实物真实性不推断。

验收先冻结：开洞梁柱24-2=22m³；空心截面0.0576m³；两箱重叠48-12=36m³；米/毫米、旋转/平移、实例覆盖类型、同名不同材质ID与跨材相交；公开buildingSMART原始梁文件及独立截面面积×长度，不能以包围盒代替。之后实际隔离解析/API/成本碳/撤证链、前端逻辑与构建。浏览器仍依用户暂缓，不绕过。

依据：[buildingSMART IFC4材料关联](https://standards.buildingsmart.org/IFC/RELEASE/IFC4/ADD2/HTML/schema/ifcproductextension/lexical/ifcrelassociatesmaterial.htm)中的实例覆盖类型，以及[材料轮廓集使用定义](https://standards.buildingsmart.org/IFC/RELEASE/IFC4/ADD2_TC1/HTML/schema/ifcmaterialresource/lexical/ifcmaterialprofilesetusage.htm)。声明来源不自动证明几何/材料真实性。公开原文件沿用此前固定提交、哈希与署名；无再分发许可不上传原件。

PR78收口：已查精确提交三CI成功，后端2026通过/22跳过/2警告/6子测试，前端246+构建，接口30；该批复杂截面全场网格仍未过，不加分。保留原日志与当前回执。
