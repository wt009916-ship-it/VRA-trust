"""Metric, reviewable room geometry. Recognition never establishes engineering truth."""
from typing import Literal

from pydantic import Field, StrictBool, StrictFloat, StrictInt, model_validator
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from .schema import Contract
from .model_geometry import parts, simple_pieces


class Segment(Contract):
    polygon: list[tuple[StrictFloat, StrictFloat]] = Field(min_length=3, max_length=256)
    elevation_m: StrictFloat = Field(default=0, ge=-100, le=1500)
    height_m: StrictFloat = Field(default=3, gt=.000001, le=30)

    @model_validator(mode="after")
    def topology(self):
        if any(abs(v) > 10000 for pt in self.polygon for v in pt):
            raise ValueError("坐标超出本地工程坐标范围，请先转换大地坐标")
        p = Polygon(self.polygon)
        if not p.is_valid or p.area < .000001 or p.area > 100000:
            raise ValueError("空间分段必须是不自交、非零面积的闭合平面")
        self.polygon = list(orient(p, sign=1).exterior.coords)[:-1]
        return self


class BoundaryHint(Contract):
    points: list[tuple[StrictFloat, StrictFloat, StrictFloat]] = Field(min_length=3, max_length=100)
    classification: Literal["INTERNAL", "EXTERNAL", "EXTERNAL_EARTH", "EXTERNAL_WATER", "EXTERNAL_FIRE", "NOTDEFINED"]
    source_id: str = Field(min_length=1, max_length=100)
    element_plane_range_m: tuple[StrictFloat, StrictFloat] | None = None

    @model_validator(mode="after")
    def bounded(self):
        from .model_geometry import frame
        if any(abs(v) > 15000 for p in self.points for v in p):
            raise ValueError("边界坐标超出工程坐标范围")
        frame(self.points)
        if self.element_plane_range_m:
            low, high = self.element_plane_range_m
            if not -15000 <= low <= high <= 15000 or high-low > 1:
                raise ValueError("墙体投影范围无效")
        return self


class DrawingTrace(Contract):
    page: StrictInt = Field(ge=1, le=500)
    pixels: tuple[StrictInt, StrictInt]
    polygon_px: list[tuple[StrictFloat, StrictFloat]] = Field(min_length=3, max_length=100)
    scale_to_m: StrictFloat = Field(gt=0, le=100)
    scale_basis: str = Field(min_length=10, max_length=500)
    closure_m: StrictFloat = Field(ge=0, le=1.5)
    label: str = Field(max_length=500)
    annotated_area_m2: StrictFloat | None = Field(default=None, gt=0)
    area_error_percent: StrictFloat | None = None


class QuantitySource(Contract):
    value: StrictFloat = Field(gt=0)
    entity_id: StrictInt = Field(gt=0)
    set: str = Field(max_length=200)


class Reconstruction(Contract):
    method: Literal["IFC_FOOTPRINT_QUANTITY_EXTRUSION"]
    footprint_entity_id: StrictInt = Field(gt=0)
    quantities: dict[Literal["Height", "NetFloorArea", "NetVolume"], QuantitySource]
    area_error_percent: StrictFloat = Field(ge=-1, le=1)
    volume_error_percent: StrictFloat = Field(ge=-1, le=1)
    assumption: str = Field(max_length=500)


class Room(Segment):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,59}$")
    name: str = Field(min_length=1, max_length=120)
    height_m: StrictFloat = Field(default=3, gt=.5, le=30)
    source_locator: str = Field(default="人工输入", min_length=1, max_length=500)
    holes: list[list[tuple[StrictFloat, StrictFloat]]] = Field(default_factory=list, max_length=16)
    segments: list[Segment] = Field(default_factory=list, max_length=128)
    reconstruction: Reconstruction | None = None
    drawing: DrawingTrace | None = None
    ifc_source: str | None = Field(default=None, max_length=100)
    boundary_hints: list[BoundaryHint] = Field(default_factory=list, max_length=500)
    conditioned: StrictBool | None = True
    include_floor_area: StrictBool | None = True

    @model_validator(mode="after")
    def solid(self):
        minimum = .05 if self.ifc_source else .5
        if any(not 3 <= len(ring) <= 100 or any(abs(v) > 10000 for pt in ring for v in pt) for ring in self.holes):
            raise ValueError("孔洞须有 3–100 个有界顶点")
        footprint = Polygon(self.polygon, self.holes)
        if not footprint.is_valid:
            raise ValueError("孔洞须在空间内部且互不相交，不能与外轮廓相交")
        self.holes = [list(ring.coords)[:-1] for ring in orient(footprint, sign=1).interiors]
        if self.holes and not self.segments:
            pieces = simple_pieces(footprint)
            if len(pieces) > 128:
                raise ValueError("带孔空间分解超过 128 段，请简化源几何")
            self.segments = [Segment(polygon=list(p.exterior.coords)[:-1], elevation_m=self.elevation_m,
                                     height_m=self.height_m) for p in pieces]
        if footprint.area < minimum:
            raise ValueError(f"房间底面积须不小于 {minimum:g} m²（IFC 保留小型设备间）")
        if self.segments:
            low = min(s.elevation_m for s in self.segments)
            high = max(s.elevation_m+s.height_m for s in self.segments)
            if abs(low-self.elevation_m) > 1e-6 or abs(high-low-self.height_m) > 1e-6:
                raise ValueError("房间高度与分段范围不一致")
            base = unary_union([Polygon(s.polygon) for s in self.segments if abs(s.elevation_m-low) < 1e-7])
            if base.symmetric_difference(footprint).area > 1e-6:
                raise ValueError("房间底面与最低分段不一致")
            for i, a in enumerate(self.segments):
                for b in self.segments[i+1:]:
                    if min(a.elevation_m+a.height_m, b.elevation_m+b.height_m)-max(a.elevation_m, b.elevation_m) > 1e-6:
                        if Polygon(a.polygon).intersection(Polygon(b.polygon)).area > 1e-7:
                            raise ValueError("同一空间的几何分段体积重叠")
        return self


class MaterialLayer(Contract):
    name: str = Field(min_length=1, max_length=120)
    thickness_m: StrictFloat = Field(gt=.001, le=2)
    conductivity_w_mk: StrictFloat = Field(gt=.005, le=400)
    density_kg_m3: StrictFloat = Field(ge=1, le=30000)
    specific_heat_j_kgk: StrictFloat = Field(ge=100, le=6000)


class Operation(Contract):
    """An explicit load/ventilation scenario, never an inferred occupancy standard."""
    weekday: list[StrictFloat] = Field(min_length=24, max_length=24)
    weekend: list[StrictFloat] = Field(min_length=24, max_length=24)
    outdoor_air_l_s_person: StrictFloat = Field(ge=0, le=30)
    outdoor_air_l_s_m2: StrictFloat = Field(ge=0, le=10)
    sensible_recovery: StrictFloat = Field(ge=0, le=.95)
    latent_recovery: StrictFloat = Field(ge=0, le=.95)
    heating_setback_c: StrictFloat = Field(ge=0, le=28)
    cooling_setback_c: StrictFloat = Field(ge=18, le=45)
    source_note: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def fractions(self):
        if any(not 0 <= v <= 1 for v in self.weekday + self.weekend):
            raise ValueError("逐时使用率须在 0–1 之间")
        if self.heating_setback_c >= self.cooling_setback_c:
            raise ValueError("非使用时段供暖温度须低于制冷温度")
        if (self.sensible_recovery or self.latent_recovery) and not (self.outdoor_air_l_s_person or self.outdoor_air_l_s_m2):
            raise ValueError("热回收需要明确的新风流量")
        return self


class HeatPump(Contract):
    """Explicit fixed-size single-speed PTHP; no inferred manufacturer data."""
    cooling_w_m2: StrictFloat = Field(gt=10, le=500)
    heating_w_m2: StrictFloat = Field(gt=10, le=500)
    airflow_l_s_m2: StrictFloat = Field(gt=.5, le=30)
    cooling_cop: StrictFloat = Field(gt=1, le=8)
    heating_cop: StrictFloat = Field(gt=1, le=8)
    sensible_heat_ratio: StrictFloat = Field(ge=.5, le=.95)
    fan_pressure_pa: StrictFloat = Field(gt=0, le=1500)
    fan_total_efficiency: StrictFloat = Field(gt=.1, le=1)
    fan_motor_efficiency: StrictFloat = Field(gt=.1, le=1)
    supplemental_w_m2: StrictFloat = Field(ge=0, le=500)
    minimum_outdoor_c: StrictFloat = Field(ge=-20, le=5)
    minimum_cooling_outdoor_c: StrictFloat = Field(ge=0, le=18)
    source_note: str = Field(min_length=10, max_length=2000)


class Thermal(Contract):
    # No default thermal values: the user must provide a scenario or measured inputs.
    wall_u: StrictFloat = Field(gt=.05, le=10)
    roof_u: StrictFloat = Field(gt=.05, le=10)
    floor_u: StrictFloat = Field(gt=.05, le=10)
    window_u: StrictFloat = Field(gt=.1, le=8)
    window_shgc: StrictFloat = Field(gt=0, lt=1)
    window_wall_ratio: StrictFloat = Field(ge=0, le=.6)
    heating_c: StrictFloat = Field(ge=5, le=28)
    cooling_c: StrictFloat = Field(ge=18, le=40)
    infiltration_ach: StrictFloat = Field(ge=0, le=5)
    ground_temperature_c: StrictFloat = Field(ge=-30, le=50)
    lights_w_m2: StrictFloat = Field(ge=0, le=50)
    equipment_w_m2: StrictFloat = Field(ge=0, le=100)
    people_m2_person: StrictFloat = Field(gt=1, le=1000)
    active_start: StrictInt = Field(ge=0, le=22)
    active_end: StrictInt = Field(ge=1, le=24)
    north_deg: StrictFloat = Field(default=0, ge=0, lt=360)
    basis: Literal["assumed_scenario", "documented"]
    source_note: str = Field(min_length=10, max_length=2000)
    constructions: dict[Literal["wall", "roof", "floor"], list[MaterialLayer]] = Field(default_factory=dict)
    operation: Operation | None = None
    heat_pump: HeatPump | None = None
    adjacency_gap_m: StrictFloat = Field(default=0, ge=0, le=.6)
    ifc_unpaired_policy: Literal["reject", "adiabatic_scenario"] = "reject"
    geometry_tolerance_m: StrictFloat = Field(default=0, ge=0, le=.05)

    @model_validator(mode="after")
    def ordered(self):
        if self.heat_pump:
            if not self.operation:
                raise ValueError("热泵设备模型须填写逐时运行与新风参数")
            if self.operation.sensible_recovery or self.operation.latent_recovery:
                raise ValueError("当前独立 PTHP 不含新风热回收器，请将回收效率设为 0；不能静默忽略")
            if self.heat_pump.fan_total_efficiency > self.heat_pump.fan_motor_efficiency:
                raise ValueError("风机总效率不能高于电机效率")
        if self.adjacency_gap_m and self.basis != "assumed_scenario":
            raise ValueError("跨墙厚邻接推断须标为假设情景并记录距离，不能当作实测连接")
        if self.ifc_unpaired_policy == "adiabatic_scenario" and self.basis != "assumed_scenario":
            raise ValueError("未配对 IFC 边界绝热处理只能用于明确假设的情景，不能标成已有文件证明")
        if self.geometry_tolerance_m and self.basis != "assumed_scenario":
            raise ValueError("几何公差简化只能用于明确假设的情景，并保留原始空间")
        for key, layers in self.constructions.items():
            if not 1 <= len(layers) <= 8:
                raise ValueError("每组构造须有 1–8 层材料")
            resistance = sum(layer.thickness_m/layer.conductivity_w_mk for layer in layers)
            film = {"wall": .17, "roof": .14, "floor": .21}[key]
            if not .05 < 1/(resistance+film) <= 10:
                raise ValueError(key + " 构造计算 U 值超出当前模型范围 (0.05, 10]")
            # U is a derived value whenever a documented/assumed layer assembly is provided.
            setattr(self, key+"_u", 1/(resistance+film))
        if self.heating_c >= self.cooling_c or self.active_start >= self.active_end:
            raise ValueError("制热设定点须低于制冷设定点；运行结束须晚于开始")
        # NoMass uses layer resistance; deduct conventional inside/outside films.
        for key, film in (("wall_u", .17), ("roof_u", .14), ("floor_u", .21)):
            if 1 / getattr(self, key) <= film:
                raise ValueError(key + " 超出当前无热容构造换算范围")
        return self


class ModelDraft(Contract):
    expected_revision: StrictInt = Field(default=0, ge=0)
    name: str = Field(default="建筑模型", min_length=1, max_length=120)
    rooms: list[Room] = Field(min_length=1, max_length=100)
    thermal: Thermal | None = None
    review_note: str = Field(min_length=5, max_length=2000)
    reviewed: bool = False

    @model_validator(mode="after")
    def nonoverlap(self):
        if len({r.id.casefold() for r in self.rooms}) != len(self.rooms):
            raise ValueError("房间 ID 重复（EnergyPlus 不区分大小写）")
        solids = [[(s["elevation_m"], s["elevation_m"]+s["height_m"], Polygon(s["polygon"]))
                   for s in parts(room.model_dump())] for room in self.rooms]
        if sum(map(len, solids)) > 1000:
            raise ValueError("建筑分段超过 1000")
        for i, room in enumerate(self.rooms):
            for j in range(i+1, len(self.rooms)):
                other = self.rooms[j]
                for low, high, shape in solids[i]:
                    for bottom, top, polygon in solids[j]:
                        if min(high, top)-max(low, bottom) > .001:
                            if shape.intersection(polygon).area > .01:
                                raise ValueError(f"房间 {room.id} 与 {other.id} 体积重叠，请修正识别候选")
        return self


class ImportOptions(Contract):
    file_id: str
    mode: Literal["geometry", "vision", "local_raster"] = "geometry"
    scale_to_m: StrictFloat | None = Field(default=None, gt=0, le=100)
    height_m: StrictFloat = Field(default=3, gt=.5, le=30)
    elevation_m: StrictFloat = Field(default=0, ge=-100, le=1500)
    layer: str | None = Field(default=None, max_length=150)
    page: StrictInt = Field(default=1, ge=1, le=500)
    send_to_provider: bool = False
    reconstruct_footprints: bool = False
    ifc_origin_m: tuple[StrictFloat, StrictFloat, StrictFloat] | None = None
    ifc_storey_ids: list[str] = Field(default_factory=list, max_length=50)
    crop_px: tuple[StrictInt, StrictInt, StrictInt, StrictInt] | None = None
    scale_basis: str = Field(default="", max_length=500)
    closure_m: StrictFloat = Field(default=0, ge=0, le=1.5)
    min_room_area_m2: StrictFloat = Field(default=1, ge=.5, le=20)

    @model_validator(mode="after")
    def raster_options(self):
        if self.mode == "local_raster" and (self.scale_to_m is None or len(self.scale_basis.strip()) < 10):
            raise ValueError("本地图纸建模须标定比例并填写至少 10 字的尺寸来源；不会自动猜测米数")
        if self.crop_px:
            x0, y0, x1, y1 = self.crop_px
            if not 0 <= x0 < x1 <= 2400 or not 0 <= y0 < y1 <= 2400:
                raise ValueError("裁剪范围须是预览图内的有效像素矩形")
        return self


class PublishModel(Contract):
    revision: StrictInt = Field(ge=1)
    scheme_id: Literal["baseline", "R1", "R2"] = "baseline"
    responsible_person: str = Field(min_length=1, max_length=100)
    review_note: str = Field(min_length=10, max_length=2000)
