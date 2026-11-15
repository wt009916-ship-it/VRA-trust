# Agent阶段动作与回执证据

最终bb21a9c（业务源码同aaed498）、草稿PR74，未合并或部署。assessment.json原冻结12题严格7/12，36次实际模型JSON响应；显式2/2、开放2/3、声明自主1/3、边界1/1、未知1/1、关系0/1、恢复0/1。候选78.5不变。

probe及probe-json保留前置协议测试（P6格式正确但语义选错）。live-first是未进入模型的闰年附件设置失败；live-final为57cce4b的两系统消息传输失败12/12；live-repair为2db70b4传输修复后一次完整语义执行。live-deferral-fix仅A06控制器回归，不崩溃但关系仍失败；live-status-fix仅最终A08回归通过。不得覆盖原7/12或将后两项称新盲测。

公开合成输入沿用validation/utility-comparison-20261109/frozen-v2中的2020；新墙体参数和Fraction答案在frozen-tasks/independent-oracle。API、EnergyPlus、固定9B均真实执行；无浏览器替代验收，无云端模型实测、训练或实楼校准。所有临时进程已停止。

source-integrity记录五次运行共555个源码字节摘要，source-snapshots保留两种未提交中间状态。未改旧摘要；源文件LF/CRLF匹配单列。私有运行数据库、口令、令牌、模型权重、大型SQL不入库。失败与原始响应、受影响测试、三次精确CI都保留；首次CI不能替代最终CI。证据文件以.gitattributes -text保留字节。
