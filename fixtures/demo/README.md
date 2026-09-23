# Demo / reference isolation

frontend-data：历史 dashboard、材料、几何和任务示例 JSON。可能含写死数值，仅保留作历史设计/测试参考。活动前端不引用这些数据，生产 API 没有静态结果 fallback。
frontend-public：旧图标资源。
reference_5zone：官方 EnergyPlus 9.0.1 模型派生的参考输入，不是历史结果。只有用户明确导入参考项目后，才复制进项目文件仓库并登记为待确认 IMPORTED 证据。结果必须重新运行物理引擎。

参考项目标记 engineering_reference / REFERENCE·非实测；追加保温与碳因子保持教学假设。不得用作稀土实测性能或真实建筑节能成绩。
