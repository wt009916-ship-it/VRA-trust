"""Native EnergyPlus 9.0 PTHP templates, expanded by its own ExpandObjects.

Fixed nameplate capacities/flows; native single-speed curves and defrost defaults
are scenario assumptions, not measured manufacturer performance curves.
"""
import re
import shutil
import subprocess


def objects(text):
    return [[p.strip() for p in chunk.split(',')] for chunk in re.sub(r'!.*', '', text).split(';') if chunk.strip()]


def expand_fixed(text, engine, directory):
    """Expand native curves/connections, then bind sizing placeholders explicitly.

    EnergyPlus 9 ExpandObjects puts user flow into Sizing:Zone but leaves the
    actual equipment autosized. No design days/hidden sizing are invented here.
    Only the compiler's constrained PTHP template is accepted by this binder.
    """
    from . import core
    parsed = objects(text)
    templates = [o for o in parsed if o[0].lower().startswith('hvactemplate:')]
    if not templates or any(o[0].lower() != 'hvactemplate:zone:pthp' for o in templates):
        raise core.ValidationError('Fixed PTHP expansion accepts only Zone:PTHP templates')
    (directory/'in.idf').write_text(text, encoding='utf-8')
    shutil.copy2(engine.parent/'Energy+.idd', directory/'Energy+.idd')
    executable = engine.parent/('ExpandObjects.exe' if engine.suffix == '.exe' else 'ExpandObjects')
    cp = subprocess.run([str(executable)], cwd=directory, capture_output=True, timeout=30)
    (directory/'expansion.log').write_bytes(cp.stdout+cp.stderr)
    expanded = directory/'expanded.idf'
    if cp.returncode or not expanded.is_file():
        raise core.ValidationError('Native HVAC template expansion failed; see expansion.log')
    rows = objects(expanded.read_text(encoding='utf-8', errors='replace'))
    changes = []

    def bind(kind, name, values):
        matches = [r for r in rows if r[0].lower() == kind.lower() and r[1].lower() == name.lower()]
        if len(matches) != 1:
            raise core.ValidationError('Expanded HVAC object missing/ambiguous: '+name)
        row = matches[0]
        for field, value in values.items():
            changes.append(dict(object=kind, name=name, field_index=field-1, before=row[field], after=str(value)))
            row[field] = str(value)

    for t in templates:
        name, flow = t[1], float(t[3])
        zones = [r for r in parsed if r[0].lower() == 'zone' and r[1] == name]
        people = [r for r in parsed if r[0].lower() == 'people' and r[2] == name]
        if len(zones) != 1 or len(people) != 1 or people[0][4].lower() != 'area/person':
            raise core.ValidationError('Fixed PTHP needs explicit unique Zone floor area and Area/Person People')
        area = float(zones[0][10])
        oa = area/float(people[0][7])*float(t[9]) + area*float(t[10]) + float(t[11])
        if oa > flow:
            raise core.ValidationError('Design outdoor airflow exceeds PTHP supply airflow: '+name)
        prefix = name+' PTHP'
        bind('ZoneHVAC:PackagedTerminalHeatPump', prefix,
             {7: flow, 8: flow, 9: flow, 10: oa, 11: oa, 12: oa, 23: 50})
        bind('Fan:OnOff', prefix+' Supply Fan', {5: flow})
        lockouts = [r for r in parsed if r[0] == 'Schedule:Constant' and r[1] == name+'CoolingLockout']
        if len(lockouts) != 1:
            raise core.ValidationError('Missing explicit cooling compressor temperature limit: '+name)
        bind('Coil:Cooling:DX:SingleSpeed', prefix+' Cooling Coil', {6: flow, 15: float(lockouts[0][3])})
        bind('Coil:Heating:DX:SingleSpeed', prefix+' Heating Coil', {5: flow, 23: 0})
    # The source template and native expansion remain archived separately.
    if any(v.lower() == 'autosize' for row in rows for v in row):
        raise core.ValidationError('Unbound autosize field in fixed-capacity PTHP expansion')
    result = '\n\n'.join(',\n  '.join(r)+';' for r in rows)
    (directory/'fixed.idf').write_text(result, encoding='utf-8')
    core.write_json(directory/'sizing-bindings.json', changes)
    return directory/'fixed.idf'


def template(name, area, thermal):
    p = thermal["heat_pump"]
    op = thermal["operation"]
    flow = area * p["airflow_l_s_m2"] / 1000
    # Field order verified against EnergyPlus 9.0 Energy+.idd, not newer schemas.
    fields = [name, "", flow, flow, flow, "", "", "Sum",
              op["outdoor_air_l_s_person"] / 1000, op["outdoor_air_l_s_m2"] / 1000, 0,
              "Always", "Occupied", "DrawThrough", p["fan_total_efficiency"],
              p["fan_pressure_pa"], p["fan_motor_efficiency"], "SingleSpeedDX", "Always",
              area * p["cooling_w_m2"], p["sensible_heat_ratio"], p["cooling_cop"],
              "SingleSpeedDXHeatPump", "Always", area * p["heating_w_m2"], p["heating_cop"],
              p["minimum_outdoor_c"], 5, "ReverseCycle", "OnDemand", "",
              "Electric", "Always", area * p["supplemental_w_m2"], 5, "", "", "",
              "SupplyAirTemperature", 14, "", "SupplyAirTemperature", 50, "", "", "",
              "None", "", 0, "None"]
    return (f'Schedule:Constant, {name}CoolingLockout, Temperature, {p["minimum_cooling_outdoor_c"]};\n'
            + "HVACTemplate:Zone:PTHP,\n  " + ",\n  ".join(str(v) for v in fields) + ";\n")
