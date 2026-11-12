import json,re
from pathlib import Path
root=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108');b=root/'validation/agent-phase-contract-20261113';f=json.loads((b/'live-repair/frozen-tasks.json').read_text(encoding='utf-8'));rows=[]
for ident in ['O01','O02']:
 task=next(t for t in f['tasks'] if t['id']==ident);q=task['message'];old={};literal={}
 for kind in ['thermal','utility']:
  old[kind]=re.findall(r'\b'+kind+r'_[a-f0-9]{32}\b',q)
  literal[kind]=re.findall(r'(?<![A-Za-z0-9_])'+kind+r'_[a-f0-9]{32}(?![A-Za-z0-9_])',q)
 rows.append({'task':ident,'question':q,'current_word_boundary_matches':old,'complete_ascii_identifier_matches':literal,'observed_first_model_tool':'professional_inventory','scope':'Static reproduction against exact frozen message and actual first action; revised parser has not been implemented or accepted.'})
assert rows[0]['current_word_boundary_matches']['thermal']==[] and len(rows[0]['complete_ascii_identifier_matches']['thermal'])==1
assert all(not values for values in rows[1]['current_word_boundary_matches'].values())
p=b/'next-metric-diagnostic.json';d=json.loads(p.read_text(encoding='utf-8'));d['identifier_boundary_reproduction']=rows;d['confirmed_gaps'].insert(0,'Regex Unicode word boundary prevents explicit ID extraction when Chinese text is adjacent, unnecessarily withholding direct read tools.');p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=root/'docs/AGENT_METRIC_READ_PLAN.md';s=p.read_text(encoding='utf-8');s=s.replace('1. 让当前能耗指标目录约束实际读取参数。','0. 先修复一般开放任务的明确ID提取。原\\b在中文紧贴ID时漏识别，O01/O02被迫先查目录；next-metric-diagnostic已对原冻结文本静态复现。用完整ASCII标识符边界，验证中文/英文/括号/截断及跨项目反例；保留项目归属核验，不把放宽字符串边界当放宽权限。\n1. 让当前能耗指标目录约束实际读取参数。');p.write_text(s,encoding='utf-8')
p=root/'docs/AGENT_PHASE_ACTIONS_DEFECTS.md';s=p.read_text(encoding='utf-8')+'''

## PA-10 中文紧贴明确记录ID时未开放直接读取：静态复现，待修复
- 功能：一般开放任务的记录目标提取。
- 描述：正则使用Unicode词边界\\b；中文与ASCII字母都属于词字符，紧贴时没有边界，ID被漏掉。
- 复现：以原O01/O02冻结问题运行backend/agent.py中的记录ID正则；与完整ASCII标识符边界匹配比较。
- 预期：完整ID得到识别并在当前项目授权下开放读取，不必先查目录。
- 实际：现行正则两题均未识别到目标ID；实际第一动作均为professional_inventory。静态替代边界能匹配，但尚未实现或实际验收。O02另有指标名错误，不能据此认定仅修边界就能全部通过。
- 严重程度：中，增加模型轮次和事件消耗，部分失败不能全归因于模型。
- 证据：next-metric-diagnostic.json、live-repair/O01/O02-task.json及冻结问题。
- 建议：下批先修复完整ASCII标识符边界，加入中英文相邻、截断、括号和跨项目反例；不改变项目权限。
''';p.write_text(s,encoding='utf-8')
p=b/'environment-failures.json';d=json.loads(p.read_text(encoding='utf-8'));d['failures'].append({'type':'audit_script','step':'frozen-task equality normalization','detail':'First comparison used Unicode word boundaries and did not normalize IDs adjacent to Chinese. Correct ASCII identifier boundary matched the complete original task bodies/expectations across all transport and bounded repairs. This also exposed the existing product ID extraction defect PA-10; product remains unchanged.'});p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(rows,ensure_ascii=False))
