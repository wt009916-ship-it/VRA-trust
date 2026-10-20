"""Deterministic IFC4 space export and EnergyPlus 9.0 ideal-load model compiler."""
import math

from shapely.geometry import LineString, Point, Polygon

from . import core

COMPILER_VERSION = "prismatic-ideal-loads-1"
LIMITATIONS = [
    "水平棱柱空间模型；不表示施工级墙、门、结构构件或完整 BIM。",
    "理想负荷 HVAC：DistrictHeating/DistrictCooling 是供热/供冷需求，不是热泵耗电；未建真实设备效率、风机、水泵、管网。",
    "有分层构造时按材料厚度、导热、密度与比热建模；未提供构造层时按 U 值生成无热容层。未建相变潜热或温变物性，窗按均匀窗墙比生成。",
    "人员、照明、设备和 HVAC 按每日同一运行时段，无假日差异；渗透按 ACH，机械新风与湿度控制尚未建模；土温全年固定。",
    "本结果用于已声明参数的方案情景，未校准、未签署，不等同于建筑节能合规验收。",
]


def geometry(model):
    rooms = model["rooms"]
    surfaces = []
    polygons = {r["id"]: Polygon(r["polygon"]) for r in rooms}
    minimum = min(r["elevation_m"] for r in rooms)
    for r in rooms:
        rid, z, height = r["id"], r["elevation_m"], r["height_m"]
        poly = polygons[rid]
        # Refuse partial vertical adjacency rather than turning it into outside air.
        for other in rooms:
            if other is r:
                continue
            q = polygons[other["id"]]
            overlap = poly.intersection(q).area
            touching = abs(z + height-other["elevation_m"]) < .001 or abs(z-other["elevation_m"]-other["height_m"]) < .001
            if overlap > .01 and touching and poly.symmetric_difference(q).area > .01:
                raise core.ValidationError("部分叠层空间需要拆分成对齐热区；当前编译器拒绝近似楼板边界")
            vertical_overlap = min(z + height, other["elevation_m"] + other["height_m"])-max(z, other["elevation_m"])
            if poly.boundary.intersection(q.boundary).length > .01 and vertical_overlap > .001:
                if abs(z-other["elevation_m"]) > .001 or abs(height-other["height_m"]) > .001:
                    raise core.ValidationError("相邻房间存在错层或不同层高，请先拆分热区")
        for kind, plane_z, suffix in (("Floor", z, "F"), ("Roof", z+height, "R")):
            other = next((q for q in rooms if q is not r and
                          abs((q["elevation_m"]+q["height_m"] if kind == "Floor" else q["elevation_m"])-plane_z) < .001
                          and poly.symmetric_difference(polygons[q["id"]]).area < .01), None)
            points = [[x, y, plane_z] for x, y in r["polygon"]]
            if kind == "Floor":
                points.reverse()
            surfaces.append({"name": rid+"_"+suffix, "zone": rid, "kind": kind,
                             "construction": ("FloorReverse" if kind == "Roof" else "Floor") if other else ("Floor" if kind == "Floor" else "Roof"),
                             "boundary": "Surface" if other else ("Ground" if kind == "Floor" and abs(z-minimum) < .001 else "Outdoors"),
                             "other": (other["id"]+("_R" if kind == "Floor" else "_F")) if other else "",
                             "points": points})
        coords = r["polygon"]
        n = 0
        for a, b in zip(coords, coords[1:] + coords[:1]):
            edge = LineString([a, b])
            cuts = {0.0, 1.0}
            for q in rooms:
                if abs(z-q["elevation_m"]) < .001:
                    for point in q["polygon"]:
                        if edge.distance(Point(point)) < .00001:
                            cuts.add(edge.project(Point(point), normalized=True))
            cuts = sorted(cuts)
            for begin, end in zip(cuts, cuts[1:]):
                if end-begin < .000001:
                    continue
                p, q = edge.interpolate(begin, normalized=True), edge.interpolate(end, normalized=True)
                n += 1
                surfaces.append({"name": f"{rid}_W{n}", "zone": rid, "kind": "Wall", "construction": "Wall",
                                 "boundary": "Outdoors", "other": "", "points":
                                 [[p.x, p.y, z], [q.x, q.y, z], [q.x, q.y, z+height], [p.x, p.y, z+height]]})
    for index, a in enumerate(surfaces):
        if a["kind"] != "Wall":
            continue
        key = {tuple(round(c, 5) for c in pt) for pt in a["points"]}
        for b in surfaces[index+1:]:
            if b["kind"] == "Wall" and b["zone"] != a["zone"] and key == {tuple(round(c, 5) for c in pt) for pt in b["points"]}:
                a.update(boundary="Surface", other=b["name"])
                b.update(boundary="Surface", other=a["name"], construction="WallReverse")
    return surfaces


def idf(model):
    t = model.get("thermal")
    if not t:
        raise core.ValidationError("需完整填写热工、内部负荷、时段与参数来源")
    surfaces = geometry(model)
    used_constructions = {surface["construction"] for surface in surfaces}
    objects = ["! VRA compiler " + COMPILER_VERSION, "! Ideal loads: thermal demand is NOT heat-pump electricity."]

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
        obj("Zone", name, 0, 0, 0, 0, 1, 1, r["height_m"], "autocalculate", "autocalculate")
        obj("ZoneInfiltration:DesignFlowRate", name+"Infil", name, "Always", "AirChanges/Hour",
            "", "", "", t["infiltration_ach"], 1, 0, 0, 0)
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
            center = [sum(p[j] for p in s["points"])/4 for j in range(3)]
            scale = math.sqrt(t["window_wall_ratio"])
            points = [[center[j]+scale*(p[j]-center[j]) for j in range(3)] for p in s["points"]]
            obj("FenestrationSurface:Detailed", s["name"]+"Win", "Window", "Window", s["name"], "",
                "autocalculate", "", 1, 4, *[round(v, 6) for p in points for v in p])
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
            pts = [doc.createIfcCartesianPoint((float(x), float(y))) for x, y in room["polygon"]]
            curve = doc.createIfcPolyline(pts + [pts[0]])
            profile = doc.createIfcArbitraryClosedProfileDef("AREA", None, curve)
            rep = run("geometry.add_profile_representation", doc, context=body, profile=profile,
                      depth=room["height_m"], cardinal_point=None)
            run("geometry.assign_representation", doc, product=space, representation=rep)
            matrix = np.eye(4)
            matrix[2, 3] = elevation
            run("geometry.edit_object_placement", doc, product=space, matrix=matrix, is_si=True)
            pset = run("pset.add_pset", doc, product=space, name="VRA_Provenance")
            run("pset.edit_pset", doc, pset=pset, properties={"RoomId": room["id"], "Source": room["source_locator"],
                "ModelRevision": model.get("revision", 0), "Reviewed": model.get("reviewed", False)})
    return doc.to_string()
