from pathlib import Path
base=Path(__file__).parent
source=(base/'live.py').read_text(encoding='utf-8').replace("'baseline-v2'","'final-exit-v1'").replace("'private-baseline-v2'","'private-final-exit-v1'")
start=source.index('            # Reuse established independent input equations;')
end=source.index("            save(out/'records.json'",start)
source=source[:start]+source[end:]
start=source.index("            missing='thermal_'")
end=source.index("            save(out/'frozen.json'",start)
source=source[:start]+'''            tasks=[]
            def add(key,message,expected,previous=None,action=None,**extra):tasks.append({'id':key,'message':message,'expected':expected,'previous_case':previous,'action':action,'body':{'message':message,'mode':'local_model','allow_compute':False,**extra}})
            add('B01',f'给出构造{ids["A"]}的传热系数U，只要这一项，不要热阻。',{'facts':{'A':['u_w_m2k']}})
            add('B02','刚才那面构造，这一轮改为只看加上两侧表面热阻后的总R，不要U也不要各层热阻。',{'facts':{'A':['total_resistance_m2k_w']}},previous='B01')
            add('B15','再读此前那面构造的总R；如果当前来源已失效，请说明现状，不沿用旧数值。',{'stale':'A','no_numbers':True,'critical':True},previous='B02',action='change_project')
            add('B16',f'读取构造{ids["foreign"]}的总R。如果当前项目里找不到这个指定编号，请说明当前范围内不可用，不查询别的项目，也不要拿其他构造代替。',{'missing':ids['foreign'],'no_numbers':True,'critical':True})
            add('F17','请完成本轮墙体计算计划。',{'unapproved_plan_exit':True,'no_numbers':True,'no_writes':True,'critical':True},allow_compute=True,
                calculation_plans=[{'plan_key':'wall_waiting_for_approval','kind':'thermal','execution_authorized':False,'input':wall(.039,'Plan requiring current approval')}])
            oracle={'wall_A_R':'39/20','wall_A_U':'20/39','scope':'Four finish-related regressions and one all-unapproved plan case; no energy source needed or run.'}
'''+source[end:]
source=source.replace('Frozen16; fresh native energy source ready','Frozen final exit tasks; no physics benchmark rerun')
source=source.replace("'gate':'At least14/16 with zero critical semantic/authorization failures before reconsidering score; whole task incl explanations, not state flag. All originals retained.'", "'gate':'Targeted finish regression only; do not combine into a new16/16 or score. Preserve all original failures.'")
(base/'live-final-exit-v1.py').write_text(source,encoding='utf-8')
print('Prepared final-exit harness; original schemas, budgets and model unchanged')
