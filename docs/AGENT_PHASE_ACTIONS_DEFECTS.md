# 本批缺陷、证据和复现

证据根目录validation/agent-phase-contract-20261113。原始冻结问题在live-repair/frozen-tasks.json；固定模型和源文件摘要在receipt。后续复验不覆盖首次结果。

## PA-01 目录阶段自由原文可冒充交付：限定协议通道已修复
- 功能：open_ended动作和工程交付。
- 描述：PR73 D02仅读目录即可输出虚构正式交付；tool_choice=required也不保证没有自由原文。
- 复现：查看probe/P2，或历史D02；尝试用未数值读取的事实提交回执。
- 预期：仅执行可验证动作，未读事实不得交付。
- 实际：required探针3次均有工具，但P2另有自由文字；JSON探针3/3格式合规，P6却语义选错。新协议36次实际动作格式合规，实际数值来自当前已读回执并重查；目录和旧回执被拒。
- 严重程度：高；开放任务协议通道修复，不代表全部语义或注入问题关闭。
- 证据：probe/receipt.json、probe-json/P6.json、tests/test_agent_actions.py、live-repair/model-calls、assessment.json。
- 建议：保留原始公开响应审计；继续独立评价工具选择和问题完整性，其他inspect协议不能据此算全覆盖。

## PA-02 两条系统消息与本机模板不兼容：已修复
- 功能：本地模型动作传输。
- 描述：动作协议在已有系统消息前再插入系统消息，本机模板只允许一条起始系统消息。
- 复现：57cce4b运行live-final冻结任务。
- 预期：原任务和权限完整保留并进入推理。
- 实际：12题HTTP500、Jinja提示System message must be at the beginning，全部未推理；2db70b4合并起始系统消息后可执行。
- 严重程度：高，真实运行阻断，已修复。
- 证据：live-final/model-server.log及12个task；test_action_payload_consolidates_existing_system_context_for_local_template；live-repair。
- 建议：新模型适配必须验证实际模板，简化探针不能替代应用完整消息验收。

## PA-03 合法JSON中的指标名错误、反复读取目录：未修复
- 功能：自主能耗读取、多工具恢复。
- 描述：schema的fact_keys仍是任意字符串，目录得到的指标没有成为下一次读取的动态枚举；批量读取不携带能耗指标。
- 复现：A03要求CV(RMSE)；O02要求比较小时数及墙体U。
- 预期：选择cvrmse_percent或compared_hours，读到对应数值后交付；错误后实际纠正。
- 实际：A03把请求键cv当指标，随后4次professional_read_many只读目录，未交付；O02使用comparison_hours两次，达到预算后失败。没有错误数值通过。
- 严重程度：高，关键自主任务失败。
- 证据：model-call-007至011、023至026，A03/O02-task.json。
- 建议：动态字段schema和每记录选择式批量读取；明确目录/数值进度，不提高预算掩盖重复。新题验收，不修某句特例。

## PA-04 对明确的零账单问题多余澄清：未修复
- 功能：原意理解和无定义值说明。
- 描述：把用户明确要求的无定义指标和原因，误处理成需要用户再次选择的说明形式。
- 复现：A05明确要求CV(RMSE)及无法定义原因，禁止显示0%。
- 预期：读取null事实及来源原因，说明分母为零。
- 实际：模型未读取就询问要数学原因还是状态；用户已经要求两者，未完成任务。
- 严重程度：中，不是伪造数值，但不能按安全拒绝计成功。
- 证据：model-call-015、A05-task.json。
- 建议：区分未知用户意图和已知指标无定义；澄清入口不能成为跳过明确要求的捷径。

## PA-05 关系解释从模型计划中遗漏：未修复
- 功能：多来源专业解释。
- 描述：模型计划只包含数值字段，缺失用户同时要求的载体关系；字段覆盖无法检测这类遗漏。
- 复现：A06要求燃气能量、电力能量，并问同为kWh能否当成用电量。
- 预期：数值和载体正确，明确同一能量单位不能等同能源载体。
- 实际：计划只列两个数值且explanation_topics为空。控制器异常修复后两个数值正确、output_contract_coverage=fulfilled，但仍无关系回答；整个自由任务仍partial。不能据此判语义完成。
- 严重程度：高，计划覆盖与用户问题脱节。
- 证据：live-repair/model-call-016、A06-task.json；live-deferral-fix/A06-task.json。
- 建议：关系解释作为独立义务保留目标、来源和验证状态；不能把字段覆盖或值清单当成关系解释。

## PA-06 同批交付后被拒的澄清触发KeyError：已修复
- 功能：失败恢复。
- 描述：控制器对失败动作仍按成功返回读取finish字段，造成未捕获的键缺失。
- 复现：同一响应先两次professional_deliver，再requested_defer已经交付的请求键。
- 预期：澄清被拒并作为可恢复错误保留，已交付来源继续可核验。
- 实际：2db70b4对TOOL_ERROR直接索引finish导致A06失败；最终仅对needs_clarification读取该字段。单元同批回归和真实A06复验无崩溃。
- 严重程度：高，已修复控制异常，A06语义仍失败。
- 证据：backend-defer-fix.log、live-deferral-fix；test_failed_defer_after_delivery_in_same_batch_is_recoverable。
- 建议：所有动作完成标志绑定成功状态，批内状态变化不能沿用批前资格。

## PA-07 状态任务开放必被拒的数值工具：已修复
- 功能：来源失效说明和动态工具目录。
- 描述：动态schema和执行资格不一致，对纯状态任务提供了数值工具。
- 复现：A08，墙体要求R，撤销确认的账单只要求当前状态。
- 预期：墙体交付R，账单做非数值来源审查，不交旧能量。
- 实际：原schema开放professional_limit，执行拒绝且整任务失败；非数值热工也触发空数值选择schema。最终排除review_ids的数值交付/限制入口，A08真实回归通过且账单stale、numeric_values_delivered=false。
- 严重程度：高，已修复；未发现撤销数据数值泄露。
- 证据：live-repair/A08；backend-status-fix.log、backend-status-final.log；live-status-fix/A08；test_status_only_plan_never_offers_numeric_limitation_substitute。
- 建议：开放给模型的schema必须与当前执行前置条件一致，保留非数值与数值交付的区分。

## PA-08 不确定退出仍被未解决读取拦回循环：已修复控制路径
- 功能：一般自由任务澄清。
- 描述：显式不确定状态仍被常规完成检查拦回重试，未能实现已声明的澄清退出。
- 复现：先失败的多记录读取，再requested_defer；O02也出现澄清后继续调用直至预算耗尽。
- 预期：以incomplete/partial退出，保留未解决目标；不能声称资料缺失或任务完成。
- 实际：原控制器继续尝试；最终question_deferred单独终止，不设model_finished_delivery，实际失败目标仍在列表。
- 严重程度：中，契约回归通过；O02完整自主任务未重测，不改原失败分。
- 证据：backend-defer-exit-final.log、test_open_question_defer_stops_after_selected_read_without_false_completion；原O02-task.json。
- 建议：后续新模型题验证实际澄清体验，不能用该回归宣称小时数选择已修复。


## PA-09 全部开放任务协议切换后漏适配两组测试驱动：已修复并记录安排缺陷
- 功能：工程和服务恢复CI。
- 描述：局部专项遗漏工程mock中的旧Statement schema及故障传输mock中的原生tool_calls，导致完整CI才暴露27个格式失败。
- 复现：2db70b4或aaed498运行test_agent_engineering.py和test_agent_service_recovery.py。
- 预期：测试驱动遵循当前动作/事实选择协议，继续断言独立算术、重试预算、来源失效和不重复写入。
- 实际：旧驱动4个工程及23个故障用例失败；bb21a9c只适配两个测试文件，56项受影响回归通过，原断言没有删除或放宽。产品源码未变。
- 严重程度：中，测试覆盖安排失误造成额外CI等待；已修复。
- 证据：pre-fix-ci/backend.log、pre-fixture-ci/backend.log、backend-ci-fixture-fix.log及bb21a9c差异。
- 建议：协议/控制流程改动提交完整CI前，一次覆盖全部受影响Agent和网关组；独立物理黄金批不因此重跑。


## PA-10 中文紧贴明确记录ID时未开放直接读取：静态复现，待修复
- 功能：一般开放任务的记录目标提取。
- 描述：正则使用Unicode词边界\b；中文与ASCII字母都属于词字符，紧贴时没有边界，ID被漏掉。
- 复现：以原O01/O02冻结问题运行backend/agent.py中的记录ID正则；与完整ASCII标识符边界匹配比较。
- 预期：完整ID得到识别并在当前项目授权下开放读取，不必先查目录。
- 实际：现行正则两题均未识别到目标ID；实际第一动作均为professional_inventory。静态替代边界能匹配，但尚未实现或实际验收。O02另有指标名错误，不能据此认定仅修边界就能全部通过。
- 严重程度：中，增加模型轮次和事件消耗，部分失败不能全归因于模型。
- 证据：next-metric-diagnostic.json、live-repair/O01/O02-task.json及冻结问题。
- 建议：下批先修复完整ASCII标识符边界，加入中英文相邻、截断、括号和跨项目反例；不改变项目权限。
