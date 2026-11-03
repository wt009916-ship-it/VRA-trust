"""Central four-pipe fan-coils, native EnergyPlus 9.0 plant loops and design sizing.

The upstream ExpandObjects produces coils, pumps, branches and control topology.
Generic reference equipment curves are explicit assumptions, not fitted products.
"""
from typing import Literal

from pydantic import Field, StrictFloat, StrictInt, model_validator

from .schema import Contract


class DesignDay(Contract):
    kind: Literal['winter', 'summer']
    month: StrictInt = Field(ge=1, le=12)
    day: StrictInt = Field(ge=1, le=31)
    dry_bulb_c: StrictFloat = Field(ge=-60, le=60)
    daily_range_c: StrictFloat = Field(ge=0, le=30)
    wet_bulb_c: StrictFloat = Field(ge=-60, le=50)
    pressure_pa: StrictFloat = Field(ge=50000, le=110000)
    wind_speed_m_s: StrictFloat = Field(ge=0, le=30)
    wind_direction_deg: StrictFloat = Field(ge=0, lt=360)
    sky_clearness: StrictFloat = Field(ge=0, le=1.2)

    @model_validator(mode='after')
    def temperatures(self):
        from datetime import date
        date(2024, self.month, self.day)
        if self.wet_bulb_c > self.dry_bulb_c:
            raise ValueError('设计日湿球温度不得高于干球温度')
        return self


class CentralSystem(Contract):
    kind: Literal['four_pipe_fan_coil']
    basis: Literal['design_scenario', 'documented_design']
    source_note: str = Field(min_length=10, max_length=2000)
    source_file_id: str | None = None
    source_file_hash: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    design_days: list[DesignDay] = Field(min_length=2, max_length=8)
    chiller_cop: StrictFloat = Field(gt=1, le=12)
    chiller_capacity_w: StrictFloat | None = Field(default=None, gt=0, le=1e9)
    condenser: Literal['AirCooled', 'WaterCooled']
    boiler_efficiency: StrictFloat = Field(gt=.1, le=1)
    boiler_capacity_w: StrictFloat | None = Field(default=None, gt=0, le=1e9)
    boiler_fuel: Literal['NaturalGas', 'Electricity']
    chilled_water_c: StrictFloat = Field(ge=4, le=16)
    chilled_water_delta_c: StrictFloat = Field(ge=2, le=12)
    hot_water_c: StrictFloat = Field(ge=35, le=90)
    hot_water_delta_c: StrictFloat = Field(ge=3, le=25)
    chilled_pump_head_pa: StrictFloat = Field(gt=0, le=2e6)
    hot_pump_head_pa: StrictFloat = Field(gt=0, le=2e6)
    condenser_pump_head_pa: StrictFloat | None = Field(default=None, gt=0, le=2e6)
    fan_pressure_pa: StrictFloat = Field(gt=0, le=1500)
    fan_total_efficiency: StrictFloat = Field(gt=.1, le=1)
    fan_motor_efficiency: StrictFloat = Field(gt=.1, le=1)
    curve_basis: Literal['native_reference']

    @model_validator(mode='after')
    def complete(self):
        if {d.kind for d in self.design_days} != {'winter', 'summer'}:
            raise ValueError('中央系统自动设计须同时有冬季和夏季设计日及来源')
        if bool(self.source_file_id) != bool(self.source_file_hash):
            raise ValueError('中央系统来源文件ID与哈希须同时填写')
        if self.basis == 'documented_design' and not self.source_file_id:
            raise ValueError('有文件依据的中央系统须绑定项目原件，不接受无原件声明')
        if self.fan_total_efficiency > self.fan_motor_efficiency:
            raise ValueError('风机总效率不得高于电机效率')
        if self.condenser == 'WaterCooled' and self.condenser_pump_head_pa is None:
            raise ValueError('水冷系统须提供冷却水泵压头')
        return self


def obj(kind, *fields):
    return kind+',\n  '+',\n  '.join(str(v) for v in fields)+';\n'


def plant(thermal):
    p = thermal['central_system']
    result = []
    for i, day in enumerate(p['design_days']):
        result.append(obj('SizingPeriod:DesignDay', 'VRA_'+day['kind']+'_'+str(i), day['month'], day['day'],
            'WinterDesignDay' if day['kind'] == 'winter' else 'SummerDesignDay', day['dry_bulb_c'],
            day['daily_range_c'], '', '', 'Wetbulb', day['wet_bulb_c'], '', '', '', '', day['pressure_pa'],
            day['wind_speed_m_s'], day['wind_direction_deg'], 'No', 'No', 'No', 'ASHRAEClearSky', '', '', '', '', day['sky_clearness']))
    # Exact native IDD field positions; blank optional fields use documented native defaults.
    chilled = ['Chilled Water Loop', '', 'Intermittent', 'Default', '', '', p['chilled_water_c'],
               'ConstantPrimaryNoSecondary', p['chilled_pump_head_pa'], p['chilled_pump_head_pa'],
               'Default', '', '', '', 29.4, p.get('condenser_pump_head_pa') or p['chilled_pump_head_pa'],
               'None', '', '', '', '', '', '', '', '', '', '', '', '', p['chilled_water_delta_c'], 0]
    result.append(obj('HVACTemplate:Plant:ChilledWaterLoop', *chilled))
    result.append(obj('HVACTemplate:Plant:Chiller', 'VRA Chiller', 'ElectricReciprocatingChiller',
                      p.get('chiller_capacity_w') or 'Autosize', p['chiller_cop'], p['condenser'], 1, 1))
    if p['condenser'] == 'WaterCooled':
        result.append(obj('HVACTemplate:Plant:Tower', 'VRA Tower', 'SingleSpeed', 'Autosize', 'Autosize',
                          'Autosize', 'Autosize', 'Autosize', 1, 1))
    result.append(obj('HVACTemplate:Plant:HotWaterLoop', 'Hot Water Loop', '', 'Intermittent', 'Default', '', '',
                      p['hot_water_c'], 'ConstantFlow', p['hot_pump_head_pa'], 'None', '', '', '', '', '', '', '', '', p['hot_water_delta_c']))
    result.append(obj('HVACTemplate:Plant:Boiler', 'VRA Boiler', 'HotWaterBoiler',
                      p.get('boiler_capacity_w') or 'Autosize', p['boiler_efficiency'], p['boiler_fuel'], 1, 1))
    return result


def terminal(name, thermal):
    p, op = thermal['central_system'], thermal['operation']
    return obj('HVACTemplate:Zone:FanCoil', name, '', 'Autosize', 1, 1, 'Sum',
               op['outdoor_air_l_s_person']/1000, op['outdoor_air_l_s_m2']/1000, 0, 'Always',
               p['fan_total_efficiency'], p['fan_pressure_pa'], p['fan_motor_efficiency'], 1,
               'ChilledWater', 'Always', 13, 'HotWater', 'Always', 40, '',
               'SupplyAirTemperature', '', 'SupplyAirTemperature', '', '', '',
               'CyclingFan', '', '', 'Occupied', 'None', '', '')


def outputs(thermal):
    p = thermal['central_system']
    return ['Chiller Electric Energy', 'Boiler Gas Energy' if p['boiler_fuel'] == 'NaturalGas' else 'Boiler Electric Energy',
            'Pump Electric Energy', 'Fan Electric Energy']+(['Cooling Tower Fan Electric Energy'] if p['condenser'] == 'WaterCooled' else [])


def topology(model):
    p = (model.get('thermal') or {}).get('central_system')
    if not p:
        return None
    return {'kind': p['kind'], 'basis': p['basis'], 'curve_basis': p['curve_basis'],
            'source_file_id': p.get('source_file_id'), 'source_file_hash': p.get('source_file_hash'),
            'design_days': p['design_days'],
            'plant': ['chiller', 'chilled_water_pump', 'boiler', 'hot_water_pump']+
                     (['cooling_tower', 'condenser_water_pump'] if p['condenser'] == 'WaterCooled' else []),
            'terminal_zone_ids': [r['id'] for r in model['rooms'] if r.get('conditioned') is not False],
            'sizing': 'Native design-day autosizing for terminal coils and water flows; plant capacities explicit or autosized',
            'limitations': ['Generic native reference curves and controls', 'No traced pipe lengths, hydraulic balancing, thermal pipe losses or high-rise pressure zoning',
                            'Source CAD/BIM connectivity is not automatically translated into this topology']}
