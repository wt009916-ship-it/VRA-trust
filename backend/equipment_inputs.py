"""Project-file-bound absolute PTHP nameplates and optional source performance curves."""
import csv
import io
import json
import math
from itertools import islice
from typing import Annotated, Literal

from pydantic import Field, StrictFloat, model_validator

from . import core
from .schema import Contract

CURVES = ('cooling_capacity_temperature', 'cooling_capacity_flow', 'cooling_eir_temperature',
          'cooling_eir_flow', 'cooling_part_load', 'heating_capacity_temperature',
          'heating_capacity_flow', 'heating_eir_temperature', 'heating_eir_flow', 'heating_part_load')


class PerformanceCurve(Contract):
    kind: Literal['quadratic', 'biquadratic']
    coefficients: list[Annotated[StrictFloat, Field(ge=-1e6, le=1e6)]] = Field(min_length=3, max_length=6)
    x_min: StrictFloat = Field(ge=-1000, le=1000)
    x_max: StrictFloat = Field(ge=-1000, le=1000)
    y_min: StrictFloat | None = Field(default=None, ge=-1000, le=1000)
    y_max: StrictFloat | None = Field(default=None, ge=-1000, le=1000)
    source_note: str = Field(min_length=10, max_length=1000)

    @model_validator(mode='after')
    def valid_curve(self):
        if len(self.coefficients) != (3 if self.kind == 'quadratic' else 6) or self.x_min >= self.x_max:
            raise ValueError('曲线系数数量或自变量范围无效')
        if self.kind == 'biquadratic' and (self.y_min is None or self.y_max is None or self.y_min >= self.y_max):
            raise ValueError('双二次曲线须填写有效的第二温度范围')
        c = self.coefficients
        points = [(self.x_min, 0.), (self.x_max, 0.)]
        if self.kind == 'quadratic':
            if c[2] > 0 and self.x_min < -c[1]/(2*c[2]) < self.x_max:
                points.append((-c[1]/(2*c[2]), 0.))
        else:
            points = [(x, y) for x in (self.x_min, self.x_max) for y in (self.y_min, self.y_max)]
            for x in (self.x_min, self.x_max):
                if c[4] > 0:
                    y = -(c[3]+c[5]*x)/(2*c[4])
                    if self.y_min < y < self.y_max:
                        points.append((x, y))
            for y in (self.y_min, self.y_max):
                if c[2] > 0:
                    x = -(c[1]+c[5]*y)/(2*c[2])
                    if self.x_min < x < self.x_max:
                        points.append((x, y))
            det = 4*c[2]*c[4]-c[5]**2
            if abs(det) > 1e-15:
                x, y = (-2*c[4]*c[1]+c[5]*c[3])/det, (-2*c[2]*c[3]+c[5]*c[1])/det
                if self.x_min < x < self.x_max and self.y_min < y < self.y_max:
                    points.append((x, y))
        values = [self.evaluate(x, y) for x, y in points]
        if any(not math.isfinite(v) or v <= 0 for v in values):
            raise ValueError('性能曲线在声明区间存在非正值或非有限值；须核对系数、单位和有效工况')
        return self

    def evaluate(self, x, y=0):
        c = self.coefficients
        return c[0]+c[1]*x+c[2]*x*x+(c[3]*y+c[4]*y*y+c[5]*x*y if len(c) == 6 else 0)


class ZoneEquipment(Contract):
    zone_id: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,59}$')
    system_type: Literal['PTHP']
    manufacturer: str = Field(min_length=1, max_length=200)
    model: str = Field(min_length=1, max_length=200)
    cooling_capacity_w: StrictFloat = Field(gt=0, le=100000000)
    heating_capacity_w: StrictFloat = Field(gt=0, le=100000000)
    airflow_m3_s: StrictFloat = Field(gt=0, le=1000)
    cooling_cop: StrictFloat = Field(gt=1, le=8)
    heating_cop: StrictFloat = Field(gt=1, le=8)
    sensible_heat_ratio: StrictFloat = Field(ge=.5, le=.95)
    fan_pressure_pa: StrictFloat = Field(gt=0, le=1500)
    fan_total_efficiency: StrictFloat = Field(gt=.1, le=1)
    fan_motor_efficiency: StrictFloat = Field(gt=.1, le=1)
    supplemental_capacity_w: StrictFloat = Field(ge=0, le=100000000)
    minimum_outdoor_c: StrictFloat = Field(ge=-20, le=5)
    minimum_cooling_outdoor_c: StrictFloat = Field(ge=0, le=18)
    curve_basis: Literal['source_curves', 'native_reference']
    curves: dict[str, PerformanceCurve] = Field(default_factory=dict, max_length=10)
    source_file_id: str
    source_file_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_locator: str = Field(min_length=5, max_length=500)
    source_note: str = Field(min_length=10, max_length=2000)

    @model_validator(mode='after')
    def coherent(self):
        if self.fan_total_efficiency > self.fan_motor_efficiency:
            raise ValueError('设备风机总效率不能大于电机效率')
        if self.curve_basis == 'source_curves' and set(self.curves) != set(CURVES):
            raise ValueError('源性能曲线须完整提供10项容量/EIR/流量/部分负荷曲线')
        if self.curve_basis == 'native_reference' and self.curves:
            raise ValueError('原生参考曲线模式不能混入未声明的源曲线')
        for key, curve in self.curves.items():
            if key not in CURVES or ('cooling' in key and 'temperature' in key and curve.kind != 'biquadratic'):
                raise ValueError('不支持此曲线类型或名称：'+key)
            if 'part_load' in key and (curve.kind != 'quadratic' or not curve.x_min <= 0 < 1 <= curve.x_max or abs(curve.evaluate(1)-1) > .02):
                raise ValueError('部分负荷修正曲线须覆盖0–1，并在满负荷归一至1±0.02')
        return self


NUMERIC = ('cooling_capacity_w', 'heating_capacity_w', 'airflow_m3_s', 'cooling_cop', 'heating_cop',
           'sensible_heat_ratio', 'fan_pressure_pa', 'fan_total_efficiency', 'fan_motor_efficiency',
           'supplemental_capacity_w', 'minimum_outdoor_c', 'minimum_cooling_outdoor_c')
COLUMNS = ('zone_id', 'system_type', 'manufacturer', 'model', *NUMERIC, 'curve_basis', 'source_note', 'curves_json')


def read_csv(record, path):
    if path.suffix.lower() != '.csv':
        raise core.ValidationError('设备清单须为UTF-8 CSV，使用有单位的固定列名；未猜测Excel列含义')
    try:
        reader = csv.DictReader(io.StringIO(path.read_text(encoding='utf-8-sig')), strict=True)
        fields = reader.fieldnames
        rows = list(islice(reader, 2001))
    except UnicodeDecodeError:
        raise core.ValidationError('设备CSV不是有效UTF-8，请从表格软件另存为UTF-8 CSV后重试') from None
    except csv.Error as exc:
        raise core.ValidationError('设备CSV引号、分隔符或字段长度无效：'+str(exc)[:300]) from None
    if set(fields or []) != set(COLUMNS) or len(fields) != len(COLUMNS):
        raise core.ValidationError('设备CSV列不匹配；请先下载模板，额定功率W、送风m³/s，禁止混用kW或L/s')
    equipment = []
    for n, row in enumerate(rows, 2):
        if n > 2001:
            raise core.ValidationError('设备清单超过2000行，未截断')
        try:
            if None in row or any(row[k] is None for k in COLUMNS):
                raise ValueError('字段数量不匹配')
            values = {k: row[k].strip() for k in COLUMNS if k != 'curves_json'}
            values.update({k: float(row[k]) for k in NUMERIC})
            values.update(curves=json.loads(row['curves_json']) if row['curves_json'].strip() else {},
                          source_file_id=record['file_id'], source_file_hash=record['hash'],
                          source_locator=f'CSV row {n}; zone_id={row["zone_id"]}')
            equipment.append(ZoneEquipment(**values).model_dump())
        except (ValueError, TypeError) as exc:
            raise core.ValidationError(f'设备CSV第{n}行无效：'+str(exc)[:700]) from None
    if not equipment or len({e['zone_id'].casefold() for e in equipment}) != len(equipment):
        raise core.ValidationError('设备清单为空或空间ID重复；不会覆盖或自动分摊容量')
    return {'equipment': equipment, 'source': record, 'warnings': [
        '清单只绑定来源和额定参数，不证明设备已安装或实际变工况性能；源文件与空间对应须复核。',
        '当前自动编译限定独立PTHP；冷水机组、VRF及水系统应使用具备依据的外部IDF，不能用PTHP代替。']}


def thermal_for_zone(model, room, area):
    thermal = model['thermal']
    e = next((e for e in model.get('equipment', []) if e['zone_id'] == room['id']), None)
    if not e:
        return thermal
    return {**thermal, 'heat_pump': {'cooling_w_m2': e['cooling_capacity_w']/area,
        'heating_w_m2': e['heating_capacity_w']/area, 'airflow_l_s_m2': e['airflow_m3_s']*1000/area,
        **{k: e[k] for k in ('cooling_cop', 'heating_cop', 'sensible_heat_ratio', 'fan_pressure_pa',
                            'fan_total_efficiency', 'fan_motor_efficiency', 'minimum_outdoor_c', 'minimum_cooling_outdoor_c')},
        'supplemental_w_m2': e['supplemental_capacity_w']/area, 'source_note': e['source_note']}}


def curve_objects(equipment):
    objects = []
    for key, curve in equipment.get('curves', {}).items():
        name = 'VRA_EQ_'+equipment['zone_id']+'_'+key
        fields = [name, *curve['coefficients'], curve['x_min'], curve['x_max']]
        if curve['kind'] == 'biquadratic':
            fields.extend([curve['y_min'], curve['y_max']])
        fields.extend([0, '', 'Temperature' if 'temperature' in key else 'Dimensionless'])
        if curve['kind'] == 'biquadratic':
            fields.append('Temperature')
        fields.append('Dimensionless')
        objects.append('Curve:'+('Biquadratic' if curve['kind'] == 'biquadratic' else 'Quadratic')+',\n  '+',\n  '.join(map(str, fields))+';')
    return objects
