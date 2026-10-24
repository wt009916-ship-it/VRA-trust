"""Deterministic IFC4 space export and EnergyPlus 9.0 ideal-load model compiler."""

from shapely.geometry import Polygon

from . import core, model_geometry, honeybee_bridge, thermal_mesh, heat_pump

COMPILER_VERSION = "reviewed-thermal-honeybee-pthp-4"
LIMITATIONS = [
    "水平分段空间模型，保留变截面和共面局部邻接；斜面仍拒绝。不表示完整施工 BIM。",
    "IFC 未配对内部及未知边界默认拒绝；仅显式 assumed_scenario 可按绝热计算，并保留逐面来源。该情景不等于完整建筑热模型。",
    "理想负荷模式的 DistrictHeating/DistrictCooling 是冷热需求；PTHP 模式为逐房间定容单速空气源热泵、风机、电辅热的原生模拟，不含水系统和管网。两种口径不能直接排名。",
    "PTHP 使用官方模板默认变工况曲线与按需逆循环除霜；额定参数须另附来源，不能替代厂家曲线或实测校准。新风为设计值，使用时连续风机、其余随负荷启停；不含热回收。",
    "有分层构造时按材料厚度、导热、密度与比热建模；未提供构造层时按 U 值生成无热容层。未建相变潜热或温变物性，窗按均匀窗墙比生成。",
    "可显式填写工作日/周末 24 小时使用率、非使用温度、新风和显潜热回收；无运行档案时保持旧每日时段。未配置法定假日日历和湿度控制；土温全年固定。",
    "本结果用于已声明参数的方案情景，未校准、未签署，不等同于建筑节能合规验收。",
]


def compiler_hash():
    return core.hash_json({"export": core.sha(__file__), "heat_pump": core.sha(heat_pump.__file__), "geometry": core.sha(model_geometry.__file__),
                           "thermal_mesh": core.sha(thermal_mesh.__file__), "honeybee_bridge": core.sha(honeybee_bridge.__file__), "libraries": honeybee_bridge.library_versions()})


def geometry(model):
    derived, _ = model_geometry.thermal_geometry_model(model)
    return thermal_mesh.conform(model_geometry.geometry(derived))


def idf(model):
    t = model.get("thermal")
    if not t:
        raise core.ValidationError("需完整填写热工、内部负荷、时段与参数来源")
    surfaces = geometry(model)
    independent = honeybee_bridge.audit(model, surfaces)
    if not independent["passed"]:
        raise core.ValidationError("Honeybee 独立几何校验失败：" + "; ".join(i["message"] for i in independent["issues"])[:1500])
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
    obj("WindowMaterial:SimpleGlazingSystem", "Glass", t["window_u"], t["window_shgc"], .6)
    obj("Construction", "Window", "Glass")
    validated_volumes = {r["room_id"]: r["volume_m3"] for r in independent["rooms"]}
    for r in model["rooms"]:
        name = r["id"]
        volume = sum(Polygon(s["polygon"]).area*s["height_m"] for s in model_geometry.parts(r))
        area = model_geometry.floor_area(r)
        obj("Zone", name, 0, 0, 0, 0, 1, 1, volume/area, validated_volumes[name], area,
            "", "", "Yes" if r.get("include_floor_area", True) else "No")
        obj("ZoneInfiltration:DesignFlowRate", name+"Infil", name, "Always", "AirChanges/Hour",
            "", "", "", t["infiltration_ach"], 1, 0, 0, 0)
        if not r.get("conditioned", True):
            continue
        obj("People", name+"People", name, "Occupied", "Area/Person", "", "", t["people_m2_person"], .3, "autocalculate", "Activity")
        obj("Lights", name+"Lights", name, "Occupied", "Watts/Area", "", t["lights_w_m2"], "", 0, .5, .2, 0)
        obj("ElectricEquipment", name+"Equip", name, "Occupied", "Watts/Area", "", t["equipment_w_m2"], "", 0, .5, 0)
        obj("ThermostatSetpoint:DualSetpoint", name+"Set", "Heat", "Cool")
        obj("ZoneControl:Thermostat", name+"Thermostat", name, "Control4", "ThermostatSetpoint:DualSetpoint", name+"Set")
        if t.get("heat_pump"):
            objects.append(heat_pump.template(name, area, t))
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
    if t.get("heat_pump"):
        for variable in ("Heating Coil Electric Energy", "Cooling Coil Electric Energy", "Fan Electric Energy"):
            obj("Output:Variable", "*", variable, "Hourly")
    else:
        obj("Output:Variable", "*", "Zone Ideal Loads Supply Air Total Heating Energy", "Hourly")
        obj("Output:Variable", "*", "Zone Ideal Loads Supply Air Total Cooling Energy", "Hourly")
    return "\n".join(objects), surfaces


def scope(model):
    return "packaged_heat_pump_electricity" if (model.get("thermal") or {}).get("heat_pump") else "ideal_thermal_loads"


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
            for section in model_geometry.parts(room):
                pts = [doc.createIfcCartesianPoint((float(x), float(y))) for x, y in section["polygon"]]
                curve = doc.createIfcPolyline(pts + [pts[0]])
                profile = doc.createIfcArbitraryClosedProfileDef("AREA", None, curve)
                position = doc.createIfcAxis2Placement3D(doc.createIfcCartesianPoint(
                    (0., 0., float(section["elevation_m"]-elevation))), None, None)
                solids.append(doc.createIfcExtrudedAreaSolid(profile, position,
                    doc.createIfcDirection((0., 0., 1.)), float(section["height_m"])))
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
    return doc.to_string()
