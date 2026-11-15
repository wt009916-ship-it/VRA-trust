from pathlib import Path
root=Path.cwd()
p=root/'validation/agent-open-completion-20261114/live_acceptance.py'
s=p.read_text(encoding='utf-8')
a=s.index("   open_task('M01'");b=s.index("   frozen_tasks=",a)
s=s[:a]+"""   open_task('N01','分别查两份记录：'+records['cancellation']['utility_id']+'只交付均方根百分比CV(RMSE)；墙体'+wall_record['thermal_id']+'只交付包含表面热阻的总R。不要U或平均偏差。',{'record_facts':{'cancellation':['cvrmse_percent'],'wall':['total_resistance_m2k_w']},'group':'open'})
   open_task('N02','比较资料'+records['bias']['utility_id']+'取平均偏差MBE百分数，另一份'+records['cancellation']['utility_id']+'取RMSE的kWh值。各自保留编号和单位，不要互换指标。',{'record_facts':{'bias':['mbe_percent'],'cancellation':['rmse_kwh']},'group':'open'})
   open_task('N03','记录'+records['zero']['utility_id']+'请读取CV(RMSE)，无定义时列空值和原因；另外墙体'+wall_record['thermal_id']+'给出U。只需要这两项。',{'record_facts':{'zero':['cvrmse_percent'],'wall':['u_w_m2k']},'null_reason':True,'group':'open'})
   open_task('N04','以下是排除要求：不要读取或报告'+records['bias']['utility_id']+'。本次仅从'+records['matched']['utility_id']+'取实际比较覆盖小时数，不要完整年度小时数、能量或误差。',{'record_facts':{'matched':['compared_hours']},'forbidden_read_record':records['bias']['utility_id'],'group':'negative_scope'})
""" +s[b:]
s=s.replace("'minimum_complete':7,'total':8,'groups':{'open':2,'scoped':3,'uncertainty':1,'known_relationship_gap':1,'recovery':1}","'minimum_complete':4,'total':4,'groups':{'open':3,'negative_scope':1}")
s=s.replace("At least 7/7 metric tasks plus separately report the relationship control. This screen cannot establish full Agent competence or 95 points.","Require exact requested fields per source, preserve null reasons and exclusions; all four tasks required. Broader original assessment remains separate.")
s=s.replace("Eight new questions: catalog-constrained metric reads and independent unresolved relationship control. No claim that the full metric/relationship work batch is complete.","Four new frozen open tasks on metric combinations, null handling and excluded records.")
(root/'validation/agent-open-completion-20261114/holdout.py').write_text(s,encoding='utf-8')
print('Prepared four fresh questions and gates before inference.')
