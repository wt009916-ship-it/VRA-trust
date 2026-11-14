"""Typed read failures and selected-target progress, never an inferred full task plan."""
from . import core
from .agent_semantics import inspection


class RecordsUnavailable(core.ValidationError):
    def __init__(self, unavailable, present=()):
        super().__init__('Selected professional records unavailable in this project; no result reads executed')
        self.unavailable=list(unavailable)
        self.present=list(present)


def advice(error, approved_ids, offered):
    if not isinstance(error,RecordsUnavailable):return None
    calls=[];can_missing='professional_missing' in offered
    for ident in error.unavailable:
        kind=ident.split('_',1)[0]
        if can_missing and ident in approved_ids:
            calls.append({'tool':'professional_missing','arguments':{'missing':{'kinds':[kind],'record_id':ident,'finish':False}}})
    if error.present:
        if 'professional_read_many' in offered:
            calls.append({'tool':'professional_read_many','arguments':{'record_ids':error.present}})
        else:
            for ident in error.present:
                spec=inspection(ident.split('_',1)[0])
                if spec.read_tool in offered:calls.append({'tool':spec.read_tool,'arguments':{spec.argument:ident}})
    lookup='professional_missing' if calls and calls[0]['tool']=='professional_missing' else None
    unapproved=[i for i in error.unavailable if not can_missing or i not in approved_ids]
    if unapproved:
        kinds=list(dict.fromkeys(i.split('_',1)[0] for i in unapproved))
        if 'professional_inventory' in offered:
            lookup=lookup or 'professional_inventory';calls.append({'tool':'professional_inventory','arguments':{'kinds':kinds}})
        elif len(kinds)==1 and inspection(kinds[0]).list_tool in offered:
            list_tool=inspection(kinds[0]).list_tool
            lookup=lookup or list_tool;calls.append({'tool':list_tool,'arguments':{}})
    return {'error_code':'professional_record_unavailable','scope':'current_project',
            'unavailable_record_ids':error.unavailable,'present_record_ids':error.present,'result_reads_executed':0,
            'selected_record_ids':[i for i in error.unavailable+error.present if can_missing and i in approved_ids],
            'lookup_tool':lookup,'suggested_calls':calls,'same_call_retry_recommended':False,
            'guidance':'整批预检未执行结果读取。present仅表示记录存在，须另读当前结果；unavailable须按指定编号核验缺失。逐项处理，不原样重复失败批次；不补零、不新建计算。建议调用尚未执行，不代表任务已完成。'}


def unresolved(record):
    selected={i for e in record['events'] for i in e.get('recovery',{}).get('selected_record_ids',[])}
    delivered={r['record_id'] for r in record.get('professional_deliveries',[])}
    delivered.update(r['request'].get('record_id') for r in record.get('missing_deliveries',[]))
    return sorted(selected-delivered)


def attach(answer, record):
    pending=unresolved(record)
    if not pending:return answer
    return {**answer,'unresolved_selected_reads':pending,
            'gaps':[*answer.get('gaps',[]),{'message':'已选读取目标尚未交付：'+', '.join(pending),
                'action':'逐项读取当前结果或按原编号核验缺失；此清单仅覆盖已选工具目标，不证明原问题已完整拆解。'}]}
