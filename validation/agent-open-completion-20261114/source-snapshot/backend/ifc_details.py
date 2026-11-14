"""Source-linked IFC declarations. Declared quantities are not measured quantities."""
import math
from collections import Counter

from ifcopenshell.util.unit import get_prefix_multiplier

QUANTITIES = {
    'IfcQuantityLength': ('LengthValue', 'LENGTHUNIT', 'm'),
    'IfcQuantityArea': ('AreaValue', 'AREAUNIT', 'm2'),
    'IfcQuantityVolume': ('VolumeValue', 'VOLUMEUNIT', 'm3'),
    'IfcQuantityWeight': ('WeightValue', 'MASSUNIT', 'kg'),
    'IfcQuantityTime': ('TimeValue', 'TIMEUNIT', 's'),
    'IfcQuantityCount': ('CountValue', None, 'count'),
}
SI_NAMES = {'LENGTHUNIT': ('METRE', 1, 1.), 'AREAUNIT': ('SQUARE_METRE', 2, 1.),
            'VOLUMEUNIT': ('CUBIC_METRE', 3, 1.), 'MASSUNIT': ('GRAM', 1, .001),
            'TIMEUNIT': ('SECOND', 1, 1.)}


def unit_scale(unit, expected, seen=()):
    """Reject unknown/offset/cyclic units; no default scale of one."""
    if unit.id() in seen or len(seen) >= 12:
        raise ValueError('cyclic_or_deep_unit')
    if getattr(unit, 'UnitType', None) != expected:
        raise ValueError('unit_dimension_mismatch')
    if unit.is_a('IfcSIUnit'):
        name, power, base = SI_NAMES[expected]
        if unit.Name != name:
            raise ValueError('unit_name_mismatch')
        scale = get_prefix_multiplier(unit.Prefix)**power * base
    elif unit.is_a('IfcConversionBasedUnit') and not unit.is_a('IfcConversionBasedUnitWithOffset'):
        dimensions = {'LENGTHUNIT': (1,0,0,0,0,0,0), 'AREAUNIT': (2,0,0,0,0,0,0),
                      'VOLUMEUNIT': (3,0,0,0,0,0,0), 'MASSUNIT': (0,1,0,0,0,0,0),
                      'TIMEUNIT': (0,0,1,0,0,0,0)}
        if tuple(unit.Dimensions) != dimensions[expected]:
            raise ValueError('unit_exponents_mismatch')
        factor = unit.ConversionFactor
        scale = float(factor.ValueComponent.wrappedValue) * unit_scale(factor.UnitComponent, expected, (*seen, unit.id()))
    else:
        raise ValueError('unsupported_unit')
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError('invalid_unit_scale')
    return scale


def project_units(project):
    groups = {}
    for unit in project.UnitsInContext.Units if project.UnitsInContext else ():
        kind = getattr(unit, 'UnitType', None)
        if kind in SI_NAMES:
            groups.setdefault(kind, []).append(unit)
    return groups


def spatial_relations(element):
    rows = []
    for rel in (*getattr(element, 'ContainedInStructure', ()), *getattr(element, 'Decomposes', ()), *getattr(element, 'Nests', ())):
        if rel.is_a('IfcRelContainedInSpatialStructure'):
            parent = rel.RelatingStructure
        elif rel.is_a('IfcRelAggregates') or rel.is_a('IfcRelNests'):
            parent = rel.RelatingObject
        else:
            continue
        if not any(r['relation_id'] == rel.id() for r in rows):
            rows.append({'relation_id': rel.id(), 'relation_type': rel.is_a(), 'parent_id': parent.id(),
                         'parent_type': parent.is_a(), 'parent_name': parent.Name})
    return rows


def normalized_quantity(q, units):
    spec = QUANTITIES.get(q.is_a())
    result = {'value_si': None, 'si_unit': None, 'unit_source': None, 'unit_id': None}
    if spec is None:
        return {**result, 'status': 'unsupported_quantity'}
    field, kind, symbol = spec
    value = getattr(q, field)
    result.update(value=value, value_type=q.is_a(), si_unit=symbol)
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
        return {**result, 'status': 'invalid_quantity_value'}
    if kind is None:
        if q.Unit:
            return {**result, 'status': 'unsupported_count_unit'}
        return {**result, 'value_si': value, 'unit_source': 'dimensionless_count', 'status': 'declared_normalized'}
    if q.Unit:
        unit = q.Unit
        result['unit_source'] = 'explicit'
    else:
        candidates = units.get(kind, [])
        if len(candidates) != 1:
            return {**result, 'status': 'missing_unit' if not candidates else 'conflicting_project_units'}
        unit = candidates[0]
        result['unit_source'] = 'project'
    result.update(unit_id=unit.id(), unit_definition=str(unit))
    try:
        scale = unit_scale(unit, kind)
        converted = value * scale
        if not math.isfinite(converted):
            raise ValueError('quantity_overflow')
    except (ValueError, TypeError, OverflowError, KeyError) as exc:
        return {**result, 'status': str(exc)}
    return {**result, 'value_si': converted, 'scale_to_si': scale, 'status': 'declared_normalized'}


def declarations(element, units):
    """Preserve each relation and duplicate; mark overrides without erasing origin."""
    types, sets, issues = [], [], []
    rels = list(getattr(element, 'IsDefinedBy', ())) + list(getattr(element, 'IsTypedBy', ()))
    seen_rels = set()
    for rel in rels:
        if rel.id() in seen_rels:
            continue
        seen_rels.add(rel.id())
        if rel.is_a('IfcRelDefinesByType'):
            t = rel.RelatingType
            types.append({'id': t.id(), 'global_id': t.GlobalId, 'name': t.Name, 'type': t.is_a(), 'relation_id': rel.id()})
            for pset in t.HasPropertySets or ():
                sets.append((pset, 'type', t.id(), rel.id()))
        elif rel.is_a('IfcRelDefinesByProperties'):
            definition = rel.RelatingPropertyDefinition
            for pset in definition if isinstance(definition, tuple) else (definition,):
                sets.append((pset, 'instance', element.id(), rel.id()))
    if len(types) > 1:
        issues.append('multiple_type_assignments')
    props, quantities = [], []
    visited = 0

    def walk(item, pset, scope, owner, relation, path, stack):
        nonlocal visited
        visited += 1
        if visited > 2000 or len(stack) >= 12:
            raise ValueError('IFC property budget exceeded')
        if item.id() in stack:
            raise ValueError('Cyclic IFC property definition')
        row = {'set': pset.Name, 'set_id': pset.id(), 'name': item.Name,
               'source_id': item.id(), 'scope': scope, 'owner_id': owner, 'relation_id': relation,
               'path': [*path, item.Name], 'source_kind': 'model_declaration'}
        if item.is_a('IfcComplexProperty') or item.is_a('IfcPhysicalComplexQuantity'):
            children = item.HasProperties if item.is_a('IfcComplexProperty') else item.HasQuantities
            for child in children:
                walk(child, pset, scope, owner, relation, row['path'], (*stack, item.id()))
        elif item.is_a('IfcPhysicalSimpleQuantity'):
            quantities.append({**row, 'method_of_measurement': getattr(pset, 'MethodOfMeasurement', None),
                               'formula': getattr(item, 'Formula', None), **normalized_quantity(item, units)})
        elif item.is_a('IfcPropertySingleValue'):
            value = item.NominalValue
            props.append({**row, 'value': value.wrappedValue if value is not None else None,
                          'value_type': value.is_a() if value is not None else None,
                          'explicit_unit': str(item.Unit) if item.Unit else None, 'status': 'declared_raw'})
        else:
            props.append({**row, 'value': None, 'value_type': item.is_a(), 'status': 'unsupported_property'})

    for pset, scope, owner, relation in sets:
        if pset.is_a('IfcPropertySet'):
            items = pset.HasProperties
        elif pset.is_a('IfcElementQuantity'):
            items = pset.Quantities
        else:
            issues.append('unsupported_property_definition:' + str(pset.id()))
            continue
        for item in items:
            walk(item, pset, scope, owner, relation, [], ())
    for rows in (props, quantities):
        def key(row):
            return row['set'], tuple(row['path'])
        instances = Counter(key(r) for r in rows if r['scope'] == 'instance')
        inherited = Counter(key(r) for r in rows if r['scope'] == 'type')
        for row in rows:
            k = key(row)
            if instances[k] > 1 or (not instances[k] and (inherited[k] > 1 or len(types) > 1)):
                row['selection'] = 'ambiguous'
            elif row['scope'] == 'type' and instances[k]:
                row['selection'] = 'overridden_by_instance'
            else:
                row['selection'] = 'effective_declaration'
    spatial = spatial_relations(element)
    if len({r['parent_id'] for r in spatial}) > 1:
        issues.append('multiple_spatial_parents')
    return {'types': types, 'properties': props, 'quantities': quantities, 'declaration_issues': issues,
            'spatial_relations': spatial}



def material_declarations(element, units):
    """Preserve IFC material bindings; no name-based classification or volume allocation."""
    count = 0

    def length(value):
        result = {'raw': value, 'value_m': None, 'unit_id': None, 'status': 'missing_unit'}
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
            return {**result, 'status': 'invalid_length'}
        candidates = units.get('LENGTHUNIT', [])
        if len(candidates) != 1:
            return {**result, 'status': 'conflicting_project_units' if candidates else 'missing_unit'}
        unit = candidates[0]
        result['unit_id'] = unit.id()
        try:
            converted = value * unit_scale(unit, 'LENGTHUNIT')
            if not math.isfinite(converted):
                raise ValueError('length_overflow')
        except (ValueError, TypeError, OverflowError, KeyError) as exc:
            return {**result, 'status': str(exc)}
        return {**result, 'value_m': converted, 'status': 'declared_normalized'}

    def describe(node, stack=()):
        nonlocal count
        count += 1
        if count > 2000 or len(stack) >= 12:
            raise ValueError('IFC material traversal budget exceeded')
        if node is None:
            return {'status': 'missing_material', 'id': None, 'type': None}
        if node.id() in stack:
            raise ValueError('Cyclic IFC material definition')
        row = {'id': node.id(), 'type': node.is_a(), 'name': getattr(node, 'Name', None),
               'source_kind': 'model_declaration', 'status': 'declared'}
        path = (*stack, node.id())
        if node.is_a('IfcMaterial'):
            row.update(category=getattr(node, 'Category', None), description=getattr(node, 'Description', None))
        elif node.is_a('IfcMaterialLayerSetUsage'):
            row.update(layer_set=describe(node.ForLayerSet, path), direction=node.LayerSetDirection,
                       sense=node.DirectionSense, offset_raw=node.OffsetFromReferenceLine,
                       reference_extent_raw=getattr(node, 'ReferenceExtent', None))
        elif node.is_a('IfcMaterialLayerSet'):
            row.update(name=node.LayerSetName, layers=[describe(x, path) for x in node.MaterialLayers])
        elif node.is_a('IfcMaterialLayer'):
            row.update(material=describe(node.Material, path), thickness=length(node.LayerThickness),
                       is_ventilated=node.IsVentilated)
            if node.is_a('IfcMaterialLayerWithOffsets'):
                row.update(status='offset_geometry_not_measured', offset_direction=node.OffsetDirection,
                           offset_values_raw=list(node.OffsetValues or ()))
        elif node.is_a('IfcMaterialList'):
            row.update(materials=[describe(x, path) for x in node.Materials],
                       proportions_status='not_declared')
        elif node.is_a('IfcMaterialConstituentSet'):
            row['constituents'] = [describe(x, path) for x in node.MaterialConstituents or ()]
        elif node.is_a('IfcMaterialConstituent'):
            fraction = node.Fraction
            valid = fraction is not None and math.isfinite(fraction) and 0 <= fraction <= 1
            row.update(material=describe(node.Material, path), fraction_raw=fraction,
                       fraction_status='declared_unverified' if valid else 'missing_or_invalid_fraction')
        elif node.is_a('IfcMaterialProfileSetUsage'):
            row.update(profile_set=describe(node.ForProfileSet, path), cardinal_point=node.CardinalPoint,
                       reference_extent_raw=node.ReferenceExtent)
        elif node.is_a('IfcMaterialProfileSet'):
            row['profiles'] = [describe(x, path) for x in node.MaterialProfiles]
            row['composite_profile_id'] = node.CompositeProfile.id() if node.CompositeProfile else None
        elif node.is_a('IfcMaterialProfile'):
            row.update(material=describe(node.Material, path),
                       profile={'id': node.Profile.id(), 'type': node.Profile.is_a()} if node.Profile else None,
                       status='profile_geometry_not_measured')
        else:
            row['status'] = 'unsupported_material_definition'
        return row

    types = {}
    for rel in (*getattr(element, 'IsDefinedBy', ()), *getattr(element, 'IsTypedBy', ())):
        if rel.is_a('IfcRelDefinesByType'):
            types[rel.RelatingType.id()] = rel.RelatingType
    owners = [(element, 'instance'), *((t, 'type') for t in types.values())]
    rows, seen = [], set()
    for owner, scope in owners:
        for rel in getattr(owner, 'HasAssociations', ()):
            if not rel.is_a('IfcRelAssociatesMaterial') or (owner.id(), rel.id()) in seen:
                continue
            seen.add((owner.id(), rel.id()))
            rows.append({'relation_id': rel.id(), 'owner_id': owner.id(), 'scope': scope,
                         'material': describe(rel.RelatingMaterial)})
    direct = [r for r in rows if r['scope'] == 'instance']
    active = direct or rows
    ambiguous = len(active) > 1 or (not direct and len(types) > 1)
    for row in rows:
        row['selection'] = ('overridden_by_instance' if direct and row['scope'] == 'type' else
                            'ambiguous' if ambiguous else 'effective_declaration')
    return {'material_assignment': {'status': 'ambiguous' if ambiguous else 'declared' if active else 'missing',
            'associations': rows, 'quantity_status': 'not_measured',
            'notice': '材料关联与层厚来自模型声明；未验证层几何、洞口扣减、材料性能或计量规则，不能按厚度比例直接分配构件体积。'}}
