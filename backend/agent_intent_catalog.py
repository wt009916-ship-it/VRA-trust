"""Domain meanings and exact user-question anchors, never inferred numeric data."""
import re

MEANINGS = {
 'thermal': {
  'total_resistance_m2k_w': '总热阻 R；含内外表面热阻和全部材料层；m² K/W；一维稳态，不是层热阻或全年节能率',
  'layer_resistance_m2k_w': '材料层热阻合计；只求和材料层d/λ，不含内外表面热阻；m² K/W',
  'u_w_m2k': '传热系数 U=1/总热阻；W/(m² K)；不是热阻或全年能耗'},
 'lifecycle': {
  'boundary_total_kgco2e': '声明核算边界内所有纳入阶段的碳排放总量；kgCO2e；整个评估期，不是年量',
  'kgco2e_m2_over_study_period': '单位面积碳排放总量=边界总量/声明面积；kgCO2e/m²；整个评估期，不是运行阶段量或年量',
  'stage.production': '仅材料生产阶段碳排放总量；kgCO2e；整个评估期',
  'stage.transport': '仅材料运输阶段碳排放总量；kgCO2e；整个评估期',
  'stage.construction': '仅施工阶段碳排放总量；kgCO2e；整个评估期，排除或缺测不能记零',
  'stage.operation': '仅建筑运行阶段碳排放总量；kgCO2e；整个评估期，不是每年排放或单位面积量',
  'stage.end_of_life': '仅寿命终结阶段碳排放总量；kgCO2e；整个评估期'},
 'cost': {'material_total': '声明材料清单的采购金额合计；币种与报价日期由来源确定；不是工程总造价'},
 'engineering': {
  'max_abs_moment_nm': '梁最大绝对弯矩；N m；静力工况',
  'max_abs_shear_n': '梁最大绝对剪力；N；静力工况',
  'max_deflection_m': '梁最大向下挠度；m；静力工况',
  'max_elastic_bending_stress_pa': '梁最大线弹性弯曲应力；Pa；不是承载力或安全结论',
  'left_reaction_n': '左支座竖向反力；N',
  'right_reaction_n': '右支座竖向反力；N',
  'left_reaction_moment_nm': '左端支座反力矩；N m；不是跨内最大弯矩'},
 'schedule': {
  'planned_duration_days': '声明基准计划的总工期；连续经过日day；不是进度情景完工日',
  'forecast_as_of_day': '进度记录截至日；相对于声明时间零点的经过日day',
  'forecast_finish_day': '按明确剩余工期情景预测的完工日；相对时间零点day；不是工期偏差',
  'forecast_finish_variance_days': '情景完工日减计划完工日的偏差；day；不是完工日'},
 'operation': {
  'sample_count': '运行数据CSV样本行数；count；整个观测窗口',
  'cell_issue_count': '缺失或无效数值单元格数量；count；不是样本行数',
  'gap_count': '超过最大采样间隔的时间缺口数量；count；不是无效单元数',
  'rule_event_sum': '各声明规则事件次数之和；count；可能重叠，不是设备故障数',
  'rule_unknown_sample_sum': '各规则未知样本次数之和；count；可能重复，不是独立样本行数'},
}


def fragments(question):
    """Deterministic exact spans, including punctuation; no model paraphrase.

    Split at sentence/semicolon/newline boundaries, then cap chunks at 400
    Unicode code points. Decimal dots and record identifiers remain intact.
    Bounds come from the existing 4000-character Chat contract.
    """
    rows=[]
    for match in re.finditer(r'[^。！？；;\n]+[。！？；;\n]*|[。！？；;\n]+',question):
        for start in range(match.start(),match.end(),400):
            end=min(start+400,match.end())
            if question[start:end].strip():
                rows.append({'fragment_id':'q'+str(len(rows)+1),'start':start,'end':end,'text':question[start:end]})
    if len(rows)>24:
        rows=[{'fragment_id':'q'+str(i//400+1),'start':i,'end':min(i+400,len(question)),
               'text':question[i:i+400]} for i in range(0,len(question),400) if question[i:i+400].strip()]
    return rows


def meaning_description(kind):
    return '选择用户实际要求的字段；键名含义：'+'；'.join(k+' = '+v for k,v in MEANINGS[kind].items())
