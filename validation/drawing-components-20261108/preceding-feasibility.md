# 构件识别可行性检查（2026-11-08，尚非能力交付）

当前代码基线：f9fa47a824ec7d0f5e3664d2c9d6a27652568912，PR57。检查未修改活动服务、原型、模型或业务数据；没有重新执行上一轮 Agent 题目。

## 已查明的实际缺口

`backend/drawing_worker.py` 的实际输出是 OCR 文字候选，`drawing_processing.py` 实现有界旋转、方向建议、中值过滤、差异像素与坐标矩阵。它们没有输出墙、门、窗的语义分割或实例分类。D08 仍未实现；不能用原件保全、OCR 框、IFC 源类型或人工标注代替。已有 `onnxruntime` 与 OpenCV 可复用，但目前验收虚拟环境没有 PyTorch、Transformers 或 safetensors。这是环境事实，不是算法不可实现的证明。

## 已核对的来源，下一轮不重复搜索

|来源|读到的事实|本轮决定|
|---|---|---|
|[CubiCasa5K 原许可证](https://github.com/CubiCasa/CubiCasa5k/blob/master/LICENSE)|CC BY-NC 4.0|没有下载、训练或集成。不能仅凭下游仓库的 MIT 标签宣布训练数据与模型已具备商业交付条件；本轮也未对衍生权重许可作法律裁定。|
|[FloorPlanCAD 原发布页](https://floorplancad.github.io/)|标注为 CC BY-NC 4.0，发布者声明不拥有图纸版权|没有下载或集成。|
|[WAFFLE 官方仓库](https://github.com/TAU-VAILab/WAFFLE)|提供独立语义分割基准入口；每图有 Wikimedia 来源链接。README 将代码许可链接到 Commons 通用许可说明|尚未取得基准与具体标注许可，不把通用链接当作一份确定的模型/代码许可证；不将其报告性能作为本应用性能。|
|[FloorplanToBlender3d 官方仓库](https://github.com/grebtsew/FloorplanToBlender3d)|GPL-3.0；作者明确列出对图像尺寸的限制|未复制代码或引入依赖。GPL 不等于禁止商业使用；仍需先明确当前项目的分发方案，且其演示不证明复杂残图识别能力。|
|[Microsoft Florence-2-base 模型卡](https://huggingface.co/microsoft/Florence-2-base)|通用视觉模型，模型卡标为 MIT|仅为一个待评估候选，没有下载或运行。模型卡不提供本项目墙/门/窗可靠性的证明；不能以通用检测能力直接关闭 D08。|

## 已取得的公开参考输入

- 来源：[Floor plan 1.jpg](https://commons.wikimedia.org/wiki/File:Floor_plan_1.jpg)，作者 Ashlynn Schindler，页面注明作者将作品置于公有领域。
- 下载地址：https://upload.wikimedia.org/wikipedia/commons/1/18/Floor_plan_1.jpg
- 原件：`C:/Users/18483/AppData/Local/Temp/vra-floorplan-feasibility-20261108/public-floor-plan-1.jpg`。
- 25322 字节，1096×602，SHA-256 `f1c7d5f3bbc3abbe4395166ed92224c07ef588a3ff4ce7470980a6cfd2c89625`。
- 已实际查看图片：包含房间边界、门扇/开启弧、窗符号及卫生设施，四周有大面积留白。尚无独立标签；这只是开发参考输入，不是冻结盲测集，更不是实楼验收。

## 对当前安排的约束

1. 当前提交 CI 收口前不改该提交、重启检查或重跑未变物理算例。CI 的运行状态见同目录 `standard-ci-*.json`。2026-11-08 00:20:09 UTC 时后端测试约运行9分钟，没有足够证据判定卡死；前端及契约已通过。
2. 后续第一件具体工作是取得独立标签并冻结未见图片/评价口径，然后只选一个许可明确的实际识别方案做有限基线。当前只有一张无标签图，不应先开发空的识别 API 或把新表单当能力。
3. 评价必须分墙分割质量、门/窗实例定位和分类，统计误报及漏报；空输出、不确定输出均不能算识别正确。开发图、扰动后的同图与真正未见图分开统计。人工/AI 辅助标签应标明作者及复核状态，不冒称第三方金标准。
4. 原件哈希、像素坐标映射、缺失结构不补造和受限资源属于交付条件；它们不替代识别准确率。识别候选不得自动变成数量、尺寸或结构结论。
5. 一次有限基线不足以支持商业成熟度；若基线失败，保存失败并判断是数据、算法还是运行预算不合适，不对同一图片不停改阈值后称盲测通过。没有证据支持当前方案必能到95+。

本轮能力得分增量为0，既有开发侧证据复评仍75。这里完成的是选型和输入核查，不是构件识别开发或验收。未扩大训练，未绕过 PR56 审批，未发布 PR57。

## 本轮收口回执

- f9fa47a 三项 CI 最终全部成功，Backend 运行 42428550705：1355 passed、22 skipped、2 warnings、6 subtests passed，633.78 秒。完整状态保存在 `standard-ci-20261108T002642Z.json`，测试阶段原日志摘录为 `standard-ci-backend-pytest-excerpt.log`；PR57 描述已更新，回执 `standard-ci-pr-closed.json`。不再等待、重启或重复运行本提交 CI。
- 新的独立评价模块位于同目录 `drawing-components/evaluate.py`：门/窗以分类后一对一最大匹配计算 TP/FP/FN，墙体分别报告像素微平均及逐图宏平均 IoU；重复框、错分类、缺失整图结果不被隐藏。来源摘要或坐标系不一致直接拒绝；双方都空的类别指标为 null，不获得满分。
- 验证命令：`python -B -X utf8 -m pytest outputs/vra-soak-20261108/drawing-components/test_evaluate.py -q -p no:cacheprovider`。实际结果 13 passed in 0.10s。独立手算检查包括 2/5 墙体 IoU、重复框 F1=2/3、贪心匹配陷阱、错类别、未提交预测、越界/NaN、来源错配及空类。该结果只证明评分器这些边界行为，不证明识别算法表现。
- 评价模块和选型记录仍为本机研发准备材料，未加入活动应用。没有为了这份 CI 回执单独提交并再次触发相同全量测试。
- 下一次具体工作：直接复用上述来源核查与评分器，完成有可追溯标签的公开输入集；冻结样本和判据之后再运行一个识别候选。不要重做本页许可检索或启动另一轮规范提示词实验。
