"""Source IFC engineering/interior meshes, separate from thermal zone geometry.

No bounding-box substitutes, furniture generation or implicit thermal mapping.
Budgets fail explicitly; absent/failed source representations remain in inventory.
"""
from collections import Counter
from functools import lru_cache
import json
import threading
import time

import numpy as np
from pydantic import Field, StrictFloat

from . import core
from .schema import Contract


GROUPS = {
    'structure': ('IfcWall', 'IfcSlab', 'IfcColumn', 'IfcBeam', 'IfcRoof', 'IfcCurtainWall'),
    'doors_windows': ('IfcDoor', 'IfcWindow', 'IfcOpeningElement'),
    'stairs': ('IfcStair', 'IfcStairFlight', 'IfcRailing', 'IfcRamp', 'IfcRampFlight'),
    'services': ('IfcDistributionElement',),
    'furniture': ('IfcFurnishingElement',),
}


@lru_cache(maxsize=2)
def _geometry_data(path, verified_sha256):
    return core.read_json(path)


class ComponentBuild(Contract):
    file_id: str
    origin_m: tuple[StrictFloat, StrictFloat, StrictFloat] = (0., 0., 0.)
    storey_ids: list[str] = Field(default_factory=list, max_length=200)


def source_meshes(path, options):
    import ifcopenshell
    import ifcopenshell.geom
    from ifcopenshell.util.element import get_psets
    from .model_import import spatial_ancestor, storey_inventory
    document = ifcopenshell.open(str(path))
    inventory = storey_inventory(document)
    if set(options.storey_ids)-{s['id'] for s in inventory['storeys']}:
        raise core.ValidationError('构件范围包含源文件中不存在的楼层')
    products = {e.GlobalId: (group, e) for group, kinds in GROUPS.items() for kind in kinds for e in document.by_type(kind)}
    rows, selected = {}, []
    for gid, (group, entity) in products.items():
        storey = spatial_ancestor(entity, 'IfcBuildingStorey')
        if options.storey_ids and (not storey or storey.GlobalId not in options.storey_ids):
            continue
        building = spatial_ancestor(entity, 'IfcBuilding')
        rows[gid] = {'source_id': gid, 'entity_id': entity.id(), 'ifc_type': entity.is_a(),
                     'category': group, 'name': str(entity.Name or gid)[:500],
                     'storey_id': storey.GlobalId if storey else None, 'storey_name': str(storey.Name or '') if storey else None,
                     'building_id': building.GlobalId if building else None,
                     'status': 'NO_REPRESENTATION' if not entity.Representation else 'GEOMETRY_FAILED',
                     'thermal_mapping': 'NOT_BOUND', 'vertices': [], 'triangles': []}
        if entity.Representation:
            selected.append(entity)
    if len(rows) > 15000:
        raise core.ValidationError('源构件超过15000，请选择楼层；未丢弃构件冒充完整模型')
    started = time.perf_counter()
    settings = ifcopenshell.geom.settings()
    settings.set('use-world-coords', True)
    # Native tessellation and opening subtraction; preserve actual source triangles.
    iterator = ifcopenshell.geom.iterator(settings, document, 2, include=selected) if selected else None
    triangle_count = 0
    if iterator and iterator.initialize():
        while True:
            shape = iterator.get()
            entity = document.by_id(shape.id)
            row = rows[entity.GlobalId]
            vertices = np.asarray(shape.geometry.verts).reshape(-1, 3)-np.asarray(options.origin_m)
            triangles = np.asarray(shape.geometry.faces).reshape(-1, 3)
            triangle_count += len(triangles)
            if triangle_count > 2_000_000 or time.perf_counter()-started > 120:
                raise core.ValidationError('源构件三角面或120秒预算超限，请选择楼层；未返回截断模型')
            if (len(vertices) and len(triangles) and np.isfinite(vertices).all() and
                    triangles.min() >= 0 and triangles.max() < len(vertices)):
                row.update(status='SOURCE_MESH', vertices=vertices.tolist(), triangles=triangles.tolist(),
                           bounds_m=[vertices.min(axis=0).tolist(), vertices.max(axis=0).tolist()])
                if row['category'] in {'services', 'doors_windows', 'furniture'}:
                    properties = get_psets(entity, psets_only=True)
                    row['source_properties'] = {
                        str(k): {str(key): value if isinstance(value, (bool, int, float)) else str(value)[:1000]
                                 for key, value in vals.items() if key != 'id'}
                        for k, vals in properties.items() if isinstance(vals, dict)}
            if not iterator.next():
                break
    counts = Counter(row['category'] for row in rows.values())
    status = Counter(row['status'] for row in rows.values())
    return {'schema_version': 'vra.source-components.v1', 'schema': document.schema,
            'origin_m': list(options.origin_m), 'selected_storey_ids': options.storey_ids,
            'inventory': inventory, 'source_component_count': len(products), 'in_scope_count': len(rows),
            'category_counts': dict(counts), 'status_counts': dict(status), 'triangles': triangle_count,
            'components': list(rows.values()), 'elapsed_seconds': time.perf_counter()-started,
            'tessellation': {'engine': 'IfcOpenShell/OpenCASCADE', 'linear_deflection_m': settings.get('mesher-linear-deflection'),
                             'angular_deflection_rad': settings.get('mesher-angular-deflection'), 'opening_subtraction': True},
            'limits': ['Actual source meshes, not a complete as-built survey', 'Absent furniture/equipment are not generated',
                       'Unrepresented/failed components remain in inventory', 'Components are not automatically thermal surfaces, equipment performance or connected hydraulic systems']}


class Components:
    def __init__(self, domain):
        self.domain, self.store = domain, domain.store
        self.capacity = threading.BoundedSemaphore(1)

    def build(self, project_id, body, actor):
        from .domain import identifier
        source, path = self.domain.file_record(project_id, body.file_id)
        if path.suffix.lower() != '.ifc':
            raise core.ValidationError('工程构件提取须使用IFC原文件')
        if not self.capacity.acquire(blocking=False):
            raise core.ValidationError('构件解析正在运行，请稍后重试')
        try:
            data = source_meshes(path, body)
            current, _ = self.domain.file_record(project_id, body.file_id)
            if current['hash'] != source['hash']:
                raise core.ValidationError('构件解析期间源文件发生变化，未采纳')
            asset_id = identifier('component')
            asset = self.domain.add_file(project_id, asset_id+'.json',
                json.dumps(data, ensure_ascii=False, allow_nan=False).encode())
            record = {k: v for k, v in data.items() if k != 'components'}
            record.update(component_id=asset_id, project_id=project_id, name=source['name']+' · 源构件',
                source_file_id=body.file_id, source_file_hash=source['hash'], actor=actor, created_at=core.now(),
                geometry_file_id=asset['file_id'], geometry_file_hash=asset['hash'], rules_sha256=core.sha(__file__))
            return self.store.put('component', record)
        finally:
            self.capacity.release()

    def geometry(self, project_id, asset_id, storey_id=None, category=None, offset=0, limit=100):
        record = self.store.get('component', asset_id)
        if record['project_id'] != project_id:
            raise core.ValidationError('构件资料不属于当前项目')
        for fid, expected in ((record['source_file_id'], record['source_file_hash']),
                              (record['geometry_file_id'], record['geometry_file_hash'])):
            source, path = self.domain.file_record(project_id, fid)
            if source['hash'] != expected:
                raise core.ValidationError('构件来源或几何文件已变化，请重建；未显示失效模型')
        if record['rules_sha256'] != core.sha(__file__):
            raise core.ValidationError('构件解析规则已变化，请重新提取，旧版本保留')
        data = _geometry_data(str(path), record['geometry_file_hash'])
        rows = [r for r in data['components'] if (not storey_id or r['storey_id'] == storey_id) and
                (not category or r['category'] == category)]
        return {'component_id': asset_id, 'total': len(rows), 'offset': offset, 'limit': limit,
                'components': rows[offset:offset+limit], 'remaining': max(0, len(rows)-offset-limit),
                'origin_m': record['origin_m'], 'limits': record['limits']}


def register_components(app, domain):
    from fastapi import Request, Query
    service = Components(domain)

    @app.get('/api/projects/{project_id}/components')
    def list_components(project_id: str):
        return domain.store.list('component', project_id)

    @app.get('/api/projects/{project_id}/components/sources')
    def sources(project_id: str):
        return [{k: f[k] for k in ('file_id', 'name', 'hash', 'size')} for f in domain.store.list('file', project_id)
                if f['name'].lower().endswith('.ifc')]

    @app.post('/api/projects/{project_id}/components', status_code=201)
    def build(project_id: str, body: ComponentBuild, request: Request):
        return service.build(project_id, body, request.state.user['display_name'])

    @app.get('/api/projects/{project_id}/components/{component_id}/geometry')
    def geometry(project_id: str, component_id: str, storey_id: str | None = None, category: str | None = None,
                 offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=300)):
        if category and category not in GROUPS:
            raise core.ValidationError('未知构件类别')
        return service.geometry(project_id, component_id, storey_id, category, offset, limit)
