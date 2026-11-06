"""Bounded CSV operational screening with explicit units, rules and sample coverage."""
import csv
import html
import io
import json
import math
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from typing import Literal

from pydantic import Field, StrictFloat, field_validator, model_validator
from .calculation_provenance import validity, persist, version as provenance_version
from . import core
from .domain import identifier
from .schema import Contract

UNITS={'degC':('temperature','degC',1,0),'degF':('temperature','degC',5/9,-160/9),'K':('temperature','degC',1,-273.15),
    'W':('power','W',1,0),'kW':('power','W',1000,0),'Pa':('pressure','Pa',1,0),'kPa':('pressure','Pa',1000,0),
    'ratio':('fraction','ratio',1,0),'percent':('fraction','ratio',.01,0),'rpm':('speed','rpm',1,0),'rev_s':('speed','rpm',60,0),
    'kg_s':('mass_flow','kg_s',1,0),'L_s':('volume_flow','m3_s',.001,0),'m3_s':('volume_flow','m3_s',1,0),'state':('state','state',1,0)}
Unit=Literal['degC','degF','K','W','kW','Pa','kPa','ratio','percent','rpm','rev_s','kg_s','L_s','m3_s','state']
FORMATS={'iso8601':None,'yyyy-mm-dd hh:mm:ss':'%Y-%m-%d %H:%M:%S','mm/dd/yyyy hh:mm':'%m/%d/%Y %H:%M','yyyy-mm-dd hh:mm':'%Y-%m-%d %H:%M'}


class Channel(Contract):
    channel_id: str = Field(pattern=r'^[a-zA-Z][a-zA-Z0-9_]{0,39}$')
    column: str = Field(min_length=1,max_length=160)
    name: str = Field(min_length=1,max_length=160)
    unit: Unit
    source: str = Field(min_length=5,max_length=1000)


class Rule(Contract):
    rule_id: str = Field(min_length=1,max_length=60)
    name: str = Field(min_length=1,max_length=160)
    kind: Literal['range','difference','rate']
    channel_id: str
    other_channel_id: str | None = None
    unit: str = Field(min_length=1,max_length=30)
    lower: StrictFloat | None = Field(default=None,ge=-1e12,le=1e12)
    upper: StrictFloat | None = Field(default=None,ge=-1e12,le=1e12)
    threshold: StrictFloat | None = Field(default=None,ge=0,le=1e12)
    minimum_duration_seconds: StrictFloat = Field(ge=0,le=604800)
    gate_channel_id: str | None = None
    gate_minimum: StrictFloat | None = Field(default=None,ge=-1e12,le=1e12)
    gate_unit: str | None = None
    source: str = Field(min_length=5,max_length=1000)

    @model_validator(mode='after')
    def coherent(self):
        if self.kind=='range':
            if self.lower is None and self.upper is None:raise ValueError('Range needs at least one bound')
            if self.lower is not None and self.upper is not None and self.lower>=self.upper:raise ValueError('Range bounds reversed or equal')
            if self.threshold is not None or self.other_channel_id is not None:raise ValueError('Range has no threshold/other channel')
        else:
            if self.threshold is None or self.lower is not None or self.upper is not None:raise ValueError('Difference/rate requires a threshold, not range bounds')
            if (self.kind=='difference')!=(self.other_channel_id is not None):raise ValueError('Only difference requires a second channel')
            if self.other_channel_id==self.channel_id:raise ValueError('Difference needs distinct channels')
        if (self.gate_channel_id is None)!=(self.gate_minimum is None) or (self.gate_channel_id is None)!=(self.gate_unit is None):
            raise ValueError('Gate needs channel, minimum and explicit canonical unit')
        return self


class AnalysisInput(Contract):
    name: str = Field(min_length=1,max_length=160)
    file_id: str = Field(pattern=r'^file_[a-f0-9]{32}$')
    equipment: str = Field(min_length=1,max_length=160)
    data_nature: Literal['measured','simulation','synthetic']
    source: str = Field(min_length=5,max_length=2000)
    time_column: str = Field(min_length=1,max_length=160)
    time_format: Literal['iso8601','yyyy-mm-dd hh:mm:ss','mm/dd/yyyy hh:mm','yyyy-mm-dd hh:mm']
    clock_basis: Literal['offset_aware','declared_local_clock']
    clock_source: str = Field(min_length=5,max_length=1000)
    expected_interval_seconds: StrictFloat = Field(ge=.001,le=86400)
    maximum_gap_seconds: StrictFloat = Field(ge=.001,le=604800)
    channels: list[Channel] = Field(min_length=1,max_length=20)
    rules: list[Rule] = Field(min_length=1,max_length=30)
    evidence_ids: list[str] = Field(default_factory=list,max_length=30)

    @field_validator('expected_interval_seconds','maximum_gap_seconds')
    @classmethod
    def time_precision(cls,value):
        if round(value,3)!=value:raise ValueError('Time intervals support milliseconds')
        return value

    @model_validator(mode='after')
    def coherent(self):
        if self.maximum_gap_seconds<self.expected_interval_seconds:raise ValueError('Maximum gap below expected cadence')
        for ids in ([c.channel_id for c in self.channels],[c.column for c in self.channels],[r.rule_id for r in self.rules],self.evidence_ids):
            if len(ids)!=len(set(ids)):raise ValueError('Duplicate channel, column, rule or evidence')
        if self.time_column in {c.column for c in self.channels}:raise ValueError('Time column cannot be a numeric channel')
        channels={c.channel_id:c for c in self.channels}
        if self.clock_basis=='offset_aware' and self.time_format!='iso8601':raise ValueError('Offset-aware timestamps require ISO8601')
        for rule in self.rules:
            for key in (rule.channel_id,rule.other_channel_id,rule.gate_channel_id):
                if key is not None and key not in channels:raise ValueError('Unknown rule channel: '+key)
            dim,unit,_,_=UNITS[channels[rule.channel_id].unit]
            if rule.unit!=unit+('/min' if rule.kind=='rate' else ''):raise ValueError('Rule threshold unit must match normalized channel unit')
            if rule.other_channel_id and UNITS[channels[rule.other_channel_id].unit][0]!=dim:raise ValueError('Difference channel dimensions differ')
            if rule.gate_channel_id and rule.gate_unit!=UNITS[channels[rule.gate_channel_id].unit][1]:raise ValueError('Gate unit mismatch')
        return self


def timestamp(raw,body):
    try:
        if body.time_format=='iso8601' and not re.match(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}',raw):raise ValueError('Explicit date and time required')
        dt=datetime.fromisoformat(raw.replace('Z','+00:00')) if body.time_format=='iso8601' else datetime.strptime(raw,FORMATS[body.time_format])
        aware=dt.tzinfo is not None and dt.utcoffset() is not None
        if aware!=(body.clock_basis=='offset_aware'):raise ValueError('Clock basis/offset mismatch')
        return dt.astimezone(timezone.utc) if aware else dt
    except (ValueError,OverflowError) as exc:raise core.ValidationError('Timestamp does not match explicit format and clock basis') from exc


def parse_csv(path,body):
    if path.stat().st_size>8*1024*1024:raise core.ValidationError('Operations CSV exceeds 8 MiB')
    try:text=path.read_text(encoding='utf-8-sig')
    except UnicodeError as exc:raise core.ValidationError('Use UTF-8 CSV') from exc
    if '\0' in text:raise core.ValidationError('NUL in CSV')
    reader=csv.reader(io.StringIO(text),strict=True)
    try:
        header=next(reader)
        if not header or len(header)>64 or any(not h.strip() for h in header) or len(set(header))!=len(header):raise core.ValidationError('CSV needs unique nonempty headers, maximum 64')
        required=[body.time_column]+[c.column for c in body.channels]
        if not set(required)<=set(header):raise core.ValidationError('Mapped column absent from CSV')
        indices={key:header.index(key) for key in required};rows=[];issues=[];issue_count=0;gaps=[];gap_count=0;irregular=0;previous=None
        for raw in reader:
            line=reader.line_num
            if len(rows)>=50000:raise core.ValidationError('CSV exceeds 50000 samples')
            if len(raw)!=len(header):raise core.ValidationError('CSV column count mismatch at line '+str(line))
            try:dt=timestamp(raw[indices[body.time_column]].strip(),body)
            except core.ValidationError as exc:raise core.ValidationError(str(exc)+' at CSV line '+str(line)) from exc
            if previous is not None:
                step=(dt-previous).total_seconds()
                if step<=0:raise core.ValidationError('Duplicate or non-monotonic timestamp at line '+str(line))
                if abs(step-body.expected_interval_seconds)>1e-6:irregular+=1
                if step>body.maximum_gap_seconds:
                    gap_count+=1
                    if len(gaps)<100:gaps.append({'before_line':line,'seconds':step})
            values={}
            for channel in body.channels:
                value=None;reason=None;cell=raw[indices[channel.column]].strip()
                try:
                    if not cell:reason='missing'
                    else:
                        if len(cell)>128:raise ValueError('Numeric cell too long')
                        decimal=Decimal(cell)
                        if not decimal.is_finite() or len(decimal.as_tuple().digits)>40 or not -100<=decimal.as_tuple().exponent<=100:
                            raise ValueError('Numeric representation out of supported bounds')
                        value=Fraction(decimal);dim,_,scale,offset=UNITS[channel.unit]
                        value=(value-32)*Fraction(5,9) if channel.unit=='degF' else value*Fraction(str(scale))+Fraction(str(offset))
                        if abs(value)>10**12:reason='nonfinite_or_out_of_range'
                        elif dim=='temperature' and value < Fraction('-273.15'):reason='below_absolute_zero'
                        elif dim=='fraction' and not 0<=value<=1:reason='fraction_outside_zero_one'
                        elif dim=='state' and value.denominator!=1:reason='noninteger_state'
                except (ValueError,OverflowError,InvalidOperation):reason='not_numeric_or_unsupported_precision'
                if reason:
                    value=None;issue_count+=1
                    if len(issues)<100:issues.append({'line':line,'channel_id':channel.channel_id,'reason':reason})
                values[channel.channel_id]=value
            rows.append({'line':line,'timestamp':dt.isoformat(),'dt':dt,'values':values});previous=dt
        if len(rows)<2:raise core.ValidationError('At least two timestamped samples required')
        return rows,{'sample_count':len(rows),'cell_issue_count':issue_count,'cell_issues':issues,'cell_issues_truncated':issue_count>len(issues),
            'gap_count':gap_count,'gaps':gaps,'gaps_truncated':gap_count>len(gaps),'irregular_intervals':irregular,'first_time':rows[0]['timestamp'],'last_time':rows[-1]['timestamp']}
    except (csv.Error,StopIteration) as exc:raise core.ValidationError('Malformed or empty CSV') from exc


def evaluate_rule(rows,body,rule):
    evaluated=excluded=unknown=violating=event_count=0;events=[];run=[]
    def close():
        nonlocal event_count
        if run:
            span=(run[-1]['dt']-run[0]['dt']).total_seconds()
            if span>=rule.minimum_duration_seconds:
                event_count+=1
                if len(events)<200:events.append({'first_line':run[0]['line'],'last_line':run[-1]['line'],'start':run[0]['timestamp'],'end':run[-1]['timestamp'],'observed_span_seconds':span,'samples':len(run)})
            run.clear()
    for i,row in enumerate(rows):
        gap=i>0 and (row['dt']-rows[i-1]['dt']).total_seconds()>body.maximum_gap_seconds
        if gap:close()
        values=row['values'];gate=values.get(rule.gate_channel_id) if rule.gate_channel_id else None
        if rule.gate_channel_id and gate is None:unknown+=1;close();continue
        if rule.gate_channel_id and gate<Fraction(str(rule.gate_minimum)):excluded+=1;close();continue
        value=values[rule.channel_id]
        if rule.kind=='difference':
            other=values[rule.other_channel_id];value=None if value is None or other is None else abs(value-other)
        elif rule.kind=='rate':
            previous=rows[i-1]['values'][rule.channel_id] if i else None
            value=None if value is None or previous is None or gap else abs(value-previous)*60/Fraction(str((row['dt']-rows[i-1]['dt']).total_seconds()))
        if value is None:unknown+=1;close();continue
        evaluated+=1
        bad=(rule.lower is not None and value<Fraction(str(rule.lower))) or (rule.upper is not None and value>Fraction(str(rule.upper))) if rule.kind=='range' else value>Fraction(str(rule.threshold))
        if bad:violating+=1;run.append(row)
        else:close()
    close()
    return {'rule_id':rule.rule_id,'name':rule.name,'kind':rule.kind,'unit':rule.unit,'evaluated_samples':evaluated,
        'excluded_by_gate_samples':excluded,'unknown_samples':unknown,'violating_samples':violating,'event_count':event_count,'events':events,'events_truncated':event_count>len(events),
        'state':'events_detected' if event_count else 'insufficient_evidence' if unknown or evaluated==0 else 'no_rule_event',
        'recommended_checks':['复核对应行、采样时钟、单位和传感器校准；确认规则适用于当前工况。',
            {'range':'核查设定值和运行边界，比较独立测点；不能仅凭越限判断故障部件。','difference':'核查指令、反馈、接线及执行机构；在获授权的维护流程中验证，不自动下发控制命令。','rate':'核查突变是否来自启停、工况切换、时钟或传感器异常；与相邻测点交叉核对。'}[rule.kind]],
        'cause_confirmed':False}


def analyze(path,body):
    rows,quality=parse_csv(path,body);results=[evaluate_rule(rows,body,r) for r in body.rules];summary=[]
    for channel in body.channels:
        vals=[r['values'][channel.channel_id] for r in rows if r['values'][channel.channel_id] is not None]
        summary.append({'channel_id':channel.channel_id,'name':channel.name,'input_unit':channel.unit,'unit':UNITS[channel.unit][1],
            'valid_samples':len(vals),'missing_or_invalid':len(rows)-len(vals),'minimum':float(min(vals)) if vals else None,'maximum':float(max(vals)) if vals else None,
            'sample_mean':math.fsum(vals)/len(vals) if vals else None})
    selected=sorted({round(i*(len(rows)-1)/199) for i in range(min(200,len(rows)))}) if len(rows)>200 else range(len(rows))
    preview=[{'line':rows[i]['line'],'timestamp':rows[i]['timestamp'],'values':{k:float(v) if v is not None else None for k,v in rows[i]['values'].items()}} for i in selected]
    quality_problem=quality['cell_issue_count'] or quality['gap_count'] or any(r['unknown_samples'] or not r['evaluated_samples'] for r in results)
    return {'status':'events_detected' if any(r['event_count'] for r in results) else 'insufficient_evidence' if quality_problem else 'no_rule_event',
        'quality':quality,'channels':summary,'rules':results,'series_preview':preview,'preview_downsampled':len(rows)>len(preview),
        'source_status':'USER_DECLARED','data_nature':body.data_nature,'equipment':body.equipment,'diagnosis':'NOT_CONFIRMED','control_action':'NONE',
        'limitations':['仅检测声明规则，不把无告警当作设备健康；故障原因及维修措施需专业复核。',
            '持续时间是首末异常样本间跨度；缺测或超出最大间隔会断开事件，不外推最后一个样本后的持续时间。',
            '样本间连续性为明确采样假设，无法证明两次采样之间没有变化。均值是样本均值，不是时间加权均值或能耗积分。',
            '本地时钟不自动推断时区或夏令时；预览最多200个抽样点，完整数据以原件和事件行号为准。',
            '事件判断用原始十进制有理数计算；数值单元限128字符、40位有效数字和±100十进制指数。汇总与预览转为浮点显示。']}


class Operations:
    def __init__(self,domain):self.domain,self.store=domain,domain.store
    def preview(self,pid,fid):
        file,path=self.domain.file_record(pid,fid)
        if path.suffix.lower()!='.csv' or path.stat().st_size>8*1024*1024:raise core.ValidationError('Use CSV up to 8 MiB')
        try:
            reader=csv.reader(io.StringIO(path.read_text(encoding='utf-8-sig')),strict=True);header=next(reader)
            if not header or len(header)>64 or any(not x.strip() or '\0' in x for x in header) or len(set(header))!=len(header):raise core.ValidationError('Invalid CSV headers')
            sample=[]
            for _ in range(5):
                row=next(reader,None)
                if row is None:break
                if len(row)!=len(header):raise core.ValidationError('Preview row width mismatch')
                sample.append(row)
            return {'file_id':fid,'name':file['name'],'hash':file['hash'],'headers':header,'sample_rows':sample,'note':'仅预览前5行；完整时间、数值和规则检查在分析时执行。'}
        except (UnicodeError,csv.Error,StopIteration) as exc:raise core.ValidationError('Malformed UTF-8 CSV') from exc
    def save(self,pid,body, *, expected_bindings=None):
        project=self.store.get('project',pid);file,path=self.domain.file_record(pid,body.file_id);snapshots=[]
        if path.suffix.lower()!='.csv':raise core.ValidationError('Operations input must be CSV')
        for eid in body.evidence_ids:
            ev=self.store.get('evidence',eid)
            if ev['project_id']!=pid or ev['review_state']=='rejected':raise core.ValidationError('Foreign or rejected operations evidence')
            if ev['source_file']:self.domain.file_record(pid,ev['source_file'])
            snapshots.append(ev)
        obj={'operation_id':identifier('operation'),'project_id':pid,'project_revision':project['revision'],'input':body.model_dump(),
            'result':analyze(path,body),'file_snapshot':file,'source_snapshot':snapshots,'calculator_hash':provenance_version(Path(__file__)),'created_at':core.now()}
        obj['hash']=core.hash_json(obj);persist(self.domain, 'operation', obj, expected_bindings);return self.view(pid,obj['operation_id'])
    def view(self,pid,oid):
        obj=self.store.get('operation',oid)
        if obj['project_id']!=pid:raise core.ValidationError('Cross-project operations record rejected')
        if core.hash_json({k:v for k,v in obj.items() if k not in {'hash','revision'}})!=obj['hash']:raise core.ValidationError('Operations record integrity failed')
        provenance = validity(self.domain, obj, provenance_version(Path(__file__)))
        stale = provenance['stale_reasons']
        return {**obj, **provenance,'status':'stale' if stale else obj['result']['status'],'result':None if stale else obj['result']}


def report(record):
    esc=lambda x:html.escape(str(x));r=record.get('result')
    content='<p>当前来源已失效，不提供当前异常结论。</p>'
    if r:content='<p>样本数：'+esc(r['quality']['sample_count'])+'；事件数：'+esc(sum(x['event_count'] for x in r['rules']))+'</p>'+''.join('<h2>'+esc(x['name'])+'</h2><p>事件 '+esc(x['event_count'])+'；未知样本 '+esc(x['unknown_samples'])+'</p><ul>'+''.join('<li>'+esc(s)+'</li>' for s in x['recommended_checks'])+'</ul>' for x in r['rules'])
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>设备运行核查</title><style>body{font:16px/1.7 system-ui;max-width:1000px;margin:30px auto;padding:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>'+esc(record['input']['name'])+'</h1><p>规则筛查，不是设备健康证明或确定故障诊断。状态：'+esc(record['status'])+'</p>'+content+'<h2>规则、事件行号、数据质量及来源</h2><pre>'+esc(json.dumps(record,ensure_ascii=False,indent=2))+'</pre></html>'
