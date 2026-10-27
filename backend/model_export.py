"""Deterministic IFC4 space export and EnergyPlus 9.0 ideal-load model compiler."""
from functools import lru_cache
import copy
import json

from . import core, model_geometry, honeybee_bridge, thermal_mesh, heat_pump, solid_geometry, equipment_inputs, source_windows, column_mass

COMPILER_VERSION = "reviewed-polyhedral-source-window-pthp-6"
LIMITATIONS = [
    "空间保留水平分段或闭合多面体斜面；构件重建为待复核的推导候选，不表示完整施工 BIM。",
    "IFC 未配对内部及未知边界默认拒绝；仅显式 assumed_scenario 可按绝热计算，并保留逐面来源。该情景不等于完整建筑热模型。",
    "理想负荷模式的 DistrictHeating/DistrictCooling 是冷热需求；PTHP 模式为逐房间定容单速空气源热泵、风机、电辅热的原生模拟，不含水系统和管网。两种口径不能直接排名。",
    "PTHP 可按空间导入有来源的绝对铭牌及10项容量/EIR/流量/部分负荷曲线；缺曲线时须显式采用原生参考曲线，不能称为厂家变工况实测。除霜仍为官方模板假设；不含设备热回收、水系统或VRF自动编译。",
    "有分层构造时按材料厚度、导热、密度与比热建模；未提供构造层时按 U 值生成无热容层。未建相变潜热或温变物性。开窗可选择显式窗墙比或IFC源窗/窗洞投影；投影不等于净玻璃，U/SHGC仍须依据。",
    "可显式填写工作日/周末 24 小时使用率、非使用温度、新风和显潜热回收；无运行档案时保持旧每日时段。未配置法定假日日历和湿度控制；土温全年固定。",
    "本结果用于已声明参数的方案情景，未校准、未签署，不等同于建筑节能合规验收。",
]


def compiler_hash():
    return core.hash_json({"export": core.sha(__file__), "heat_pump": core.sha(heat_pump.__file__), "geometry": core.sha(model_geometry.__file__),
                           "thermal_mesh": core.sha(thermal_mesh.__file__), "honeybee_bridge": core.sha(honeybee_bridge.__file__),
                           'solid_geometry': core.sha(solid_geometry.__file__), 'equipment_inputs': core.sha(equipment_inputs.__file__),
                           'source_windows': core.sha(source_windows.__file__),
                           'column_mass': core.sha(column_mass.__file__),
                           "libraries": honeybee_bridge.library_versions()})


def geometry(model, *, return_report=False):
    output, report = copy.deepcopy(_geometry_cached(json.dumps(model, sort_keys=True), compiler_hash()))
    return (output, report) if return_report else output


@lru_cache(maxsize=2)
def _geometry_cached(model_json, compiler):
    model = json.loads(model_json)
    derived, column_report = column_mass.reduce(model)
    derived, _ = model_geometry.thermal_geometry_model(derived)
    surfaces, overlay = model_geometry.geometry(derived, return_report=True)
    if (model.get('thermal') or {}).get('window_geometry') == 'source':
        surfaces = source_windows.partition_parents(model, surfaces)
    output, report = thermal_mesh.conform(surfaces, return_report=True,
        preserve_window_walls=(model.get('thermal') or {}).get('window_geometry') == 'source')
    report.update(overlay)
    report['column_mass_reduction'] = column_report
    return output, report


@lru_cache(maxsize=2)
def _audit_cached(model_json, compiler):
    model = json.loads(model_json)
    surfaces, _ = _geometry_cached(model_json, compiler)
    return honeybee_bridge.audit(model, surfaces)


def geometry_audit(model):
    return copy.deepcopy(_audit_cached(json.dumps(model, sort_keys=True), compiler_hash()))


def idf(model):
    t = model.get("thermal")
    if not t:
        raise core.ValidationError("需完整填写热工、内部负荷、时段与参数来源")
    surfaces = geometry(model)
    independent = geometry_audit(model)
    if not independent["passed"]:
        raise core.ValidationError("几何与引擎兼容性校验失败：" + "; ".join(i["message"] for i in independent["issues"])[:1500])
    used_constructions = {surface["construction"] for surface in surfaces}
    objects = ["! VRA compiler " + COMPILER_VERSION, "! HVAC scope: " + scope(model),
               "! Geometry normalization tolerance (m): " + str(t.get("geometry_tolerance_m", 0)),
               "! Unpaired IFC boundary policy: " + t.get("ifc_unpaired_policy", "reject")]

    def obj(kind, *fields):
        objects.append(kind + ",\n  " + ",\n  ".join(str(v) for v in fields) + ";\n")

    obj("Version", "9.0")
    obj("SimulationControl", "No", "No", "No", "No", "Yes")
    obj("Building", "VRA", t["north_deg"], "Suburbs", .04, .4, "FullExterior", 25, 6)
    obj("Timestep", 6)
    obj("RunPeriod", "Annual", 1, 1, "", 12, 31, "", "Monday", "Yes", "Yes", "No", "Yes", "Yes")
    obj("Site:GroundTemperature:BuildingSurface", *([t["ground_temperature_c"]]*12))
    obj("GlobalGeometryRules", "UpperLeftCorner", "Counterclockwise", "World")
    obj("ScheduleTypeLimits", "Fraction", 0, 1, "Continuous")
    if not t.get("operation"):
        obj("ScheduleTypeLimits", "Temperature", -60, 100, "Continuous", "Temperature")
    obj("ScheduleTypeLimits", "Control", 0, 4, "Discrete")
    obj("ScheduleTypeLimits", "Any")
    for name, limit, value in [("Always", "Fraction", 1), ("Control4", "Control", 4),
                               ("Heat", "Temperature", t["heating_c"]), ("Cool", "Temperature", t["cooling_c"]),
                               ("Activity", "Any", 120)]:
        if not t.get("operation") or name not in {"Heat", "Cool"}:
            obj("Schedule:Constant", name, limit, value)
    fields = ["Occupied", "Fraction", "Through: 12/31", "For: AllDays"]
    if t["active_start"]:
        fields += [f'Until: {t["active_start"]:02d}:00', 0]
    fields += [f'Until: {t["active_end"]:02d}:00', 1]
    if t["active_end"] < 24:
        fields += ["Until: 24:00", 0]
    if t.get("operation"):
        objects.extend(honeybee_bridge.schedules(t))
    else:
        obj("Schedule:Compact", *fields)
    for name, key, film in [("Wall", "wall_u", .17), ("Roof", "roof_u", .14), ("Floor", "floor_u", .21)]:
        layers = t.get("constructions", {}).get(name.lower(), [])
        if layers:
            names = []
            for i, layer in enumerate(layers):
                layer_name = name + "_L" + str(i+1)
                names.append(layer_name)
                obj("Material", layer_name, "MediumRough", layer["thickness_m"], layer["conductivity_w_mk"],
                    layer["density_kg_m3"], layer["specific_heat_j_kgk"], .9, .7, .7)
            obj("Construction", name, *names)
            if name+"Reverse" in used_constructions:
                obj("Construction", name+"Reverse", *reversed(names))
        else:
            obj("Material:NoMass", name+"Layer", "MediumRough", 1/t[key]-film, .9, .7, .7)
            obj("Construction", name, name+"Layer")
            if name+"Reverse" in used_constructions:
                obj("Construction", name+"Reverse", name+"Layer")
    if t.get('window_geometry') == 'source' or (t["window_wall_ratio"] and any(s["kind"] == "Wall" and s["boundary"] == "Outdoors" for s in surfaces)):
        obj("WindowMaterial:SimpleGlazingSystem", "Glass", t["window_u"], t["window_shgc"], .6)
        obj("Construction", "Window", "Glass")
    validated_volumes = {r["room_id"]: r["volume_m3"] for r in independent["rooms"]}
    _, geometry_report = geometry(model, return_report=True)
    column_by_zone = {r['room_id']: r for r in geometry_report['column_mass_reduction']}
    for r in model["rooms"]:
        name = r["id"]
        volume = model_geometry.room_volume(r)
        area = model_geometry.floor_area(r)
        zone_thermal = equipment_inputs.thermal_for_zone(model, r, area)
        height = 'autocalculate' if r.get('shell') or len(r.get('segments', [])) > 1 else r['height_m']
        obj("Zone", name, 0, 0, 0, 0, 1, 1, height, volume if name in column_by_zone else validated_volumes[name], area,
            "", "", "Yes" if r.get("include_floor_area", True) else "No")
        if name in column_by_zone:
            mass, material = column_by_zone[name], t['column_mass_material']
            obj('Material', name+'ColMassMat', 'MediumRough', mass['equivalent_thickness_m'],
                material['conductivity_w_mk'], material['density_kg_m3'], material['specific_heat_j_kgk'], .9, .7, .7)
            obj('Construction', name+'ColMass', name+'ColMassMat')
            obj('InternalMass', name+'Columns', name+'ColMass', name, mass['exposed_lateral_area_m2'])
        obj("ZoneInfiltration:DesignFlowRate", name+"Infil", name, "Always", "AirChanges/Hour",
            "", "", "", t["infiltration_ach"], 1, 0, 0, 0)
        if not r.get("conditioned", True):
            continue
        obj("People", name+"People", name, "Occupied", "Area/Person", "", "", t["people_m2_person"], .3, "autocalculate", "Activity")
        obj("Lights", name+"Lights", name, "Occupied", "Watts/Area", "", t["lights_w_m2"], "", 0, .5, .2, 0)
        obj("ElectricEquipment", name+"Equip", name, "Occupied", "Watts/Area", "", t["equipment_w_m2"], "", 0, .5, 0)
        obj("ThermostatSetpoint:DualSetpoint", name+"Set", "Heat", "Cool")
        obj("ZoneControl:Thermostat", name+"Thermostat", name, "Control4", "ThermostatSetpoint:DualSetpoint", name+"Set")
        if zone_thermal.get("heat_pump"):
            objects.append(heat_pump.template(name, area, zone_thermal))
            equipment = next((e for e in model.get('equipment', []) if e['zone_id'] == name), None)
            if equipment:
                objects.extend(equipment_inputs.curve_objects(equipment))
            continue
        obj("ZoneHVAC:EquipmentConnections", name, name+"Equipment", name+"Supply", "", name+"Air", name+"Return")
        obj("ZoneHVAC:EquipmentList", name+"Equipment", "SequentialLoad", "ZoneHVAC:IdealLoadsAirSystem", name+"Ideal", 1, 1)
        operation = t.get("operation")
        oa_name, recovery, sensible, latent = "", "None", 0, 0
        if operation:
            oa, oa_name = honeybee_bridge.outdoor_air(t, name)
            objects.append(oa)
            obj("OutdoorAir:Node", name+"Outdoor")
            sensible, latent = operation["sensible_recovery"], operation["latent_recovery"]
            recovery = "Enthalpy" if latent else "Sensible" if sensible else "None"
        obj("ZoneHVAC:IdealLoadsAirSystem", name+"Ideal", "Always" if operation else "Occupied", name+"Supply", "", "", 50, 13, .0156, .0077,
            "NoLimit", "", "", "NoLimit", "", "", "", "", "None", "", "None", oa_name, name+"Outdoor" if operation else "",
            "OccupancySchedule" if operation else "None", "NoEconomizer", recovery, sensible, latent)
    for s in surfaces:
        external = s["boundary"] == "Outdoors"
        obj("BuildingSurface:Detailed", s["name"], s["kind"], s["construction"], s["zone"],
            s["boundary"], s["other"], "SunExposed" if external else "NoSun",
            "WindExposed" if external else "NoWind", "autocalculate", len(s["points"]),
            *[round(v, 6) for p in s["points"] for v in p])
    # Honeybee splits concave facade apertures into engine-compatible polygons.
    hb = honeybee_bridge.geometry_model(model, surfaces)
    for face in hb.faces:
        for aperture in face.apertures:
            points = [list(p) for p in aperture.geometry.vertices]
            if len(points) > 4:
                raise core.ValidationError("窗多于四个顶点，不能交给当前 EnergyPlus；请拆分墙面")
            obj("FenestrationSurface:Detailed", aperture.identifier, "Window", "Window", face.identifier, "",
                "autocalculate", "", 1, len(points), *[round(v, 6) for p in points for v in p])
    obj("Output:Diagnostics", "DisplayExtraWarnings")
    obj("Output:SQLite", "SimpleAndTabular")
    obj("Output:Table:SummaryReports", "AllSummary")
    obj("OutputControl:Table:Style", "HTML", "JtoKWH")
    obj("Output:Variable", "*", "Zone Mean Air Temperature", "Hourly")
    if t.get("heat_pump") or model.get('equipment'):
        for variable in ("Heating Coil Electric Energy", "Cooling Coil Electric Energy", "Fan Electric Energy"):
            obj("Output:Variable", "*", variable, "Hourly")
    else:
        obj("Output:Variable", "*", "Zone Ideal Loads Supply Air Total Heating Energy", "Hourly")
        obj("Output:Variable", "*", "Zone Ideal Loads Supply Air Total Cooling Energy", "Hourly")
    return "\n".join(objects), surfaces


def scope(model):
    return "packaged_heat_pump_electricity" if (model.get("thermal") or {}).get("heat_pump") or model.get('equipment') else "ideal_thermal_loads"


def ifc(model):
    import ifcopenshell
    import ifcopenshell.api
    import numpy as np
    run = ifcopenshell.api.run
    doc = ifcopenshell.file(schema="IFC4")
    project = run("root.create_entity", doc, ifc_class="IfcProject", name=model["name"])
    run("unit.assign_unit", doc, length={"is_metric": True, "raw": "METERS"})
    context = run("context.add_context", doc, context_type="Model")
    body = run("context.add_context", doc, context_type="Model", context_identifier="Body",
               target_view="MODEL_VIEW", parent=context)
    site = run("root.create_entity", doc, ifc_class="IfcSite", name="Site")
    building = run("root.create_entity", doc, ifc_class="IfcBuilding", name=model["name"])
    run("aggregate.assign_object", doc, products=[site], relating_object=project)
    run("aggregate.assign_object", doc, products=[building], relating_object=site)
    for elevation in sorted({r["elevation_m"] for r in model["rooms"]}):
        story = run("root.create_entity", doc, ifc_class="IfcBuildingStorey", name=f"Z {elevation} m")
        story.Elevation = elevation
        run("aggregate.assign_object", doc, products=[story], relating_object=building)
        for room in [r for r in model["rooms"] if r["elevation_m"] == elevation]:
            space = run("root.create_entity", doc, ifc_class="IfcSpace", name=room["name"])
            run("aggregate.assign_object", doc, products=[space], relating_object=story)
            solids = []
            from shapely.geometry import Polygon
            from shapely.ops import unary_union
            layers = {}
            if room.get('shell'):
                faces = []
                for face in room['shell']:
                    points = [doc.createIfcCartesianPoint((float(x), float(y), float(z-elevation))) for x, y, z in face['points']]
                    loop = doc.createIfcPolyLoop(points)
                    faces.append(doc.createIfcFace([doc.createIfcFaceOuterBound(loop, True)]))
                solid = doc.createIfcFacetedBrep(doc.createIfcClosedShell(faces))
                rep = doc.createIfcShapeRepresentation(body, 'Body', 'Brep', [solid])
            else:
                for section in model_geometry.parts(room):
                    key = (section["elevation_m"], section["height_m"])
                    layers.setdefault(key, []).append(Polygon(section["polygon"], section.get("holes", [])))
                def curve_for(ring):
                    pts = [doc.createIfcCartesianPoint((float(x), float(y))) for x, y in list(ring.coords)[:-1]]
                    return doc.createIfcPolyline(pts + [pts[0]])
                for (bottom, height), footprints in layers.items():
                    for footprint in model_geometry.polygons(unary_union(footprints)):
                        curve = curve_for(footprint.exterior)
                        profile = (doc.createIfcArbitraryProfileDefWithVoids("AREA", None, curve,
                                   [curve_for(ring) for ring in footprint.interiors]) if footprint.interiors else
                                   doc.createIfcArbitraryClosedProfileDef("AREA", None, curve))
                        position = doc.createIfcAxis2Placement3D(doc.createIfcCartesianPoint(
                            (0., 0., float(bottom-elevation))), None, None)
                        solids.append(doc.createIfcExtrudedAreaSolid(profile, position,
                            doc.createIfcDirection((0., 0., 1.)), float(height)))
                solid = solids[0]
                for other in solids[1:]:
                    solid = doc.createIfcBooleanResult("UNION", solid, other)
                rep = doc.createIfcShapeRepresentation(body, "Body", "CSG" if len(solids) > 1 else "SweptSolid", [solid])
            run("geometry.assign_representation", doc, product=space, representation=rep)
            matrix = np.eye(4)
            matrix[2, 3] = elevation
            run("geometry.edit_object_placement", doc, product=space, matrix=matrix, is_si=True)
            pset = run("pset.add_pset", doc, product=space, name="VRA_Provenance")
            run("pset.edit_pset", doc, pset=pset, properties={"RoomId": room["id"], "Source": room["source_locator"],
                "ModelRevision": model.get("revision", 0), "Reviewed": model.get("reviewed", False),
                "Conditioned": room.get("conditioned"), "IncludedFloorArea": room.get("include_floor_area")})
            for opening in room.get('source_openings', []):
                window = run('root.create_entity', doc, ifc_class='IfcWindow', name='Projected source '+opening['source_id'])
                points = [doc.createIfcCartesianPoint((float(x), float(y), float(z-elevation))) for x, y, z in opening['points']]
                face = doc.createIfcFace([doc.createIfcFaceOuterBound(doc.createIfcPolyLoop(points), True)])
                surface = doc.createIfcFaceBasedSurfaceModel([doc.createIfcConnectedFaceSet([face])])
                rep = doc.createIfcShapeRepresentation(body, 'Body', 'SurfaceModel', [surface])
                run('geometry.assign_representation', doc, product=window, representation=rep)
                run('spatial.assign_container', doc, products=[window], relating_structure=story)
                run('geometry.edit_object_placement', doc, product=window, matrix=matrix, is_si=True)
                provenance = run('pset.add_pset', doc, product=window, name='VRA_Projection')
                run('pset.edit_pset', doc, pset=provenance, properties={'SourceWindowId': opening['source_id'],
                    'GeometryScope': opening['geometry_scope'], 'ProjectionOffsetM': opening['projection_offset_m'],
                    'SimplificationToleranceM': opening.get('approximation_tolerance_m', 0),
                    'Note': 'Planar thermal opening projection, not a fabricated 3D frame or glass thickness'})
    return doc.to_string()
