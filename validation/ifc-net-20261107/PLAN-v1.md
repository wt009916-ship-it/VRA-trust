# IFC 开洞补强

基线 PR49 / 396bda09ae9e95a31fbb493ab0f518a2fd38b5ff 已发布。IFC-NET-01（高）：全覆盖洞口独立答案为 0 m³，Windows/Linux 及隔离API均返回24 m³宿主原体积。证据 probe-windows-v1.json、probe-linux-v1.json、api-probe-windows-v1.json。原件保留。

原生日志 GEO124 / GEO140 指向二维布尔路径；补全轴与弧度单位后仍复现。关闭 boolean-attempt-2d 后为空网格/null，其余七例与独立答案一致，见 boolean-ab-windows-v1.json。当前修改采用该保护，未知不冒充零。解析器哈希自然改变，不重写历史记录。

接下来完成米/毫米真实API专项、双平台同字节8例、重叠/穿出/相切/重复关系/斜向映射/空间聚合、公开模型及全量回归，再浏览器失效/报告与CI发布。重复关系未审查、跨构件净量及专业扣减规则仍开放。不能把本次有限防护当全部净量能力完成。95+仍未达。

当前独立开发仓库位于 C盘 vra-design-release-a773af75c60e4c7db80c7091a498175b，分支 fix/ifc-opening-boolean-20261107。D盘Git对象junction目标消失；已从GitHub恢复本仓库主线对象，本地缓存的原仓库backup分支对象仍缺，不能宣称全部历史恢复。原D业务表和SKILL编辑保全通过。PR49最终回执在 ../design-inputs-20261107/release-receipt.json；原型由launch_prototype_v2.py启动，launcher21244。
`n本轮已实施 boolean-attempt-2d=False，新增4个真实隔离API案例（米/毫米 × 全覆盖/普通穿洞），连同既有测量/拓扑共34项通过（85.67秒），Ruff和diff检查通过。尚未做本修复的双平台全量、公开模型及浏览器验收，未提交/发布修复。当前原型仍为PR49。`n仓库主线对象已从公开GitHub重新获取并复制到本C仓库，已不依赖消失的D盘objects junction。旧origin/backup缓存引用指向的对象仍缺；自动审批拒绝了清理缓存引用，未执行删除，不绕过审批重试。保留这些引用，继续不依赖清理的工作。PR49最终release-receipt于07:17:51Z验证通过。
