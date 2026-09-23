# 稀土智暖 VRA-Trust
本仓库服务既有公共建筑改造前期的可核验工程决策。保留残图补证、材料验证、工程工具、研究与产品主线。
修改前读 docs/CURRENT_STATE_AUDIT.md、docs/IMPLEMENTATION_STATUS.md 和 .agents/skills/vra-trust/SKILL.md。以代码和新运行证据判断实现，目标文档不是证明。
- 活动服务 backend/api.py；物理计算复用 backend/core.py。frontend/legacy、legacy 是归档，含 mock，不能自动导入活动服务。
- 缺证、严重 ERR、失败或 stale 不输出确定结果；空值为 null/—，禁止 Demo fallback。
- fixtures/demo 仅供明确选择的参考输入/历史示例。参考模型真实运行不等于实测建筑。
- 修改证据保留版本和失败记录。不得重写历史 manifest 消除 stale。
- 能耗、运行 CO2、LCA、可交易信用分开；稀土、校准、稳定性和收益各需证据。
- 每阶段测试/构建/验收并更新状态，不因局部测试通过宣称全部集成完成。
- Git 排除 runtime、runs、原包、私有资料、密钥、依赖、大型输出。main 稳定、dev 集成，feature/* 或 fix/* 经 PR。
- 账号由 backend/auth.py 管理；所有业务 API 与下载必须校验会话和项目归属，写请求校验 CSRF。自动验收使用隔离数据库，禁止创建正式用户或替用户设置密码。
- 用户授权本轮 Phase 0/1 及指定 GitHub 仓库建设；其最新指示优先于资料中的历史任务说明。

- Trust/Agent 增量见 docs/TRUST_AGENT_SPATIAL_DELIVERY.md。碳因子版本只影响碳节点，不能改写原 run 或要求重新跑能耗；物理核心版本改变仍使旧物理运行保守失效。
- LLM 配置只允许首个管理员账号；Windows 密钥用 DPAPI，Linux 由环境注入。不得提交 runtime/private/provider.json。
- 反例搜索当前限定 Material 导热系数离散域，记录预算/覆盖/容差；无翻转不等于连续域稳定。补证收益是条件情景，成本须用户提供。
- 三维人工确认不改变来源性质；ASSUMED 不能显示为实测；未绑定 IDF 构件的 affected_claims 为空。
- 用户最新指示：服务器与第二台电脑访问暂缓，不擅自部署或声称完成实机验收。
