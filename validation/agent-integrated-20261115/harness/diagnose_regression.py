import json
import sys
from pathlib import Path

BASE=Path(__file__).parent
ROOT=Path('D:/稀土agent-稀土制暖全流程/.codex_work/vra-resource-leveling-20261115')
sys.path.insert(0,str(ROOT))
from backend import agent_actions

rows=[]
for path in (BASE/'regression-v1/model-calls').glob('*.json'):
    call=json.loads(path.read_text(encoding='utf-8'))
    if any('室内设备电能' in str(m.get('content','')) for m in call['messages']):
        schema=agent_actions.schema(call['tools'])
        row={'file':path.name,'response_keys':list((call.get('response') or {}).keys()),'error':call.get('error'),
             'message_chars':[len(json.dumps(m,ensure_ascii=False)) for m in call['messages']],
             'schema_chars':len(json.dumps(schema,ensure_ascii=False)),
             'tool_sizes':[{'name':t['function']['name'],'size':len(json.dumps(t,ensure_ascii=False))} for t in call['tools']]}
        rows.append(row)
(BASE/'regression-context-diagnosis.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(rows,ensure_ascii=False))
