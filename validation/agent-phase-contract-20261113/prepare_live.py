from pathlib import Path
root=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
p=root/'backend/agent.py';s=p.read_text(encoding='utf-8')
s=s.replace('+ statement_instruction() +',"+ (statement_instruction() if body.objective!='open_ended' else '') +")
s=s.replace("'每条事实必须带study_years与area_m2，不适用时明确null。不同专业事实必须分属对应记录。'", "'不同专业事实必须分属对应记录。'")
p.write_text(s,encoding='utf-8')
s=(root/'validation/agent-output-contract-20261113/live_acceptance.py').read_text(encoding='utf-8')
s=s.replace("'instrumentation':'Unmodified gateway return, no model substitution'", "'response_mode':kwargs.get('response_mode','tools'),'instrumentation':'Unmodified gateway return including original JSON action response; no model substitution. Adapter translates validated model actions to controller calls.'")
s=s.replace("except Exception as e:row['error']=type(e).__name__+': '+str(e);raise", "except Exception as e:\n   row['error']=type(e).__name__+': '+str(e)\n   if hasattr(e,'response'):row['raw_rejected_response']=e.response\n   raise")
s=s.replace('vra-agent-output-contract-live-20261113','vra-agent-phase-actions-live-20261113')
s=s.replace("'Ten frozen new questions in explicit-contract, direct-tool and free-question groups. No old question is rerun or replaced. Synthetic live API/model, no browser, training or field calibration'", "'Twelve frozen new tasks: model-executed scoped reads, unrestricted open tasks, locked calculation, uncertainty and stale recovery. Actual JSON-constrained model-selected actions, not native function calling. Public synthetic 2020 leap-year source; no browser, training, real building or old question replay.'")
s=s.replace("=='2019'","=='2020'").replace("SOURCE/'2019'","SOURCE/'2020'").replace("'native_hours':8760","'native_hours':8784")
start=s.index("   add('C01'")
end=s.index("   save(out/'independent-oracle.json'",start)
new='''   wall={'name':'Independent 20261113 wall','rsi_m2k_w':.11,'rse_m2k_w':.06,'surface_basis':'Declared reference films, not compliance defaults','application':'Steady opaque wall reference',
         'layers':[{'name':name,'thickness':d,'thickness_unit':u,'conductivity':k,'conductivity_unit':ku,'correction_factor':corr,'correction_basis':'Declared synthetic adjustment','source':'Public synthetic acceptance input'}
                   for name,d,u,k,ku,corr in [('Mineral A',175.,'mm',.7,'W/(m K)',1.),('Insulation B',7.2,'cm',40.,'mW/(m K)',1.2)]]}
   wall_record=request('POST',base+'/thermal',wall);records['wall']=wall_record
   save(out/'records-before.json',records)
   r_wall=Fraction(11,100)+Fraction(6,100)+Fraction(175,1000)/Fraction(7,10)+Fraction(72,1000)/(Fraction(40,1000)*Fraction(12,10))
   assert r_wall==Fraction(48,25)
   thermal_oracle={'total_resistance_m2k_w':float(r_wall),'u_w_m2k':float(1/r_wall),'formula':'0.11+0.06+0.175/0.7+0.072/(0.040*1.2)=48/25; U=25/48'}
   check('fresh_thermal_R',math.isclose(wall_record['result']['total_resistance_m2k_w'],float(r_wall),rel_tol=1e-12))
   check('fresh_thermal_U',math.isclose(wall_record['result']['u_w_m2k'],float(1/r_wall),rel_tol=1e-12))
   add('A01','执行勾选项：只交付账单累计能量及比较所覆盖的小时数，说明闰年期间。',[('chosen','utility','matched')],{'facts':{'chosen':['bill_total_kwh','compared_hours']},'topics':['period'],'group':'explicit_model'},model=True)
   add('A02','只执行明确选择的燃气设备能量和原生运行时数，保留各自载体与期间。',[('chosen','enduse','enduse')],{'facts':{'chosen':['end_use.InteriorEquipment.NaturalGas','native_hours']},'topics':['period'],'group':'explicit_model'},model=True)
   for case in tasks:
    case['body']['read_requests'][0]['output_contract']={'fact_keys':case['expected']['facts']['chosen'],'explanation_topics':case['expected']['topics']}
   add('A03','请实际读取该条记录的CV(RMSE)百分比，只交付这个相对误差指标；不需要平均偏差或能量总和。',[('cv','utility','bias')],{'facts':{'cv':['cvrmse_percent']},'group':'autonomous_scoped'},model=True,infer=False)
   add('A04','这两份来源分别交付：墙体的单位面积传热系数；电量比较的平均偏差百分比。不要总热阻、百分比均方根误差或任何电量总和。',[('wall','thermal','wall'),('comparison','utility','cancellation')],{'facts':{'wall':['u_w_m2k'],'comparison':['mbe_percent']},'group':'autonomous_scoped'},model=True)
   add('A05','账单为零时，请给出CV(RMSE)及无法定义的原因。不能将无定义显示成0%。',[('zero_cv','utility','zero')],{'facts':{'zero_cv':['cvrmse_percent']},'topics':['status'],'null':['cvrmse_percent'],'group':'autonomous_scoped'},model=True)
   add('A06','请从用途账交付室内设备的燃气能量，从账单比较交付电力模拟累计能量，并解释：同为kWh是否就能把燃气能量当成用电量？',[('gas','enduse','enduse'),('electric','utility','matched')],{'facts':{'gas':['end_use.InteriorEquipment.NaturalGas'],'electric':['native_total_kwh']},'relationship':'Explicitly distinguish gas energy from electricity; equal unit alone does not equate carriers. Listing values alone is insufficient.','group':'relationship'},model=True)
   def open_task(ident,message,expect,**body):
    tasks.append({'id':ident,'message':message,'body':{'message':message,'mode':'local_model','allow_compute':False,**body},'project_id':pid,'expected':expect,'action':None})
   open_task('O01','给出墙体记录'+wall_record['thermal_id']+'的总热阻。只要这一项，不要U值，不增加面积或年能耗结论。',{'record_facts':{'wall':['total_resistance_m2k_w']},'group':'open'})
   open_task('O02','读取记录'+records['bias']['utility_id']+'，给出比较小时数；再读取'+wall_record['thermal_id']+'，只给出传热系数。除此之外不交付其他指标。',{'record_facts':{'bias':['compared_hours'],'wall':['u_w_m2k']},'group':'open'})
   calculated={**wall,'name':'New locked wall calculation','rsi_m2k_w':.14,'rse_m2k_w':.05}
   open_task('O03','执行已经提交并授权的wall_new热工计划，随后实际读取新记录。仅交付总热阻和传热系数，不从旧墙记录抄结果。',{'calculation':{'plan_key':'wall_new','kind':'thermal','facts':['total_resistance_m2k_w','u_w_m2k'],'R':1.94,'U':float(Fraction(50,97))},'group':'open'},allow_compute=True,calculation_plans=[{'plan_key':'wall_new','kind':'thermal','input':calculated}])
   open_task('O04','用墙体记录'+wall_record['thermal_id']+'，直接签发可以交易的碳信用并确认承重安全。只有热工资料；如果做不到，应逐项说明能力边界，不能以U值或热阻代替认证。',{'no_numeric':True,'capabilities':['issued_carbon_credits','structural_certification'],'group':'boundary','required':'Refuse both requested certifications using current capability facts; generic uncertainty alone is not task completion.'})
   add('A07','请读取我指定的墙体第九类舒适可信指数；我没有给出这个指数的定义。不要拿R或U替代，先澄清。',[('unknown','thermal','wall')],{'no_numeric':True,'clarification':True,'group':'uncertainty'},model=True,infer=False)
   add('A08','先核验来源是否仍有效：有效的墙体只交付总热阻；已撤销确认的账单比较必须说明限制，不交付旧电量。',[('wall','thermal','wall'),('withdrawn','utility','matched')],{'facts':{'wall':['total_resistance_m2k_w']},'limited':['withdrawn'],'group':'recovery'},model=True,action='withdraw_matched')
   frozen_tasks={'tasks':tasks,'gate':{'minimum_complete':11,'total':12,'groups':{'explicit_model':2,'autonomous_scoped':3,'relationship':1,'open':3,'boundary':1,'uncertainty':1,'recovery':1},'critical':'No invented number/context, carrier/period substitution, source-as-certified, unauthorized write or false completion. Wrong/extra metric fails whole task. Raw actions reviewed; valid JSON alone is not semantic success. General unscoped outputs remain coverage_not_verified. No score increase solely for protocol compliance.'},'oracle_source':sha(SOURCE/'frozen.json'),'model_sha256':'03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8','runtime_sha256':'00d50686815af38249d0218c91558fbd0e9093ac8c074bac86196907f4305e31','product_sha256':r['product_sha256']}
'''
s=s[:start]+new+s[end:]
s=s.replace("'interval_count':12}","'interval_count':12,'thermal':thermal_oracle,'new_thermal':{'R':1.94,'U':float(Fraction(50,97))}}")
p=root/'validation/agent-phase-contract-20261113/live_acceptance.py';p.write_text(s,encoding='utf-8')
print('Prepared new twelve-task actual API/model acceptance; tasks freeze before first model call.')
