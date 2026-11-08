"""Check explicit engineering metric constraints, not unrestricted language intent.

Only original user text is inspected. This never supplies numeric answers,
changes a model plan, expands scope, or marks intent_verified=True. Rules are
deliberately auditable; ambiguous negation/binding abstains instead of guessing.
"""
import re
import unicodedata
from . import core
from .agent_intent_catalog import fragments

# Quantity names are domain vocabulary, not known task IDs or benchmark text.
METRICS = {
 'thermal': {
  'total_resistance_m2k_w': r'总热阻|总\s*R',
  'layer_resistance_m2k_w': r'材料(?:层)?热阻|只含材料[^，,；;。]*R|d\s*/\s*[λλ]',
  'u_w_m2k': r'传热系数|(?<![A-Za-z])U(?![A-Za-z])'},
 'lifecycle': {
  'boundary_total_kgco2e': r'边界[^，,；;。]*(?:总碳|总量|总排放)|全部(?:已)?纳入阶段[^，,；;。]*(?:合计|总量)',
  'kgco2e_m2_over_study_period': r'单位(?:建筑)?面积[^，,；;。]*(?:排放|碳)|每平方米[^，,；;。]*(?:排放|碳)|kg\s*CO2e\s*/\s*m2',
  'stage.production': r'(?:材料|建材)生产|生产阶段',
  'stage.transport': r'材料运输|运输阶段',
  'stage.construction': r'施工(?:活动|阶段)',
  'stage.operation': r'运行(?:这一)?阶段|运行碳排放',
  'stage.end_of_life': r'寿命终结|拆除阶段'},
 'schedule': {
  'planned_duration_days': r'基准计划[^，,；;。]*工期|计划总工期',
  'forecast_as_of_day': r'(?:记录|进度)截至(?:第几天|日)',
  'forecast_finish_day': r'(?:预测|情景|预计)[^，,；;。]*(?:第几天[^，,；;。]*(?:完工|完成)|完工日|完工[^，,；;。]*哪一天)',
  'forecast_finish_variance_days': r'完工[^，,；;。]*(?:相差|偏差)|工期偏差'},
 'engineering': {
  'max_abs_moment_nm': r'最大(?:绝对)?弯矩',
  'max_abs_shear_n': r'最大(?:绝对)?剪力',
  'max_deflection_m': r'最大(?:向下)?挠度',
  'max_elastic_bending_stress_pa': r'最大(?:线弹性)?弯曲应力',
  'left_reaction_n': r'左(?:端|支座)[^，,；;。]*竖向[^，,；;。]*反力(?!矩)',
  'right_reaction_n': r'右(?:端|支座)[^，,；;。]*竖向[^，,；;。]*反力(?!矩)',
  'left_reaction_moment_nm': r'左(?:端|支座)[^，,；;。]*反力矩'},
 'operation': {
  'sample_count': r'(?:总)?样本行数',
  'cell_issue_count': r'(?:无效|缺失)[^，,；;。]*单元格(?:数|数量)',
  'gap_count': r'(?:时间|采样)缺口(?:数|数量)',
  'rule_event_sum': r'各规则[^，,；;。]*(?:触发|事件)次数之和',
  'rule_unknown_sample_sum': r'各规则[^，,；;。]*未知样本次数之和'},
 'cost': {'material_total': r'材料(?:采购)?(?:金额|报价|费用)(?:合计|总额)|材料清单[^，,；;。]*采购金额'},
}
NEGATIVE = re.compile(r'不要|无需|不用|不需要|不要求|(?<![分识个差特类性])别|不是|不把|不折算|不讨论|不另算|不列|不计入|不包含')
AMBIGUOUS = re.compile(r'不要只|不只是|不仅|不是不|不能不|并非不|除了|除非|是否|是不是|例如|比如|假如|如果')
NO_EXPLANATION = re.compile(r'(?:只|仅)(?:列|给|返回|报)[^，,；;。]*(?:数值|数字)|(?:无需|不用|不需要|不要|别)(?:额外的?|附加的?)?(?:文字)?(?:解释|说明|文字主题)')
TOPICS = {'area':r'面积解释|解释[^，,；;。]*面积|说明[^，,；;。]*面积',
          'period':r'(?:解释|说明)[^，,；;。]*(?:期间|评估期|时间范围)',
          'meaning':r'(?:解释|说明)[^，,；;。]*(?:含义|意义)',
          'scope':r'(?:解释|说明)[^，,；;。]*适用范围',
          'status':r'(?:解释|说明)[^，,；;。]*状态',
          'history':r'(?:解释|说明)[^，,；;。]*历史'}


def _bound_text(question,request,requests):
    same=[r for r in requests if r['kind']==request['kind'] and r['purpose']=='results']
    if len(same)<=1:return question,[]
    # Never combine two same-kind records' different demands. Exact original
    # sentence binding is required; shared/implicit binding remains unverified.
    selected=[]
    for f in fragments(question):
        mentioned=[r for r in same if r.get('record_id') and r['record_id'] in f['text']]
        if len(mentioned)==1 and mentioned[0]['request_key']==request['request_key']:selected.append(f['text'])
    return '\n'.join(selected),([] if selected else ['AMBIGUOUS_RECORD_BINDING'])


def analyze(question,request,requests):
    bound,uncertain=_bound_text(question,request,requests)
    text=unicodedata.normalize('NFKC',bound)
    required,forbidden,topics,excluded=set(),set(),set(),set()
    unsupported=[];evidence=[];no_explanation=False
    if request['purpose']!='results':
        return {'required_facts':[],'forbidden_facts':[],'required_topics':[], 'forbidden_topics':[],
                'unsupported':[],'uncertain':['AVAILABILITY_NOT_NUMERIC'],'matches':[],'intent_verified':False}
    for chunk in re.finditer(r'[^，,；;。！？!?\n]+',text):
        part=chunk.group()
        if AMBIGUOUS.search(part):
            uncertain.append('UNRESOLVED_LANGUAGE_SCOPE');continue
        def polarity(match):
            # Negation after a matched request can describe its subject, e.g.
            # explain why area is NOT an input. It must not negate 'explain'.
            if NEGATIVE.search(match.group()):
                uncertain.append('NEGATION_INSIDE_METRIC_PHRASE');return None
            return 'excluded' if NEGATIVE.search(part[:match.start()]) else 'requested'
        for fact,pattern in METRICS.get(request['kind'],{}).items():
            match=re.search(pattern,part,re.I)
            if match and (sign:=polarity(match)) is not None:
                (forbidden if sign=='excluded' else required).add(fact)
                evidence.append({'field':fact,'polarity':sign,
                    'text':part,'normalized_start':chunk.start(),'normalized_end':chunk.end()})
        annual=re.search(r'每年|年均|年度|kg\s*CO2e\s*/\s*(?:a|年)',part,re.I)
        if request['kind']=='lifecycle' and annual and polarity(annual)=='requested':
            unsupported.append('ANNUAL_CARBON_NOT_A_STORED_STUDY_PERIOD_FACT')
        if NO_EXPLANATION.search(part):no_explanation=True
        for topic,pattern in TOPICS.items():
            match=re.search(pattern,part)
            if match and (sign:=polarity(match)) is not None: (excluded if sign=='excluded' else topics).add(topic)
    if no_explanation:excluded.update(['meaning','area','period','scope','status','history'])
    conflicts=required&forbidden
    if conflicts:unsupported.append('CONTRADICTORY_METRIC_REQUEST')
    if topics&excluded:unsupported.append('CONTRADICTORY_EXPLANATION_REQUEST')
    return {'required_facts':sorted(required),'forbidden_facts':sorted(forbidden),
            'required_topics':sorted(topics),'forbidden_topics':sorted(excluded),
            'unsupported':sorted(set(unsupported)),'uncertain':sorted(set(uncertain)),
            'matches':evidence,'intent_verified':False,
            'notice':'Checks explicit supported vocabulary and exclusions only; not proof of full language understanding.'}


def validate(question,request,requests,facts,topics):
    constraint=analyze(question,request,requests)
    problems={}
    if constraint['unsupported']:problems['requires_clarification_or_unsupported']=constraint['unsupported']
    for name,values in [('missing_required_facts',set(constraint['required_facts'])-set(facts)),
                        ('excluded_facts_selected',set(constraint['forbidden_facts'])&set(facts)),
                        ('missing_required_topics',set(constraint['required_topics'])-set(topics)),
                        ('excluded_topics_selected',set(constraint['forbidden_topics'])&set(topics))]:
        if values:problems[name]=sorted(values)
    if problems:
        import json
        raise core.ValidationError('Original request constraint mismatch; do not substitute another metric: '+json.dumps(problems,ensure_ascii=False))
    return constraint
