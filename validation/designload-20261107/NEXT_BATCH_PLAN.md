# 设计日与分区显热负荷：下一批实施契约

状态：2026-11-07研究准备；尚未实现产品输出、尚未运行本批基准、不计分。天气批PR #44正在等待后端CI，不改变其冻结源码与证据。

## 已确认的问题

五个天气情景的原生ZoneSizes各有10行，但设计日仍是Golden。不能按EPW城市名重新命名为当地设计负荷。年度kWh也不能直接转换为设计峰值kW。天气质量筛查不证明设计工况的适用性。

EnergyPlus 9.0网页SQL文档列出DesLoad，但固定v9.0.1源码SQLiteProcedures.cc第896行和真实SQL均为CalcDesLoad、UserDesLoad。必须沿实际写入链核验单位、倍率与含义，不能只依赖网页字段表。源码只读保存及哈希见source-discovery-v1.json；其中ZoneEquipmentManager的匹配是注释，尚未证明真正写入调用点。

## 先建立独立答案

拟用新建合成单区：5 m×5 m×3 m，六面总面积110 m²，统一无热容材料热阻2 m²K/W、内表面对流系数10 W/(m²K)、外侧综合系数25 W/(m²K)，无窗、太阳、人员、设备、新风、渗透。六面外侧用同一OtherSideCoefficients控制，避免天空/地面温度引入未知项。室内冬20°C、夏25°C，恒定设计日冬−10°C、夏35°C，倍率1。独立答案Q=AΔT/(1/hi+R+1/ho)。同时核验实算边界、实际室温、六面内表面系数与净长波交换，不能只比较一个最终数值。

预设容差：显热负荷max(1 W,独立值×0.5%)；稳态室温偏差≤0.02°C。先跑原始R=2模型，随后R=4保温变化与不同温差的新模型；不得看结果后放宽容差。该设计尚待原生模型语法及物理边界验证，失败保存新版本，不覆盖初稿。

## 产品交付边界

1. 精确追踪分区冷/热显热计算负荷与用户调整负荷，分别标W/kW；不称设备总容量、潜热总冷负荷、全楼同时峰值或规范认证。
2. SQL源文件、行定位、引擎版本、输入模型、设计日参数和命名、来源声明/人工适用性复核统一绑定。人工确认不等于独立验证。
3. 缺少Sizing输出、重复/非有限/负值、未知版本、设计日名称无法解析或变更，输出未验证/null，不能从年度能耗推算补齐。
4. 设计日原始地点和EPW地点分别展示，来源缺失/不匹配须明确；不得自动替换工况或默认为适用。
5. 现有年度结果保持原判定链；若增加负荷所需的物理输出请求，生成新运行及指纹，历史manifest不改。
6. 分区求和只可标非同时峰值和；未经时序验证不提供建筑峰值。
7. API、前端、报告/ZIP同源，失败/旧版本不保留确定数值。加入篡改、缺失、单位和模型修订反例。

## 发布验收

先确认固定版本源码单位/倍率，再最小合成原生试验；再实现严格解析/工况来源、专项反例、公开模型跨输出交叉验证、双平台真实运行、认证API与浏览器，最后全量检查、独立复评、PR同步。仅本批验收范围可加分；RS-07、RS-09、一般注入、净量、DWG/图纸修复和实楼验收继续开放。

## 已检索的主要依据

- https://bigladdersoftware.com/epx/docs/9-0/output-details-and-examples/eplusout-sql.html
- https://bigladdersoftware.com/epx/docs/9-0/input-output-reference/group-design-objects.html
- https://bigladdersoftware.com/epx/docs/9-0/input-output-reference/group-thermal-zone-description-geometry.html#surfacepropertyothersidecoefficients
- https://github.com/NatLabRockies/EnergyPlus/blob/v9.0.1/src/EnergyPlus/SQLiteProcedures.cc
- 本机固定版本Energy+.idd、CondFD1ZonePurchAirAutoSizeWithPCM.idf：只读参考，不能照搬其设备/人员/PCM为独立答案。
