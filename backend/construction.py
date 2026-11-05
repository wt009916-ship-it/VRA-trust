"""Source-bound CPM and explicit remaining-duration scenarios, not site safety approval."""
import heapq
import html
import json
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Literal

from pydantic import Field, StrictFloat, field_validator, model_validator
from . import core
from .domain import identifier
from .schema import Contract


def decimal(value):
    return Decimal(str(value))


def day_precision(value):
    if value is not None and decimal(value) != decimal(value).quantize(Decimal('.000001')):
        raise ValueError('Numeric values support at most six decimal places')
    return value


def number(value):
    if value is None:
        return None
    text=format(value, 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


class Dependency(Contract):
    task_id: str = Field(min_length=1, max_length=60)
    lag_days: StrictFloat = Field(ge=0, le=3650)
    source: str = Field(min_length=5, max_length=1000)
    _precision=field_validator('lag_days')(day_precision)


class Demand(Contract):
    resource_id: str = Field(min_length=1, max_length=60)
    units: StrictFloat = Field(ge=.000001, le=1000000)
    _precision=field_validator('units')(day_precision)


class Resource(Contract):
    resource_id: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=160)
    capacity: StrictFloat | None = Field(default=None, ge=0, le=1000000)
    unit: str = Field(min_length=1, max_length=40)
    source: str = Field(min_length=5, max_length=1000)
    _precision=field_validator('capacity')(day_precision)


class Task(Contract):
    task_id: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=160)
    duration_days: StrictFloat | None = Field(default=None, ge=0, le=3650)
    duration_source: str = Field(min_length=5, max_length=1000)
    predecessors: list[Dependency] = Field(max_length=50)
    demands: list[Demand] = Field(default_factory=list, max_length=10)
    _precision=field_validator('duration_days')(day_precision)


class Observation(Contract):
    task_id: str = Field(min_length=1, max_length=60)
    state: Literal['not_started', 'in_progress', 'completed']
    actual_start_day: StrictFloat | None = Field(default=None, ge=0, le=2000000)
    actual_finish_day: StrictFloat | None = Field(default=None, ge=0, le=2000000)
    remaining_days: StrictFloat | None = Field(default=None, gt=0, le=3650)
    source: str = Field(min_length=5, max_length=1000)
    _precision=field_validator('actual_start_day','actual_finish_day','remaining_days')(day_precision)

    @model_validator(mode='after')
    def coherent(self):
        if self.state=='not_started' and any(v is not None for v in (self.actual_start_day,self.actual_finish_day,self.remaining_days)):
            raise ValueError('Not-started tasks cannot declare actual dates or remaining work')
        if self.state=='in_progress' and (self.actual_start_day is None or self.actual_finish_day is not None):
            raise ValueError('In-progress tasks need actual start and no actual finish')
        if self.state=='completed' and (self.actual_start_day is None or self.actual_finish_day is None or self.remaining_days is not None):
            raise ValueError('Completed tasks need actual start/finish, not remaining work')
        if self.actual_finish_day is not None and self.actual_finish_day < self.actual_start_day:
            raise ValueError('Actual finish precedes start')
        return self


class Progress(Contract):
    as_of_day: StrictFloat = Field(ge=0, le=2000000)
    source: str = Field(min_length=5, max_length=1000)
    observations: list[Observation] = Field(max_length=250)
    _precision=field_validator('as_of_day')(day_precision)


def ordered(tasks):
    by_id={t.task_id:t for t in tasks}
    counts={t.task_id:len(t.predecessors) for t in tasks}
    successors={key:[] for key in by_id}
    for t in tasks:
        for dep in t.predecessors:
            if dep.task_id not in by_id:
                raise ValueError('Unknown predecessor: '+dep.task_id)
            successors[dep.task_id].append((t.task_id,decimal(dep.lag_days)))
    ready=[key for key in counts if counts[key]==0];heapq.heapify(ready);order=[]
    while ready:
        key=heapq.heappop(ready);order.append(key)
        for nxt,_ in successors[key]:
            counts[nxt]-=1
            if counts[nxt]==0:heapq.heappush(ready,nxt)
    if len(order)!=len(tasks):
        raise ValueError('Dependency cycle; blocked tasks: '+', '.join(sorted(k for k,v in counts.items() if v)))
    return by_id,order,successors


class ScheduleInput(Contract):
    name: str = Field(min_length=1, max_length=160)
    scope: str = Field(min_length=10, max_length=2000)
    calendar: Literal['continuous_elapsed_days']
    time_origin: str = Field(min_length=5, max_length=500)
    tasks: list[Task] = Field(min_length=1, max_length=250)
    resources: list[Resource] = Field(default_factory=list, max_length=50)
    evidence_ids: list[str] = Field(default_factory=list, max_length=50)
    progress: Progress | None = None
    import_file_id: str | None = Field(default=None, pattern=r'^file_[a-f0-9]{32}$')

    @model_validator(mode='after')
    def coherent(self):
        for ids in ([t.task_id for t in self.tasks],[r.resource_id for r in self.resources],self.evidence_ids):
            if len(ids)!=len(set(ids)):raise ValueError('Duplicate task, resource or evidence ID')
        resources={r.resource_id for r in self.resources}
        for t in self.tasks:
            deps=[d.task_id for d in t.predecessors];demands=[d.resource_id for d in t.demands]
            if len(deps)!=len(set(deps)) or t.task_id in deps:raise ValueError('Duplicate/self predecessor')
            if len(demands)!=len(set(demands)) or not set(demands)<=resources:raise ValueError('Duplicate/unknown task resource')
        tasks,_,_=ordered(self.tasks)
        if self.progress:
            obs={o.task_id:o for o in self.progress.observations}
            if len(obs)!=len(self.progress.observations) or not set(obs)<=set(tasks):raise ValueError('Duplicate/unknown progress task')
            for key,o in obs.items():
                if any(v is not None and v>self.progress.as_of_day for v in (o.actual_start_day,o.actual_finish_day)):
                    raise ValueError('Actual dates cannot follow the reporting day')
                if o.state!='not_started':
                    for dep in tasks[key].predecessors:
                        previous=obs.get(dep.task_id)
                        if previous and (previous.state!='completed' or decimal(o.actual_start_day)<decimal(previous.actual_finish_day)+decimal(dep.lag_days)):
                            raise ValueError('Actual sequence contradicts finish-to-start dependency: '+dep.task_id+' -> '+key)
        return self


def resources_at(body, intervals):
    """Half-open [start, finish) intervals: end then start at identical instants."""
    conflicts=[];unknown=[]
    for resource in body.resources:
        events={}
        for task in body.tasks:
            demand=next((d for d in task.demands if d.resource_id==resource.resource_id),None)
            if not demand:continue
            interval=intervals.get(task.task_id)
            if interval is None or resource.capacity is None:
                unknown.append({'resource_id':resource.resource_id,'task_id':task.task_id});continue
            start,finish=interval
            if start==finish:continue
            events.setdefault(start,[]).append((task.task_id,decimal(demand.units)))
            events.setdefault(finish,[]).append((task.task_id,None))
        active={};points=sorted(events)
        for i,point in enumerate(points):
            for key,units in sorted(events[point],key=lambda x:x[1] is not None):
                if units is None:active.pop(key,None)
                else:active[key]=units
            used=sum(active.values(),Decimal(0))
            if i+1<len(points) and used>decimal(resource.capacity):
                conflicts.append({'resource_id':resource.resource_id,'from_day':number(point),'until_day':number(points[i+1]),
                    'demand':number(used),'capacity':number(decimal(resource.capacity)),'unit':resource.unit,'tasks':sorted(active)})
    return {'status':'conflict' if conflicts else 'unknown' if unknown else 'checked_declared_resources' if body.resources else 'not_assessed',
        'conflicts':conflicts,'unknown':unknown,'note':'仅检查声明资源在当前时间区间的重叠；不自动调平，不证明现场可施工。'}


def calculate(body):
    with localcontext() as ctx:
        ctx.prec=40
        tasks,order,successors=ordered(body.tasks)
        missing=[key for key in order if tasks[key].duration_days is None]
        base={'calendar':body.calendar,'time_origin':body.time_origin,'scope':body.scope,'missing_duration_tasks':missing,
            'source_status':'USER_DECLARED','site_safety':'NOT_ASSESSED','resource_leveling':'NOT_IMPLEMENTED',
            'limitations':['连续经过日，从声明的第0天起算；不自动跳过周末、节假日、天气或夜间。',
                '只支持完成到开始FS及非负间隔；零工期表示里程碑。关键路径基于声明工期，不代表施工安全或履约保证。',
                '预测使用显式剩余工期；不按完成百分比推测，不自动补齐未报告工序。资源冲突未自动调平。']}
        if missing:return {**base,'status':'incomplete','planned':None,'forecast':None}
        early={};late={}
        for key in order:
            task=tasks[key]
            start=max((early[d.task_id][1]+decimal(d.lag_days) for d in task.predecessors),default=Decimal(0))
            early[key]=(start,start+decimal(task.duration_days))
        duration=max(x[1] for x in early.values())
        for key in reversed(order):
            finish=min((late[nxt][0]-lag for nxt,lag in successors[key]),default=duration)
            late[key]=(finish-decimal(tasks[key].duration_days),finish)
        rows=[]
        for key in order:
            start,finish=early[key];latest,latest_finish=late[key]
            free=min((early[nxt][0]-lag for nxt,lag in successors[key]),default=duration)-finish
            rows.append({'task_id':key,'name':tasks[key].name,'start_day':number(start),'finish_day':number(finish),
                'latest_start_day':number(latest),'latest_finish_day':number(latest_finish),'total_float_days':number(latest-start),
                'free_float_days':number(free),'critical':latest==start})
        critical={r['task_id'] for r in rows if r['critical']}
        edges=[{'from':key,'to':nxt,'lag_days':number(lag)} for key in order for nxt,lag in successors[key]
            if key in critical and nxt in critical and early[key][1]+lag==early[nxt][0]]
        planned={'duration_days':number(duration),'rows':rows,'critical_tasks':sorted(critical),'critical_dependencies':edges,
            'resources':resources_at(body,early),'formulas':['ES=max(EF predecessor + FS lag), EF=ES+duration','LF=min(LS successor - lag), LS=LF-duration','total_float=LS-ES; free_float=min(ES successor - lag)-EF']}
        forecast=None
        if body.progress:
            progress=body.progress;obs={o.task_id:o for o in progress.observations};intervals={};unknown=[];unverified=[]
            for key in order:
                o=obs.get(key);task=tasks[key]
                if o is None:
                    intervals[key]=None;unknown.append({'task_id':key,'reason':'not_reported'});continue
                if o.state=='completed':intervals[key]=(decimal(o.actual_start_day),decimal(o.actual_finish_day))
                elif o.state=='in_progress':
                    intervals[key]=None if o.remaining_days is None else (decimal(o.actual_start_day),decimal(progress.as_of_day)+decimal(o.remaining_days))
                    if o.remaining_days is None:unknown.append({'task_id':key,'reason':'remaining_duration_missing'})
                else:
                    if any(intervals[d.task_id] is None for d in task.predecessors):
                        intervals[key]=None;unknown.append({'task_id':key,'reason':'predecessor_forecast_missing'})
                    else:
                        start=max([decimal(progress.as_of_day)]+[intervals[d.task_id][1]+decimal(d.lag_days) for d in task.predecessors])
                        intervals[key]=(start,start+decimal(task.duration_days))
                if o.state!='not_started':
                    unverified.extend({'task_id':key,'predecessor':d.task_id} for d in task.predecessors if d.task_id not in obs)
            finish=None if unknown or unverified else max(pair[1] for pair in intervals.values())
            forecast={'status':'incomplete' if finish is None else 'scenario','as_of_day':number(decimal(progress.as_of_day)),
                'finish_day':number(finish),'finish_variance_days':number(None if finish is None else finish-duration),
                'missing':unknown,'unverified_actual_dependencies':unverified,
                'rows':[{'task_id':key,'state':obs[key].state if key in obs else 'not_reported',
                    'start_day':number(intervals[key][0]) if intervals[key] else None,
                    'finish_day':number(intervals[key][1]) if intervals[key] else None} for key in order],
                'resources':resources_at(body,intervals)}
        unresolved=planned['resources']['status'] in {'conflict','unknown'} or (forecast and forecast['resources']['status'] in {'conflict','unknown'})
        status='constraints_unresolved' if unresolved else 'incomplete_progress' if forecast and forecast['status']=='incomplete' else 'calculated'
        return {**base,'status':status,'planned':planned,'forecast':forecast}


class Schedules:
    def __init__(self,domain):self.domain,self.store=domain,domain.store

    def save(self,pid,body):
        project=self.store.get('project',pid);sources=[];imported=None
        for eid in body.evidence_ids:
            ev=self.store.get('evidence',eid)
            if ev['project_id']!=pid or ev['review_state']=='rejected':raise core.ValidationError('Foreign or rejected schedule evidence')
            if ev['source_file']:self.domain.file_record(pid,ev['source_file'])
            sources.append(ev)
        if body.import_file_id:imported,_=self.domain.file_record(pid,body.import_file_id)
        obj={'schedule_id':identifier('schedule'),'project_id':pid,'project_revision':project['revision'],
            'input':body.model_dump(),'result':calculate(body),'source_snapshot':sources,'import_source':imported,
            'calculator_hash':core.sha(Path(__file__)),'created_at':core.now()}
        obj['hash']=core.hash_json(obj);self.store.put('schedule',obj)
        return self.view(pid,obj['schedule_id'])

    def view(self,pid,sid):
        obj=self.store.get('schedule',sid)
        if obj['project_id']!=pid:raise core.ValidationError('Cross-project schedule rejected')
        if core.hash_json({k:v for k,v in obj.items() if k not in {'hash','revision'}})!=obj['hash']:
            raise core.ValidationError('Schedule integrity check failed')
        stale=obj['project_revision']!=self.store.get('project',pid)['revision'] or obj['calculator_hash']!=core.sha(Path(__file__))
        files=[obj['import_source']['file_id']] if obj['import_source'] else []
        for old in obj['source_snapshot']:
            current=self.store.get('evidence',old['evidence_id'])
            stale |= current['review_state']=='rejected' or current['revision']!=old['revision'] or current['hash']!=old['hash']
            if current['source_file']:files.append(current['source_file'])
        for fid in files:
            try:self.domain.file_record(pid,fid)
            except (ValueError,KeyError,OSError):stale=True
        return {**obj,'status':'stale' if stale else obj['result']['status'],'result':None if stale else obj['result']}


def report(record):
    esc=lambda x:html.escape(str(x));planned=(record.get('result') or {}).get('planned')
    summary='<p>当前计划结果不可用，请复核来源及缺参。</p>'
    if planned:
        summary='<h2>不含资源调平的计划工期：'+esc(planned['duration_days'])+' 连续经过日</h2><table><tr><th>工序</th><th>开始日</th><th>完成日</th><th>总时差（日）</th><th>关键工序</th></tr>'
        summary+=''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in (r['task_id']+' '+r['name'],r['start_day'],r['finish_day'],r['total_float_days'],'是' if r['critical'] else '否'))+'</tr>' for r in planned['rows'])+'</table>'
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>施工进度计算记录</title><style>body{font:16px/1.7 system-ui;max-width:1100px;margin:30px auto;padding:20px}td,th{padding:8px;border:1px solid #ccc}table{border-collapse:collapse}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>'+esc(record['input']['name'])+'</h1><p>来源为用户声明；不是施工安全审查或工期履约保证。状态：'+esc(record['status'])+'</p>'+summary+'<h2>计划、进度情景、资源冲突及完整来源</h2><pre>'+esc(json.dumps(record,ensure_ascii=False,indent=2))+'</pre></html>'
