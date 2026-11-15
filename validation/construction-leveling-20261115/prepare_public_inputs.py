"""Parse only fixed official single-mode renewable-resource references, no scheduler."""
import hashlib,json,re
from pathlib import Path
root=Path(__file__).parent/'public-reference'
frozen=json.loads((root/'frozen-public-reference.json').read_text(encoding='utf-8'))
summary=[]
for case in frozen['cases']:
 raw=(root/case['file']).read_bytes();assert hashlib.sha256(raw).hexdigest()==case['sha256']
 text=raw.decode('ascii');lines=text.splitlines()
 job_count=int(re.search(r'jobs \(incl\. supersource/sink \)\s*:\s*(\d+)',text)[1])
 renewable=int(re.search(r'- renewable\s*:\s*(\d+)',text)[1])
 assert re.search(r'- nonrenewable\s*:\s*0',text) and re.search(r'- doubly constrained\s*:\s*0',text)
 sections={name:next(i for i,l in enumerate(lines) if l.startswith(name)) for name in ['PRECEDENCE RELATIONS:','REQUESTS/DURATIONS:','RESOURCEAVAILABILITIES:']}
 successors={}
 for line in lines[sections['PRECEDENCE RELATIONS:']+1:sections['REQUESTS/DURATIONS:']]:
  if not re.fullmatch(r'\s*\d+(?:\s+\d+)+\s*',line):continue
  fields=list(map(int,line.split()));job,modes,count=fields[:3];assert modes==1 and len(fields)==3+count
  successors[job]=fields[3:]
 jobs={}
 for line in lines[sections['REQUESTS/DURATIONS:']+1:sections['RESOURCEAVAILABILITIES:']]:
  if not re.fullmatch(r'\s*\d+(?:\s+\d+)+\s*',line):continue
  fields=list(map(int,line.split()));job,mode,duration=fields[:3];assert mode==1 and len(fields)==3+renewable
  jobs[job]={'duration':duration,'demands':fields[3:]}
 capacity=next(list(map(int,l.split())) for l in lines[sections['RESOURCEAVAILABILITIES:']+1:] if re.fullmatch(r'\s*\d+(?:\s+\d+)*\s*',l))
 assert set(jobs)==set(successors)==set(range(1,job_count+1)) and len(capacity)==renewable
 assert all(j in jobs for rows in successors.values() for j in rows)
 assert all(len(set(v))==len(v) for v in successors.values())
 for job,row in jobs.items():assert all(0<=v<=capacity[i] for i,v in enumerate(row['demands']))
 source='PSPLIB official synthetic benchmark '+case['file']+' SHA256 '+case['sha256']
 body={'name':case['file'],'scope':'Synthetic RCPSP evaluation, not a real construction project','calendar':'continuous_elapsed_days',
       'time_origin':'Benchmark time zero, treating one benchmark time unit as one declared elapsed day for testing only',
       'resources':[{'resource_id':'R'+str(i+1),'name':'Declared benchmark resource '+str(i+1),'capacity':float(c),'unit':'benchmark unit','source':source} for i,c in enumerate(capacity)],
       'tasks':[{'task_id':str(job),'name':'Benchmark job '+str(job),'duration_days':float(row['duration']),'duration_source':source,
                 'predecessors':[{'task_id':str(parent),'lag_days':0.,'source':source} for parent,children in successors.items() if job in children],
                 'demands':[{'resource_id':'R'+str(i+1),'units':float(value)} for i,value in enumerate(row['demands']) if value]} for job,row in sorted(jobs.items())]}
 destination=root/(case['file']+'.schedule.json');assert not destination.exists()
 destination.write_text(json.dumps(body,indent=2)+'\n',encoding='utf-8')
 summary.append({'source':case['file'],'jobs_including_dummies':job_count,'resources':renewable,'parsed_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'fixed_priority':[str(j) for j in sorted(jobs)]})
(root/'input-preparation.json').write_text(json.dumps({'status':'source conversion only; no application solver run','cases':summary},indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary))
