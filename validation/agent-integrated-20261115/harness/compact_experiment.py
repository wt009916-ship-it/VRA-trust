"""Lossless schema sharing experiment on the captured failed request; no model call."""
import copy,json,sys
from collections import Counter
from pathlib import Path
ROOT=Path('D:/稀土agent-稀土制暖全流程/.codex_work/vra-resource-leveling-20261115');sys.path.insert(0,str(ROOT))
from backend.agent_actions import schema
BASE=Path(__file__).parent

def compact(original):
    counts=Counter();nodes={}
    def eligible(node):
        return (isinstance(node,dict) and node.get('type')=='array' and isinstance(node.get('items'),dict)
                and isinstance(node['items'].get('enum'),list) and all(isinstance(v,str) for v in node['items']['enum'])
                and len(json.dumps(node,ensure_ascii=False))>=256)
    def visit(value):
        if isinstance(value,dict):
            if eligible(value):
                key=json.dumps(value,ensure_ascii=False,sort_keys=True);counts[key]+=1;nodes[key]=value;return
            for key,child in value.items():
                if key not in {'enum','const','default','examples'}:visit(child)
        elif isinstance(value,list):
            for child in value:visit(child)
    visit(original)
    names={key:'vra_shared_enum_'+str(i) for i,key in enumerate(k for k,n in counts.items() if n>1)}
    def rewrite(value):
        if isinstance(value,dict):
            key=json.dumps(value,ensure_ascii=False,sort_keys=True) if eligible(value) else None
            if key in names:return {'$ref':'#/$defs/'+names[key]}
            return {k:copy.deepcopy(v) if k in {'enum','const','default','examples'} else rewrite(v) for k,v in value.items()}
        if isinstance(value,list):return [rewrite(v) for v in value]
        return value
    result=rewrite(original);shared={names[k]:copy.deepcopy(nodes[k]) for k in names};result.setdefault('$defs',{}).update(shared)
    def expand(value):
        if isinstance(value,dict):
            if list(value)==['$ref'] and value['$ref'].startswith('#/$defs/vra_shared_enum_'):return shared[value['$ref'].split('/')[-1]]
            return {k:expand(v) for k,v in value.items()}
        if isinstance(value,list):return [expand(v) for v in value]
        return value
    expanded=expand(result)
    for name in shared:expanded['$defs'].pop(name)
    if not expanded['$defs'] and '$defs' not in original:expanded.pop('$defs')
    assert expanded==original
    return result,{'shared_definitions':len(shared),'occurrences':sum(counts[k] for k in names),'expansion_identical':True}

if __name__=='__main__':
    captured=json.loads((BASE/'baseline-v2/model-calls/call-013.json').read_text(encoding='utf-8'));original=schema(captured['tools']);new,receipt=compact(original)
    receipt.update(original_schema_chars=len(json.dumps(original,ensure_ascii=False)),compact_schema_chars=len(json.dumps(new,ensure_ascii=False)),no_observations_or_tools_removed=True)
    (BASE/'schema-sharing-experiment.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8');print(json.dumps(receipt))
