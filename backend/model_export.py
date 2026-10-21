"""Deterministic IFC4 space export and EnergyPlus 9.0 ideal-load model compiler."""
import math

from shapely.geometry import Polygon

from . import core, model_geometry

COMPILER_VERSION = "stepped-spaces-ideal-loads-2"
LIMITATIONS = [
    "水平分段空间模型，保留变截面和共面局部邻接；斜面仍拒绝。不表示完整施工 BIM。",
    "IFC 未配对内部及未知边界默认拒绝；仅显式 assumed_scenario 可按绝热计算，并保留逐面来源。该情景不等于完整建筑热模型。",
    "理想负荷 HVAC：DistrictHeating/DistrictCooling 是供热/供冷需求，不是热泵耗电；未建真实设备效率、风机、水泵、管网。",
    "有分层构造时按材料厚度、导热、密度与比热建模；未提供构造层时按 U 值生成无热容层。未建相变潜热或温变物性，窗按均匀窗墙比生成。",
    "人员、照明、设备和 HVAC 按每日同一运行时段，无假日差异；渗透按 ACH，机械新风与湿度控制尚未建模；土温全年固定。",
    "本结果用于已声明参数的方案情景，未校准、未签署，不等同于建筑节能合规验收。",
]


def compiler_hash():
    return core.hash_json({"export": core.sha(__file__), "geometry": core.sha(model_geometry.__file__)})


def geometry(model):
    derived, _ = model_geometry.thermal_geometry_model(model)
    return model_geometry.geometry(derived)


def idf(model):
    t = model.get("thermal")
    if not t:
        raise core.ValidationError("需完整填写热工、内部负荷、时段与参数来源")
    surfaces = geometry(model)
    used_constructions = {surface["construction"] for surface in surfaces}
    objects = ["! VRA compiler " + COMPILER_VERSION, "! Ideal loads: thermal demand is NOT heat-pump electricity.",
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
    obj("ScheduleTypeLimits", "Temperature", -60, 100, "Continuous", "Temperature")
    obj("ScheduleTypeLimits", "Control", 0, 4, "Discrete")
    obj("ScheduleTypeLimits", "Any")
    for name, limit, value in [("Always", "Fraction", 1), ("Control4", "Control", 4),
                               ("Heat", "Temperature", t["heating_c"]), ("Cool", "Temperature", t["cooling_c"]),
                               ("Activity", "Any", 120)]:
        obj("Schedule:Constant", name, limit, value)
    fields = ["Occupied", "Fraction", "Through: 12/31", "For: AllDays"]
    if t["active_start"]:
        fields += [f'Until: {t["active_start"]:02d}:00', 0]
    fields += [f'Until: {t["active_end"]:02d}:00', 1]
    if t["active_end"] < 24:
        fields += ["Until: 24:00", 0]
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
    for r in model["rooms"]:
        name = r["id"]
        volume = sum(Polygon(s["polygon"]).area*s["height_m"] for s in model_geometry.parts(r))
        area = model_geometry.floor_area(r)
        obj("Zone", name, 0, 0, 0, 0, 1, 1, volume/area, "autocalculate", area,
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
        obj("ZoneHVAC:EquipmentConnections", name, name+"Equipment", name+"Supply", "", name+"Air", name+"Return")
        obj("ZoneHVAC:EquipmentList", name+"Equipment", "SequentialLoad", "ZoneHVAC:IdealLoadsAirSystem", name+"Ideal", 1, 1)
        obj("ZoneHVAC:IdealLoadsAirSystem", name+"Ideal", "Occupied", name+"Supply", "", "", 50, 13, .0156, .0077,
            "NoLimit", "", "", "NoLimit", "", "", "", "", "None", "", "None", "", "", "None", "NoEconomizer", "None", 0, 0)
    for s in surfaces:
        external = s["boundary"] == "Outdoors"
        obj("BuildingSurface:Detailed", s["name"], s["kind"], s["construction"], s["zone"],
            s["boundary"], s["other"], "SunExposed" if external else "NoSun",
            "WindExposed" if external else "NoWind", "autocalculate", len(s["points"]),
            *[round(v, 6) for p in s["points"] for v in p])
        if external and s["kind"] == "Wall" and t["window_wall_ratio"] > 0:
            center = [sum(p[j] for p in s["points"])/len(s["points"]) for j in range(3)]
            scale = math.sqrt(t["window_wall_ratio"])
            points = [[center[j]+scale*(p[j]-center[j]) for j in range(3)] for p in s["points"]]
            obj("FenestrationSurface:Detailed", s["name"]+"Win", "Window", "Window", s["name"], "",
                "autocalculate", "", 1, len(points), *[round(v, 6) for p in points for v in p])
    obj("Output:SQLite", "SimpleAndTabular")
    obj("Output:Table:SummaryReports", "AllSummary")
    obj("OutputControl:Table:Style", "HTML", "JtoKWH")
    obj("Output:Variable", "*", "Zone Mean Air Temperature", "Hourly")
    obj("Output:Variable", "*", "Zone Ideal Loads Supply Air Total Heating Energy", "Hourly")
    obj("Output:Variable", "*", "Zone Ideal Loads Supply Air Total Cooling Energy", "Hourly")
    return "\n".join(objects), surfaces


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
