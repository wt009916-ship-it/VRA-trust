"""Human-readable decision reports share the exact API assessment snapshot."""
import html
import io
import json
from pathlib import Path

from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def sections(report):
    study, certificate = report['study'], report['certificate']
    assessment = study['assessment']
    statuses = {'CANDIDATES_FOR_REVIEW': '已有待复核候选', 'NO_ELIGIBLE_CANDIDATE': '没有满足条件的候选',
                'FEASIBLE': '满足已声明约束', 'EXCLUDED': '未满足约束', 'INCOMPLETE': '决策指标不完整', 'FAILED': '失败',
                'STALE': '证据已失效', 'RUNNING': '正在计算', 'SUCCEEDED': '等待更新评估'}
    def numeric(value):
        return f'{value:,.2f}' if isinstance(value, (float, int)) else '未知'
    result = [('材料方案决策研究', [report['project']['name'], '状态：' + statuses.get(certificate['status'], certificate['status']),
               '研究 ID：' + study['study_id'], '生成时间：' + report['generated_at'],
               '工程师未签署；候选集用于条件复核。']),
              ('研究范围', ['基准运行：' + study['source_run_id'], '替换材料层：' + study['target_material'],
                            '用户依据：' + study['basis'], '真实引擎调用：' + str(study['engine_calls']),
                            '输入版本或损坏原因：' + '；'.join(study.get('stale_reasons', []))])]
    if assessment:
        labels = {'energy_kwh': '年场地能耗 kWh', 'cost_cny': '增量初始造价 CNY', 'cooling_unmet_h': '占用制冷未达设定点 h',
                  'heating_unmet_h': '占用供暖未达设定点 h', 'carbon_kg': '运行 CO2 kg'}
        bounds = {'max_cost_cny': '造价上限 CNY', 'max_cooling_unmet_h': '制冷未达时长上限 h',
                  'max_heating_unmet_h': '供暖未达时长上限 h', 'min_energy_saving_pct': '最低节能率 %'}
        result.append(('目标与约束', ['比较目标：' + '、'.join(labels[k] for k in assessment['objectives']),
                                    '工程约束：' + '；'.join(bounds[k] + '：' + (str(v) if v is not None else '未声明') for k, v in assessment['constraints'].items()),
                                    '完成 ' + str(assessment['evaluated_options']) + ' / ' + str(assessment['total_options']) + ' 个材料候选',
                                    '待测候选：' + '、'.join(assessment['untested_options']),
                                    '非支配候选：' + '、'.join(assessment['pareto_option_ids']), assessment['explanation']]))
        for row in assessment['rows']:
            result.append((row['name'] + ' / ' + statuses[row['status']], [
                '；'.join(labels[k] + '：' + numeric(v) for k, v in row['values'].items()),
                '相对基准节能率 %：' + numeric(row['energy_saving_pct']),
                '未满足约束：' + '；'.join(bounds[v['constraint']] + '，实际 ' + str(v['actual']) + ' / 约束 ' + str(v['limit']) for v in row['violations']),
                '缺少指标：' + '、'.join(labels[k] for k in row['missing']), '支配此方案：' + '、'.join(row['dominated_by']),
                '参数来源性质：' + str(row['source_nature']), '费用来源性质：' + str(row.get('cost_source_nature')), '运行：' + str(row['run_id']),
                'Warning：' + str(row['warnings'])]))
        profile = assessment['factor_snapshot']
        result.append(('碳因子依据', ['情景性质：' + ('教学/假设情景' if profile.get('scenario') else '登记因子'),
                      '适用地区：' + profile.get('region', '未知')] + [
                          carrier + '：' + str(factor['value']) + ' ' + factor['unit'] + '；来源：' + factor['source']
                          for carrier, factor in profile['factors'].items()] + ['仅运行 CO2；不是生命周期碳排或可交易信用。']))
    else:
        result.append(('当前结论不可用', ['研究未完成、已失败或输入/因子变化；不能引用历史候选集作为当前判断。']))
    result.append(('材料和费用证据', []))
    for card in study['material_snapshots'].values():
        result[-1][1].extend([card['name'] + ' / v' + str(card['revision']) + ' / ' + card['material_id'],
                         '批次：' + (card['batch'] or '未知') + '；导热系数 W/(m·K)：' + str(card['conductivity_w_mk'])
                         + '；密度 kg/m3：' + str(card['density_kg_m3']) + '；比热 J/(kg·K)：' + str(card['specific_heat_j_kgk']),
                         '测试条件：' + str(card['test_conditions']), '适用范围：' + str(card['applicability']),
                         '参数定位：' + str(card['source_locator']), '复核人 / 依据：' + card['responsible_person'] + ' / ' + str(card['review_note'])])
        for source in card['evidence_snapshot']:
            result[-1][1].append(source['name'] + ' / ' + source['status'] + ' / v' + str(source['revision']) + ' / ' + source['source_locator'] + ' / SHA256 ' + source['hash'])
    for option in study['options']:
        result[-1][1].append(option['name'] + '：增量造价 ' + str(option['cost_cny']) + ' CNY；范围：' + str(option['cost_scope']))
    for source in study['cost_snapshots'].values():
        result[-1][1].append(source['name'] + ' / ' + source['status'] + ' / v' + str(source['revision']) + ' / ' + source['source_locator'] + ' / SHA256 ' + source['hash'])
    result.append(('下一步补证任务', [task['title'] + '：' + task['action'] for task in report['diagnosis']['tasks']]))
    result.append(('适用边界与复核', study['limitations'] + ['基准来源：' + json.dumps(study['source_provenance'], ensure_ascii=False),
                  '导出是生成时快照，后续使用须按研究 ID 重新核验。原始 IDF、SQL、ERR 与哈希见证据 ZIP。']))
    return result


def decision_html(report):
    content = ''.join('<section><h2>' + html.escape(title) + '</h2>' + ''.join('<p>' + html.escape(line) + '</p>' for line in lines) + '</section>'
                      for title, lines in sections(report))
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>材料方案决策研究</title><style>body{max-width:1000px;margin:40px auto;padding:0 24px;font:15px/1.7 system-ui;color:#16352f}p{overflow-wrap:anywhere}section{border-bottom:1px solid #ddd;padding:16px 0}</style>' + content + '</html>'


def decision_pdf(report):
    font = 'STSong-Light'
    for path in [Path('C:/Windows/Fonts/simhei.ttf'), Path('/usr/share/fonts/truetype/arphic/uming.ttc')]:
        if path.is_file():
            font = 'VRA-Decision-CJK'
            pdfmetrics.registerFont(TTFont(font, str(path)))
            break
    else:
        pdfmetrics.registerFont(UnicodeCIDFont(font))
    body = ParagraphStyle('body', fontName=font, fontSize=9, leading=15, wordWrap='CJK')
    heading = ParagraphStyle('heading', parent=body, fontSize=14, leading=22, spaceBefore=16)
    story = []
    for title, lines in sections(report):
        story.append(Paragraph(html.escape(title), heading))
        for line in lines:
            story.append(Paragraph(html.escape(line), body))
            story.append(Spacer(1, 5))
    output = io.BytesIO()
    def footer(canvas, doc):
        canvas.setFont(font, 8)
        canvas.drawString(72, 30, 'VRA-Trust | 生成时快照；使用前复核研究版本 | ' + str(doc.page))
    SimpleDocTemplate(output, title='VRA-Trust Material Decision Study', author='VRA-Trust').build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
