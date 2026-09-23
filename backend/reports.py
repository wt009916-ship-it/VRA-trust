"""HTML and actual PDF render the same validated report object."""
import html
import io
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak


def report_html(report):
    payload = html.escape(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    run = report["run"]
    return f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
    <title>VRA-Trust · 工程证据报告</title><style>
    body{{max-width:1000px;margin:40px auto;font:15px/1.7 system-ui;color:#16352f;padding:0 24px}}
    pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f3;padding:20px;font-size:12px}}
    .notice{{border-left:4px solid #a56828;padding:12px;background:#fff8ea}}@media print{{button{{display:none}}}}
    </style><h1>VRA-Trust 工程证据报告</h1><p>状态：{html.escape(run['status'])} · {html.escape(run['run_id'])}</p>
    <p class="notice">Decision Certificate 草稿 · 未签署。真实仿真不等于实测验证；当前不作确定最优推荐。</p>
    <p>以下与 JSON / PDF 使用同一服务端核验对象。导出的文件是生成时快照，后续使用须重新核验 run_id。</p>
    <p>浏览器菜单或 Ctrl+P 可打印；PDF 下载由服务端生成。</p><pre>{payload}</pre></html>"""


def report_pdf(report):
    output = io.BytesIO()
    font = "STSong-Light"
    for candidate in [Path("C:/Windows/Fonts/simhei.ttf"), Path("/usr/share/fonts/truetype/arphic/uming.ttc")]:
        if candidate.is_file():
            font = "VRA-CJK"
            pdfmetrics.registerFont(TTFont(font, str(candidate)))
            break
    else:
        pdfmetrics.registerFont(UnicodeCIDFont(font))
    body = ParagraphStyle("body", fontName=font, fontSize=9, leading=15, wordWrap="CJK", textColor=colors.HexColor("#19372f"))
    heading = ParagraphStyle("heading", parent=body, fontSize=18, leading=26, spaceAfter=16)
    sub = ParagraphStyle("sub", parent=body, fontSize=12, leading=20, spaceBefore=16, spaceAfter=8)
    story = []
    def para(value, style=body):
        text = html.escape(str(value) if value is not None else "未提供").replace("²", "<super>2</super>")
        return Paragraph(text, style)
    def section(title):
        story.append(para(title, sub))
    def rows(items):
        table = Table([[para(a), para(b)] for a, b in items], colWidths=[120, 403], hAlign="LEFT")
        table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), .3, colors.HexColor("#d7e0d5")), ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 7)]))
        story.append(table)
    run, project, cert = report["run"], report["project"], report["certificate"]
    metrics, carbon = run["metrics"] or {}, run["carbon"] or {}
    def numeric(value):
        return f"{value:,.2f}" if isinstance(value, (float, int)) else "未计算 / 不可用"
    story += [para("稀土智暖 VRA-Trust", heading), para("工程证据报告 / Decision Certificate 草稿", sub), para("未签署。当前不能给出确定最优推荐。参考仿真不等于实测验证。"), Spacer(1, 16)]
    rows([("项目", project["name"]), ("数据性质", project["data_nature"]), ("运行", run["run_id"]), ("方案 / 状态", run["scheme_id"] + " / " + run["status"]), ("报告时间 UTC", report["generated_at"]), ("证书状态", cert["status"])])
    section("01  计算结果与适用范围")
    rows([("全年场地能耗 kWh", numeric(metrics.get("annual_energy_kwh"))), ("总建筑面积 m2", numeric(metrics.get("area_m2"))), ("EUI kWh/(m2·a)", numeric(metrics.get("eui_kwh_m2a"))), ("运行 CO2 kg", numeric(carbon.get("operating_carbon_kg"))), ("碳核算性质", "教学因子情景，非正式核算" if carbon.get("scenario") else carbon.get("status", "未计算")), ("引擎调用 / Warning", str(run["engine_calls_executed"]) + " / " + str(run["warnings_count"])), ("生命周期 / 签发信用", "均未评估；运行 CO2 不等于 LCA 或碳信用")])
    if run["error"] or run["stale_reasons"]:
        story.append(para("拒绝原因：" + str(run["error"] or "；".join(run["stale_reasons"]))))
    story.append(PageBreak())
    story.append(para("判断边界与补证动作", heading))
    section("02  决策状态")
    rows([("当前建议", "不发布确定推荐"), ("候选方案", ", ".join(cert["candidate_schemes"])), ("目标", cert["objective"]), ("约束", "；".join(cert["constraints"])), ("稳定性", cert['stability_status']), ("成立条件", "；".join(cert["conditions"])), ("失效条件", "；".join(cert["invalidation_conditions"])), ("反例", "未搜索，不能解读为无反例" if cert['counterexamples'] is None else str(len(cert['counterexamples'])) + ' 个已记录；仅限本次搜索域和预算'), ("未排除的不确定性", "；".join(cert["unresolved_uncertainties"])), ("建议补证", "；".join(cert["suggested_evidence_actions"])), ("工程师签署", cert["engineer_review"])])
    if report.get('robustness'):
        study = report['robustness']
        section('02.1  反例搜索范围与预算')
        rows([('搜索 ID', study['search_id']), ('状态 / 目标', study['status'] + ' / ' + study['objective']),
              ('调用数 / 预算', str(study['engine_calls']) + ' / ' + str(study['budget'])),
              ('离散网格覆盖', str(study.get('coverage', '尚未完成'))), ('范围声明', study.get('limitation', study['domain_type']))])
        for axis in study['axes']:
            story.append(para(json.dumps(axis, ensure_ascii=False)))
        for point in study['points']:
            story.append(para(json.dumps({'parameters': point['parameters'], 'order': point['order'], 'flipped': point['flipped'], 'run_ids': [r['run_id'] for r in point['runs']]}, ensure_ascii=False)))
    section("03  舒适性及输出限制")
    for key, value in metrics.get("comfort_hours", {}).items():
        story.append(para(key + ": " + numeric(value) + " h"))
    for note in run["limitations"]:
        story.append(para(note))
    story.append(PageBreak())
    story.append(para("证据索引与版本", heading))
    for index, ev in enumerate(report["evidence"], 1):
        section(f"04.{index}  {ev['name']}")
        rows([("Evidence ID / 版本", ev["evidence_id"] + " / v" + str(ev["revision"])), ("性质 / 复核", ev["status"] + " / " + ev["review_state"]), ("源文件 / 定位", str(ev["source_file"]) + " / " + ev["source_locator"]), ("SHA256", ev["hash"]), ("来源 / 授权", ev["authority"] + " / " + ev["permission"]), ("责任人 / 时间", ev["responsible_person"] + " / " + ev["timestamp"]), ("方法 / 不确定性", ev["acquisition_method"] + " / " + str(ev["uncertainty"])), ("数值 / 单位 / 置信度", json.dumps([ev["value"], ev["unit"], ev["confidence"]], ensure_ascii=False)), ("复核说明", ev["review_note"])])
    story.append(PageBreak())
    story.append(para("计算版本与复核定位", heading))
    section("05  Result Provenance")
    rows(list((run["provenance"] or {"status": "无有效结果版本"}).items()))
    if carbon.get('provenance'):
        section('05.1  独立碳派生版本（不改写原仿真）')
        for key in ['carbon_id', 'run_id', 'factor_hash', 'source_result_hash', 'calculator_version', 'timestamp', 'energyplus_calls']:
            story.append(para(key + ': ' + str(carbon['provenance'].get(key))))
    section("06  SQL 来源定位")
    for key, locator in metrics.get("locators", {}).items():
        story.append(para(key + " : " + " / ".join(str(locator.get(k, "")) for k in ["table", "row", "column", "unit", "raw_value"])))
    section("07  重放与责任边界")
    story.append(para("证据 ZIP 包含 IDF、EPW、运行请求、ERR、SQL、结果和文件哈希。以同版本 EnergyPlus 重放 input/model.idf 与 input/weather.epw，再运行 parser 校验。PDF 是生成时快照；使用前须查询 run_id 当前状态。"))
    story.append(para("不替代法定设计、审图、检测或 CCER 审定核查。本地哈希不是第三方数字签名。完整机器可读字段见同源 report.json。"))
    def footer(canvas, doc):
        canvas.setFont(font, 8)
        canvas.drawString(36, 22, "VRA-Trust | 生成时快照；后续需重新核验版本 | " + str(doc.page))
    SimpleDocTemplate(output, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36,
                      title="VRA-Trust Evidence Report", author="VRA-Trust").build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
