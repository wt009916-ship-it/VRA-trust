"""Bounded read-only native parsing subprocess. No external references are loaded."""
import json
import math
import sys
from collections import Counter
from pathlib import Path

MAX_OBJECTS = 10000


def parse_dxf(path):
    import ezdxf
    from ezdxf import units
    if __package__:
        from .dxf_geometry import inspect_geometry
    else:
        from dxf_geometry import inspect_geometry
    doc = ezdxf.readfile(path)
    audit = doc.audit()
    if audit.errors or audit.fixes:
        raise ValueError('DXF requires repair; original preserved, no automatic recovery')
    entities = list(doc.modelspace())
    if len(entities) > MAX_OBJECTS:
        raise ValueError('Modelspace entity limit exceeded')
    code = doc.units
    scale = units.conversion_factor(code, units.M) if code in range(1, 25) else None
    rows = []
    for e in entities:
        row = {'handle': e.dxf.handle, 'type': e.dxftype(), 'layer': e.dxf.layer}
        if e.dxftype() == 'LINE':
            start, end = list(e.dxf.start), list(e.dxf.end)
            if not all(math.isfinite(x) for x in start + end):
                raise ValueError('Non-finite DXF coordinate')
            row.update(start=start, end=end, length_m=None if scale is None else math.dist(start, end)*scale)
        elif e.dxftype() in {'TEXT', 'MTEXT'}:
            row['text'] = e.dxf.text if e.dxftype() == 'TEXT' else e.text
        elif e.dxftype() == 'INSERT':
            row['block_name'] = e.dxf.name
            row['expanded'] = False
        rows.append(row)
    return {'format': 'DXF', 'version': doc.dxfversion, 'parser': 'ezdxf '+ezdxf.__version__,
        'unit_code': code, 'length_scale_to_m': scale,
        'counts': dict(Counter(r['type'] for r in rows)), 'objects': rows,'geometry':inspect_geometry(doc,scale),
        'limitations': ['counts/objects保留模型空间顶层统计；geometry另列块/阵列展开实例，不与顶层数量相加。图纸空间不计入。',
            'LINE、基本圆弧/椭圆、多段线提供限定几何测量；不是净建筑工程量或构件语义分类。',
            '单位未指定时长度保持null，不默认毫米；文字与尺寸标注不自动作为真实几何。']}


def parse_ifc(path):
    import ifcopenshell
    from ifcopenshell.util.element import get_container
    from ifcopenshell.util.unit import calculate_unit_scale
    doc = ifcopenshell.open(str(path))
    projects = doc.by_type('IfcProject')
    if len(projects) != 1:
        raise ValueError('Exactly one IfcProject is required')
    length_units = [u for u in (projects[0].UnitsInContext.Units if projects[0].UnitsInContext else []) if getattr(u, 'UnitType', None) == 'LENGTHUNIT']
    if len(length_units) > 1:
        raise ValueError('Conflicting IFC length units')
    scale = calculate_unit_scale(doc) if length_units else None
    products = doc.by_type('IfcProduct')
    if len(products) > MAX_OBJECTS:
        raise ValueError('IFC product limit exceeded')
    rows, seen, issues = [], set(), []
    for e in products:
        if not e.GlobalId or e.GlobalId in seen:
            raise ValueError('Missing or duplicate IFC GlobalId')
        seen.add(e.GlobalId)
        container = get_container(e)
        props = []
        for rel in getattr(e, 'IsDefinedBy', ()):
            if not rel.is_a('IfcRelDefinesByProperties'):
                continue
            pset = rel.RelatingPropertyDefinition
            if pset.is_a('IfcPropertySet'):
                for p in pset.HasProperties:
                    if p.is_a('IfcPropertySingleValue'):
                        value = p.NominalValue.wrappedValue if p.NominalValue else None
                        props.append({'set': pset.Name, 'name': p.Name, 'value': value,
                            'value_type': p.NominalValue.is_a() if p.NominalValue else None,
                            'explicit_unit': str(p.Unit) if p.Unit else None, 'source_id': p.id()})
        if not e.ObjectPlacement:
            issues.append({'id': e.id(), 'issue': 'missing_placement'})
        rows.append({'id': e.id(), 'global_id': e.GlobalId, 'type': e.is_a(), 'name': e.Name,
            'container_id': container.id() if container else None, 'properties': props})
    return {'format': 'IFC', 'version': doc.schema, 'parser': 'ifcopenshell '+ifcopenshell.version,
        'length_scale_to_m': scale, 'counts': dict(Counter(r['type'] for r in rows)),
        'objects': rows, 'issues': issues, 'limitations': [
            '提取IfcProduct类别和声明的空间包含关系；不是几何碰撞、邻接或承重分析。',
            '仅读取实例上的单值属性；类型继承、复杂属性、工程量与几何实体尚未计算。',
            '属性保留原始值、类型和显式单位；不默认采用长度单位换算全部属性。缺单位不猜测。',
            '缺少位置只报告缺口；读取成功不等于IFC完整性或工程合规认证。']}


def parse(path):
    path = Path(path)
    if not 0 < path.stat().st_size <= 10*1024*1024:
        raise ValueError('Supported file size is 1 byte..10 MiB')
    if path.suffix.lower() == '.dxf':
        return parse_dxf(path)
    if path.suffix.lower() == '.ifc':
        return parse_ifc(path)
    raise ValueError('Unsupported format; DWG conversion and OCR are not implemented')


if __name__ == '__main__':
    try:
        result = json.dumps(parse(sys.argv[1]), ensure_ascii=False, allow_nan=False)
        if len(result.encode('utf-8')) > 8*1024*1024:
            raise ValueError('Parsed output limit exceeded')
        Path(sys.argv[2]).write_text(result, encoding='utf-8')
    except Exception as exc:
        # Avoid printing source content or native-library diagnostics to clients.
        Path(sys.argv[2]).write_text(json.dumps({'error': type(exc).__name__, 'message': str(exc)[:300]}), encoding='utf-8')
        sys.exit(1)
