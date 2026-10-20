"""Metric, reviewable room geometry. Recognition never establishes engineering truth."""
from typing import Literal

from pydantic import Field, StrictFloat, StrictInt, model_validator
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

from .schema import Contract


class Room(Contract):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,59}$")
    name: str = Field(min_length=1, max_length=120)
    polygon: list[tuple[StrictFloat, StrictFloat]] = Field(min_length=3, max_length=100)
    elevation_m: StrictFloat = Field(default=0, ge=-100, le=1500)
    height_m: StrictFloat = Field(default=3, gt=.5, le=30)
    source_locator: str = Field(default="人工输入", min_length=1, max_length=500)

    @model_validator(mode="after")
    def topology(self):
        if any(abs(v) > 10000 for pt in self.polygon for v in pt):
            raise ValueError("坐标超出本地工程坐标范围，请先转换大地坐标")
        p = Polygon(self.polygon)
        if not p.is_valid or p.area < .5 or p.area > 100000:
            raise ValueError("房间必须是不自交的闭合平面，面积 0.5–100000 m²")
        self.polygon = list(orient(p, sign=1).exterior.coords)[:-1]
        return self


class MaterialLayer(Contract):
    name: str = Field(min_length=1, max_length=120)
    thickness_m: StrictFloat = Field(gt=.001, le=2)
    conductivity_w_mk: StrictFloat = Field(gt=.005, le=400)
    density_kg_m3: StrictFloat = Field(ge=1, le=30000)
    specific_heat_j_kgk: StrictFloat = Field(ge=100, le=6000)


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

    @model_validator(mode="after")
    def ordered(self):
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
        for i, a in enumerate(self.rooms):
            for b in self.rooms[i + 1:]:
                if min(a.elevation_m + a.height_m, b.elevation_m + b.height_m) - max(a.elevation_m, b.elevation_m) > .001:
                    if Polygon(a.polygon).intersection(Polygon(b.polygon)).area > .01:
                        raise ValueError(f"房间 {a.id} 与 {b.id} 体积重叠，请修正识别候选")
        return self


class ImportOptions(Contract):
    file_id: str
    mode: Literal["geometry", "vision"] = "geometry"
    scale_to_m: StrictFloat | None = Field(default=None, gt=0, le=100)
    height_m: StrictFloat = Field(default=3, gt=.5, le=30)
    elevation_m: StrictFloat = Field(default=0, ge=-100, le=1500)
    layer: str | None = Field(default=None, max_length=150)
    page: StrictInt = Field(default=1, ge=1, le=500)
    send_to_provider: bool = False


class PublishModel(Contract):
    revision: StrictInt = Field(ge=1)
    scheme_id: Literal["baseline", "R1", "R2"] = "baseline"
    responsible_person: str = Field(min_length=1, max_length=100)
    review_note: str = Field(min_length=10, max_length=2000)
