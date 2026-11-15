from pathlib import Path

BASE = Path(__file__).parent
source = (BASE.parent/'agent-integrated-20261115/live-final-exit-v1.py').read_text(encoding='utf-8')
source = source.replace("'final-exit-v1'", "'history-live-v1'").replace("'private-final-exit-v1'", "'private-history-live-v1'")
needle = "            save(out/'records.json'"
start = source.index(needle)
source = source[:start]+'''            request('PUT',base+'/building',{'expected_revision':p['revision'],'building':{**p['building'],'area_m2':31.}})
            records['current']=request('POST',base+'/thermal',wall(.027,'Current construction after revision'))
'''+source[start:]
start = source.index('            tasks=[]')
end = source.index("            save(out/'frozen.json'", start)
source = source[:start]+'''            tasks=[]
            def add(key,message,expected,previous=None):tasks.append({'id':key,'message':message,'expected':expected,'previous_case':previous,'action':None,'body':{'message':message,'mode':'local_model','allow_compute':False}})
            add('M01',f'分别核查两份构造：旧构造只说明当前状态，新构造给总R，不要U。旧构造：{ids["A"]}；新构造：{ids["current"]}。',{'stale':'A','facts':{'current':['total_resistance_m2k_w']}})
            add('M02','先给刚才有效构造的总R，再按相同参数创建第二份计算。',{'facts':{'current':['total_resistance_m2k_w']},'current_authorization_gap':True,'no_writes':True},previous='M01')
            oracle={'current_R':'49/20','current_U':'20/49','scope':'Two multi-turn history regressions on changed synthetic parameters. Existing known intent families, not new blind questions. Experimental planner is not used.'}
'''+source[end:]
source = source.replace('Frozen final exit tasks; no physics benchmark rerun', 'Frozen two history regressions; existing application tool chain, planner inactive')
source = source.replace('Targeted finish regression only; do not combine into a new16/16 or score. Preserve all original failures.',
                        'History source resolution and explicit current authorization gap only; no score or full-suite claim.')
(BASE/'history_live.py').write_text(source, encoding='utf-8')
print('Prepared actual application two-turn history regression, no experimental task planner.')
