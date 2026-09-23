# 重放验收

从运行记录下载原始证据 ZIP，在单独目录解压并保留目录名为原 run_id（core 会核对目录名绑定）。
执行：`python scripts/replay.py path/to/run_<id>`。
脚本先核对 manifest 文件哈希与 run_id，再要求当前引擎/IDD 哈希与原运行一致。输出写入全新的 runtime/replays/run_<id>，不会覆盖历史。
比较年能耗差值容差 0.01 kWh，并记录原/新代码版本。数值复现成功只证明计算可重放，不证明建筑校准或当前决策有效。
代码版本变化可能导致历史结果 stale；不要改写历史 manifest。应以原版本检出或明确声明新版本复算。

原始输出包括 SQL、ERR、stdout/stderr、输入快照、请求、manifest、result；失败记录同样保留。GET report.json/PDF 再次查询当前有效性，已经下载的 PDF 只是生成时快照。
