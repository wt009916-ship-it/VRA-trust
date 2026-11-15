from pathlib import Path
import shutil, subprocess
root=Path(__file__).parent
repo=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()=='ced95a8dfb1ce05fc22ca2ad1e4b9d87be19eb68'
assert subprocess.check_output(['git','branch','--show-current'],cwd=repo,text=True).strip()=='feature/agent-record-comparison-20261115'
assert subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True).strip()=='?? backend/agent_comparisons.py'
shutil.copy2(root/'agent_comparisons.py',repo/'backend/agent_comparisons.py')
p=repo/'backend/agent.py';s=p.read_text(encoding='utf-8')
def replace(old,new,count=1):
 global s
 assert s.count(old)==count,(old,s.count(old))
 s=s.replace(old,new)
replace('from . import agent_outputs, agent_actions, agent_selections, agent_metric_reads','from . import agent_outputs, agent_actions, agent_selections, agent_metric_reads, agent_comparisons')
replace('class ToolArgs(Contract):','class ToolArgs(Contract):\n    comparison: agent_comparisons.Comparison | None = None')
replace('\nTOOLS = {',"\nTOOLS = {\n    'professional_compare': '比较本轮已读的两份热工/成本/碳清单同一指标。明确baseline基准与candidate对照，选择fact_key和所需outputs（difference=对照减基准；relative_change_percent=除基准的百分比）。只选来源与指标，不填数值。应用核对口径并计算；零基准百分比无定义，口径冲突正式返回不可比。不是全年节能、性能等效或认证。',")
replace('TOOL_FIELDS = {',"TOOL_FIELDS = {\n    'professional_compare': ('comparison',),")
replace("if name in {'calculation_prepare','professional_read_many','requested_availability'}:","if name in {'calculation_prepare','professional_read_many','requested_availability','professional_compare'}:")
replace("'professional_read_many', 'professional_deliver','professional_limit'} |", "'professional_read_many', 'professional_deliver','professional_limit','professional_compare'} |")
replace("offered|={'professional_read_many','professional_deliver','professional_limit','professional_missing','professional_review'}", "offered|={'professional_read_many','professional_deliver','professional_limit','professional_missing','professional_review','professional_compare'}")
replace("if body.objective != 'open_ended':offered -= {'professional_deliver','professional_limit','professional_missing'}", "if body.objective != 'open_ended':offered -= {'professional_deliver','professional_limit','professional_missing','professional_compare'}")
replace("            result = self.tools(available)","            if not agent_comparisons.candidates(record):available.discard('professional_compare')\n            result = self.tools(available)")
replace("                if name in choices:\n", "                if name == 'professional_compare':\n                    replacement=agent_comparisons.tool_schema(tool,record)\n                    tool.clear();tool.update(replacement)\n                if name in choices:\n")
replace("                if name == 'professional_missing':\n                    candidate =", "                if name == 'professional_compare':\n                    request=agent_comparisons.Comparison.model_validate(canonical['comparison'])\n                    for ident in (request.baseline_id, request.candidate_id):\n                        ensure_read_scope(inspection(ident.split('_')[0]),ident)\n                    result=agent_comparisons.evaluate(self.domain,record['project_id'],record,request)\n                    event.update(status='succeeded',result=result,result_hash=core.hash_json(result))\n                    return result\n                if name == 'professional_missing':\n                    candidate =")
replace("                    new_deliveries = sum(c['function']['name'] in {'professional_deliver','professional_limit','professional_missing','professional_review'} for c in calls)", "                    new_deliveries = sum(c['function']['name'] in {'professional_deliver','professional_limit','professional_missing','professional_review'} for c in calls)\n                    new_deliveries += 2*sum(c['function']['name']=='professional_compare' for c in calls)")
replace("                        if call['function']['name']=='professional_missing' and result.get('status')=='verified':", "                        if call['function']['name']=='professional_compare' and result.get('status') in {'verified','unavailable'}:\n                            finish_requested |= result['reference']['finish']\n                        if call['function']['name']=='professional_missing' and result.get('status')=='verified':")
replace("            answer = agent_reviews.attach(answer,self.domain,project_id,record)", "            answer = agent_comparisons.attach(answer,record)\n            answer = agent_reviews.attach(answer,self.domain,project_id,record)")
replace("                if record.get('capability_delivery'):\n                    answer = capabilities.attach(answer, record['capability_delivery'],", "                answer = agent_comparisons.attach(answer,record)\n                if record.get('capability_delivery'):\n                    answer = capabilities.attach(answer, record['capability_delivery'],")
replace("'记录不完整、模型不适用或stale时，", "'需要两份记录同一指标差值时，先选字段并读取双方，再用professional_compare明确基准、对照与所需输出；应用计算并交付来源，不用自由文字替代。'\n                    '记录不完整、模型不适用或stale时，")
p.write_text(s,encoding='utf-8')
print('Installed isolated comparison branch')
