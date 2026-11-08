"""Current-source API records for material-envelope collections."""
import html
import json
from fastapi.responses import HTMLResponse
from pydantic import Field, StrictInt
from .cad_union import IfcUnions, UnionRequest


class MaterialCollectionRequest(UnionRequest):
    product_ids: list[StrictInt] = Field(min_length=2, max_length=16)


class MaterialCollections(IfcUnions):
    operation = 'ifc_material_collection'
    record_kind = 'materialset'
    assessment = 'SELECTED_MATERIAL_ENVELOPES_NOT_PURCHASE_OR_CERTIFIED_QUANTITIES'


def report(record):
    result = record.get('result') or {}
    valid = record['status'] == result.get('status') == 'measured'
    esc = lambda x: html.escape(str(x))
    rows = ''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in (
        '#'+str(r['material_id']), r['material_name'] or '未命名', r['source_sum_m3'],
        r['overlap_deduction_m3'], r['union_envelope_m3']))+'</tr>' for r in result.get('materials', [])) if valid else ''
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>多构件材料包络计量</title>'
            '<body><h1>多构件材料包络计量</h1><p>选定墙体：'+esc(', '.join('#'+str(i) for i in record['product_ids']))+'</p>'
            '<p>当前状态：'+esc(record['status'])+'。同一IFC材料实体的空间重叠只计一次；不同材料空间冲突时不提供汇总量。</p>'
            '<p>这是模型材料层包络，已沿用模型洞口；不是采购材料净量。实体比例、密度、损耗、报价和施工计量规则须另有依据。</p>'
            +('<table><tr><th>材料实体</th><th>模型名称</th><th>原始和 m³</th><th>重复扣除 m³</th><th>去重包络 m³</th></tr>'+rows+'</table>'
              if valid else '<p>数量 —；'+esc(result.get('reason') or '来源或计算版本失效，旧量已撤下')+'</p>')
            +'<details><summary>来源、构件层对应和计算回执</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'
            +esc(json.dumps(record, ensure_ascii=False, indent=2))+'</pre></details></body></html>')


def register(app, cad):
    service = MaterialCollections(cad)
    app.state.material_collections = service

    @app.post('/api/projects/{project_id}/ifc-material-collections', status_code=201)
    def create(project_id: str, body: MaterialCollectionRequest):
        return service.create(project_id, body)

    @app.get('/api/projects/{project_id}/ifc-material-collections')
    def history(project_id: str):
        return [service.view(project_id, r['materialset_id']) for r in service.store.list('materialset', project_id)]

    @app.get('/api/projects/{project_id}/ifc-material-collections/{materialset_id}')
    def current(project_id: str, materialset_id: str):
        return service.view(project_id, materialset_id)

    @app.get('/api/projects/{project_id}/ifc-material-collections/{materialset_id}/report.html', response_class=HTMLResponse)
    def html_report(project_id: str, materialset_id: str):
        return report(service.view(project_id, materialset_id))
