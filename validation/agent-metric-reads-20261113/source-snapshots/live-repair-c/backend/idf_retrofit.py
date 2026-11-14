"""Lossless IDF 9.0 token edits for explicitly selected ordinary opaque surfaces.

Only construction-reference token spans are replaced. Original objects, comments,
geometry, schedules and HVAC remain byte-identical outside those spans.
"""
from dataclasses import dataclass
import hashlib
import re
from . import core

MAX_BYTES = 2*1024**2


@dataclass(frozen=True)
class Token:
    value: str
    start: int
    end: int


def tokens(raw):
    if not raw or len(raw)>MAX_BYTES:
        raise core.ValidationError('Model must be nonempty UTF-8 IDF up to 2 MiB')
    try:text=raw.decode('utf-8')
    except UnicodeError as exc:raise core.ValidationError('Model must use explicit UTF-8 encoding') from exc
    if any(ord(c)<32 and c not in '\r\n\t' for c in text):
        raise core.ValidationError('Control characters in IDF')
    masked=re.sub(r'![^\r\n]*',lambda m:' '*len(m[0]),text)
    if masked.startswith('\ufeff'):masked=' '+masked[1:]
    if any(c in masked for c in ['"',"'",'#','\ufeff']):
        raise core.ValidationError('Quoted fields/macros need a separate parser; no guessed edits')
    objects=[];fields=[];start=0
    for delimiter in re.finditer('[,;]',masked):
        chunk=masked[start:delimiter.start()]
        value=chunk.strip();begin=start+len(chunk)-len(chunk.lstrip())
        if len(value)>2000 or any(c in value for c in '\r\n\t'):
            raise core.ValidationError('Unsupported multiline or oversized IDF field')
        fields.append(Token(value,begin,begin+len(value)))
        if len(fields)>10000:raise core.ValidationError('IDF field budget exceeded')
        if delimiter[0]==';':
            if not fields[0].value:raise core.ValidationError('Empty IDF object')
            objects.append(fields);fields=[]
            if len(objects)>100000:raise core.ValidationError('IDF object budget exceeded')
        start=delimiter.end()
    if fields or masked[start:].strip():raise core.ValidationError('Unterminated IDF object')
    versions=[o for o in objects if o[0].value.casefold()=='version']
    if len(versions)!=1 or len(versions[0])!=2 or not re.fullmatch(r'9\.0(?:\.[0-9]+)?',versions[0][1].value):
        raise core.ValidationError('Only IDF 9.0 is supported for model derivation')
    return text,objects


def inspect(raw):
    text,objects=tokens(raw)
    constructions={};materials={};surfaces={};special=set();controls=[];movable=set()
    for o in objects:
        kind=o[0].value.casefold()
        if kind.startswith('materialproperty:') and len(o)>1:
            special.add(o[1].value.casefold())
        if kind=='surfaceproperty:heattransferalgorithm:construction' and len(o)>3:
            special.add(o[3].value.casefold())
        if (kind.startswith(('pythonplugin:','externalinterface')) or kind=='energymanagementsystem:constructionindexvariable'
            or kind=='energymanagementsystem:actuator' and any('constructionstate' in t.value.casefold().replace(' ','') for t in o)):
            controls.append(o[0].value)
        if kind=='surfacecontrol:movableinsulation' and len(o)>2:movable.add(o[2].value.casefold())
        group=constructions if kind=='construction' else materials if kind=='material' or kind.startswith(('material:','windowmaterial:')) else surfaces if kind=='buildingsurface:detailed' else None
        if group is None:continue
        if len(o)<2 or not o[1].value or o[1].value.casefold() in group:
            raise core.ValidationError('Missing/duplicate IDF object name: '+kind)
        group[o[1].value.casefold()]=o
    result=[]
    for name,o in surfaces.items():
        if len(o)<11:raise core.ValidationError('Incomplete BuildingSurface:Detailed')
        construction=constructions.get(o[3].value.casefold())
        reasons=[]
        if o[2].value.casefold() not in {'wall','roof','floor'} or o[5].value.casefold()!='outdoors':
            reasons.append('only_outdoor_opaque_surfaces')
        if controls:reasons.append('dynamic_construction_or_external_control')
        if name in movable:reasons.append('movable_insulation')
        if construction is None or not 3<=len(construction)<=12:
            reasons.append('unsupported_construction')
            layers=[]
        else:
            layers=[t.value for t in construction[2:]]
            if any(layer.casefold() not in materials or materials[layer.casefold()][0].value.casefold() not in {'material','material:nomass','material:airgap'} for layer in layers):
                reasons.append('unsupported_original_material')
            if construction[1].value.casefold() in special or any(n.casefold() in special for n in layers):
                reasons.append('special_material_or_construction_properties')
        result.append({'name':o[1].value,'surface_type':o[2].value,'construction':o[3].value,'zone':o[4].value,
                       'boundary':o[5].value,'original_layers_outside_to_inside':layers,'eligible':not reasons,'reasons':reasons})
    if len(result)>2000:raise core.ValidationError('Model surface budget exceeded')
    return {'text':text,'objects':objects,'surfaces':surfaces,'materials':materials,'constructions':constructions,'catalog':result}


def derive(raw,assignments,thermal_records,namespace):
    model=inspect(raw);by_name={s['name'].casefold():s for s in model['catalog']}
    occupied=set(model['materials'])|set(model['constructions'])
    modifications=[];new_objects=[];groups=[];selected=set()
    for index,(assignment,record) in enumerate(zip(assignments,thermal_records,strict=True)):
        rows=record['result']['layers']
        if len(rows)>10 or len(rows)!=len(assignment.properties):
            raise core.ValidationError('Each thermal layer requires declared properties; EnergyPlus Construction supports at most 10 layers')
        order=list(range(len(rows)))
        if assignment.layer_order=='inside_to_outside':order.reverse()
        construction='VRA_'+namespace+'_C'+str(index+1)
        material_names=[];material_rows=[]
        for layer_index in order:
            layer=rows[layer_index];properties=assignment.properties[layer_index]
            name='VRA_'+namespace+'_C'+str(index+1)+'_L'+str(layer_index+1)
            if name.casefold() in occupied:raise core.ValidationError('Generated material name collision')
            occupied.add(name.casefold());material_names.append(name)
            values=[layer['thickness_m'],layer['effective_conductivity_w_mk'],properties.density_kg_m3,
                    properties.specific_heat_j_kg_k,properties.thermal_absorptance,properties.solar_absorptance,properties.visible_absorptance]
            if any(v is None for v in values):raise core.ValidationError('Missing material properties')
            new_objects.append('Material, '+name+', '+properties.roughness+', '+', '.join(format(v,'.17g') for v in values)+';')
            material_rows.append({'idf_name':name,'thermal_layer_index':layer_index,'thermal_layer_name':layer['name'],
                                  'thickness_m':values[0],'effective_conductivity_w_mk':values[1],**properties.model_dump()})
        if construction.casefold() in occupied:raise core.ValidationError('Generated construction name collision')
        occupied.add(construction.casefold())
        new_objects.append('Construction, '+construction+', '+', '.join(material_names)+';')
        names=[]
        for name in assignment.surface_names:
            key=name.casefold()
            if key in selected:raise core.ValidationError('A surface may only be assigned once')
            selected.add(key)
            surface=by_name.get(key)
            if surface is None or not surface['eligible']:
                raise core.ValidationError('Surface missing or unsupported: '+name)
            token=model['surfaces'][key][3]
            modifications.append({'surface_name':surface['name'],'old_construction':token.value,'new_construction':construction,
                                  'start':token.start,'end':token.end})
            names.append(surface['name'])
        groups.append({'thermal_id':record['thermal_id'],'construction':construction,'surfaces':names,
                       'layers_outside_to_inside':material_rows,'rsi_rse_written_as_material':False})
    if not modifications or len(modifications)>1000:raise core.ValidationError('Select 1..1000 distinct surfaces')
    text=model['text'];parts=[];previous=0
    for item in sorted(modifications,key=lambda m:m['start']):
        if item['start']<previous or text[item['start']:item['end']]!=item['old_construction']:
            raise core.ValidationError('Source token span mismatch')
        parts.extend([text[previous:item['start']],item['new_construction']]);previous=item['end']
    parts.append(text[previous:])
    content=''.join(parts)+'\n\n! VRA derived ordinary-material scenario; original objects preserved.\n'+'\n'.join(new_objects)+'\n'
    data=content.encode('utf-8')
    if len(data)>MAX_BYTES:raise core.ValidationError('Derived model exceeds 2 MiB')
    # Validate syntax and names after splicing; do not silently repair anything.
    inspect(data)
    return data,{'source_sha256':hashlib.sha256(raw).hexdigest(),'derived_sha256':hashlib.sha256(data).hexdigest(),
                 'changed_reference_count':len(modifications),'added_object_count':len(new_objects),'changes':modifications,'assignments':groups,
                 'unchanged_bytes_outside_reference_spans':True,'geometry_schedules_hvac_unchanged':True}
