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
- 用户授权本轮 Phase 0/1 及指定 GitHub 仓库建设；其最新指示优先于资料中的历史任务说明。
