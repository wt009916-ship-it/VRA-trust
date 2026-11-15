"""Authenticated project routes; main API enforces ownership and CSRF."""
import csv
import io

from fastapi import Query
from fastapi.responses import HTMLResponse, Response

from . import core
from .thermal_bridge import Section, ThermalBridge, report


def register(app, domain):
    service = ThermalBridge(domain)
    app.state.thermal_bridge = service
    base = '/api/projects/{project_id}/thermal-bridges'

    @app.post(base, status_code=201)
    def create(project_id: str, body: Section):
        return service.save(project_id, body)

    @app.get(base)
    def history(project_id: str, limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000)):
        with domain.store.connect() as con:
            rows = con.execute("SELECT id FROM records WHERE kind='thermalbridge' AND project_id=? AND revision=1 ORDER BY rowid DESC LIMIT ? OFFSET ?",
                               (project_id, limit + 1, offset)).fetchall()
        items = []
        for row in rows[:limit]:
            current = service.view(project_id, row['id'])
            items.append({**{k: current[k] for k in ('thermalbridge_id', 'created_at', 'status', 'stale_reasons')},
                          'name': current['input']['name']})
        return {'items': items, 'next_offset': offset + limit if len(rows) > limit else None}

    @app.get(base + '/{thermalbridge_id}')
    def view(project_id: str, thermalbridge_id: str):
        return service.view(project_id, thermalbridge_id)

    @app.get(base + '/{thermalbridge_id}/report.html', response_class=HTMLResponse)
    def html_report(project_id: str, thermalbridge_id: str):
        return report(service.view(project_id, thermalbridge_id))

    @app.get(base + '/{thermalbridge_id}/temperatures.csv')
    def temperature_csv(project_id: str, thermalbridge_id: str):
        record = service.view(project_id, thermalbridge_id)
        result = record['result']
        if not result or result['temperature_c'] is None:
            raise core.ValidationError('当前无可导出的温度场；请补全输入或重新计算')
        buffer = io.StringIO(newline='')
        writer = csv.writer(buffer)
        writer.writerow(['record_id', 'status', 'x_m', 'y_m', 'cell_temperature_c'])
        for y, row in zip(result['y_centres_m'], result['temperature_c']):
            for x, t in zip(result['x_centres_m'], row):
                writer.writerow([thermalbridge_id, record['status'], x, y, t])
        return Response(buffer.getvalue(), media_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition': 'attachment; filename="thermal-bridge-temperatures.csv"'})
