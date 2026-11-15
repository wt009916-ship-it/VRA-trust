# 本批证据与复现

- 首轮真实任务产品：fa30deff733b331f052f6da764c67b1cba5fc89a。
- 上下文修复最终产品：0d46616e1a7682ee5f44c5e3242809570cb67f0b，PR72草案。
- 原16题：live-configured-20261113/frozen-tasks.json；逐题原始API响应、任务审计及model-calls保留。first-screen-assessment.json严格12/16，E13/E14关键失败，不采用。
- 额外修复新题：live-holdout-20261113/frozen-tasks.json，H01/H02为2/2；不替换原16题。两题有错误字段名拒绝与恢复轨迹。
- 物理输入复用validation/utility-comparison-20261109/frozen-v2。这是为了建立新Agent记录的受控来源，不计为新独立物理覆盖或实楼验证。
- native-evidence保留新运行manifest、结果、警告日志与全部文件摘要；大型SQL/原生中间文件留在receipt中声明的隔离runtime，不上传业务数据库。原件未覆盖，旧撤证记录未改哈希恢复。
- product-source-integrity.json核验两个运行时所有backend源码与各自Git提交一致，明确LF/CRLF及agent_energy.py混合换行字节差别；首次不匹配诊断和该文件原始字节另保留，不改历史指纹。
- post-ci/ci-receipt.json对应最终精确产品提交。旧fa30def后端因真实修复被取代取消，不能算通过。

复现环境：Python及backend/requirements-dev.txt；EnergyPlus9.0.1；既有llama.cpp及Qwen3.5-9B-Q4_K_M。模型和runtime SHA在冻结任务中，未下载/训练/换模型。本机启动参数和全部模型原文保留。应用本身temperature=0，未增加隐藏重试或按模型答案换题。

先将frozen-v2复制到新的隔离目录，解压weather.epw.gz为weather.epw，逐一核验frozen.json的files摘要。live_acceptance.py与holdout_acceptance.py保存实际执行脚本；在副本中只调整ROOT/SOURCE/MODEL/EXE和全新的输出/runtime路径到本机环境，再运行。不得覆盖已存在的证据目录。新运行会产生新的随机记录编号、账号和时间；数值/语义条件可复核，不承诺模型文字逐字重现。固定原题的重复结果不能回写本次首次通过率。

serve分支仅包装LocalModelGateway.complete记录传入消息与未经修改的返回，不替换模型、不替换计算结果；服务仍经真实uvicorn/HTTP/API/来源校验。口令与本地模型令牌运行时随机生成，只在进程内存/环境传递，未保存到这些证据。浏览器未启动；没有外部服务攻击或压力测试。

首次失败保留：integration-syntax-first.json、backend-first/backend-corrected、backend-agent-regression-first、各schema压缩日志；frontend-build-20261113缺依赖；live-first-20261113缺ENERGYPLUS_EXE而409。修复只发生在隔离代码或验收环境，不修改计算结果让测试通过。

运行器receipt内manual_review=pending是原始运行结束时状态，保持原件不改；最终人工原文核对与严格判定见first-screen-assessment.json及holdout-assessment.json。两个新原生运行各有3条Warning/0 Severe，完整警告日志已保留，不按零警告宣称。

最终产品67e79959fbdf119f8ed782109e28bf29811b05b2仅继续修复未授权探测/状态的默认目录预算，实际任务使用的完整显式工具定义SHA不变，见default-tools-repair.json。0d46616失败CI在ci-0d46616-failed。没有在67e7995重跑模型题，不能把旧题结果标为该提交的再次完整实测。
