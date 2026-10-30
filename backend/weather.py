"""Traceable EPW quality analysis and NASA POWER daily climate data. No imputation."""
import calendar
import csv
from datetime import date, timedelta
from functools import lru_cache
import io
import json
import math
import threading
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlencode

import httpx
from pydantic import Field, StrictFloat, model_validator

from . import core
from .domain import identifier
from .schema import Contract

VERSION = "weather-quality-1"
NASA_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
NASA_FIELDS = {"T2M": ("temperature_c", "C", -90, 70), "T2M_MIN": ("minimum_c", "C", -90, 70),
               "T2M_MAX": ("maximum_c", "C", -90, 70), "RH2M": ("humidity_pct", "%", 0, 100),
               "WS10M": ("wind_m_s", "m/s", 0, 75),
               "ALLSKY_SFC_SW_DWN": ("solar_kwh_m2", "kW-hr/m^2/day", 0, 20),
               "PRECTOTCORR": ("precipitation_mm", "mm/day", 0, 3000)}
EPW_FIELDS = {"temperature_c": (6, 99.9, -90, 70), "dew_point_c": (7, 99.9, -90, 70),
              "humidity_pct": (8, 999, 0, 100), "pressure_pa": (9, 999999, 31000, 120000),
              "infrared_wh_m2": (12, 9999, 0, 2000),
              "ghi_wh_m2": (13, 9999, 0, 2000), "dni_wh_m2": (14, 9999, 0, 2000),
              "dhi_wh_m2": (15, 9999, 0, 2000), "wind_direction_deg": (20, 999, 0, 360),
              "wind_m_s": (21, 999, 0, 40)}
SOURCES = [
    {"id": "nasa_power", "name": "NASA POWER", "kind": "已接入 · 日尺度数据", "url": "https://power.larc.nasa.gov/",
     "description": "全球公开气象及太阳辐射数据；保留原始响应、单位、时间标准和模型来源。不是现场测量或 EPW。"},
    {"id": "onebuilding", "name": "Climate.OneBuilding", "kind": "EPW 数据查找入口", "url": "https://climate.onebuilding.org/",
     "description": "查找建筑仿真典型气象年。下载原始 EPW 后在本页上传检查，并核对站点、年代和数据许可。"},
    {"id": "energyplus", "name": "EnergyPlus Weather", "kind": "EPW 数据查找入口", "url": "https://energyplus.net/weather",
     "description": "建筑模拟天气资料入口。典型气象年不代表某一实际年份，不用于极端天气设计定值。"},
    {"id": "open_meteo", "name": "Open-Meteo", "kind": "候选接口 · 未接入", "url": "https://open-meteo.com/en/docs/historical-weather-api",
     "description": "历史再分析数据接口；免费托管接口与商业服务的使用条件不同，本产品未自动调用。"},
]


class AnalysisOptions(Contract):
    heating_base_c: StrictFloat = Field(default=18, ge=0, le=30)
    cooling_base_c: StrictFloat = Field(default=26, ge=10, le=40)

    @model_validator(mode="after")
    def ordered(self):
        if self.heating_base_c >= self.cooling_base_c:
            raise ValueError("采暖度日基准须低于制冷度日基准")
        return self


class EPWAnalysis(AnalysisOptions):
    file_id: str


class NASARequest(AnalysisOptions):
    latitude: StrictFloat = Field(ge=-90, le=90)
    longitude: StrictFloat = Field(ge=-180, le=180)
    start: date
    end: date
    label: str = Field(min_length=1, max_length=120)
    refresh: bool = False

    @model_validator(mode="after")
    def period(self):
        if self.start < date(1984, 1, 1) or self.end >= date.today() or not 0 <= (self.end-self.start).days <= 365:
            raise ValueError("选择 1984 年起至昨天、最长 366 天的历史区间；近期数据可能尚未发布")
        if self.start.year != self.end.year:
            raise ValueError("月度画像按单个自然年整理；跨年资料请按年份分别获取")
        return self


def finite(value, low, high, missing=None):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        if not math.isfinite(n) or (missing is not None and n >= missing) or not low <= n <= high:
            return None
        return n
    except (ValueError, TypeError):
        return None


def avg(values):
    valid = [v for v in values if v is not None]
    return round(sum(valid)/len(valid), 3) if valid else None


def aggregate(rows, options, hourly, full_year, issues):
    daily = defaultdict(list)
    for row in rows:
        daily[row["date"]].append(row)
    days = []
    for key, group in sorted(daily.items()):
        time_complete = len(group) == (24 if hourly else 1) and (not hourly or {r["hour"] for r in group} == set(range(1, 25)))
        complete = time_complete and all(r["temperature_c"] is not None for r in group)
        temperature = avg([r["temperature_c"] for r in group]) if complete else None
        solar = [r["ghi_wh_m2"]/1000 if r["ghi_wh_m2"] is not None else None for r in group] if hourly else [r["solar_kwh_m2"] for r in group]
        d = {"date": key, "month": int(key[5:7]), "temperature_c": temperature,
             "solar_kwh_m2": round(sum(solar), 5) if time_complete and all(x is not None for x in solar) else None,
             "humidity_pct": avg([r["humidity_pct"] for r in group]), "wind_m_s": avg([r["wind_m_s"] for r in group])}
        d["heating_degree_days"] = max(0, options.heating_base_c-temperature) if temperature is not None else None
        d["cooling_degree_days"] = max(0, temperature-options.cooling_base_c) if temperature is not None else None
        days.append(d)
    months = []
    for month in sorted({d["month"] for d in days}):
        group = [d for d in days if d["month"] == month]
        sample_rows = [r for r in rows if int(r["date"][5:7]) == month]
        values = [r["temperature_c"] for r in sample_rows if r["temperature_c"] is not None]
        item = {"month": month, "days": len(group), "valid_temperature_days": sum(d["temperature_c"] is not None for d in group),
                "temperature_c": avg([d["temperature_c"] for d in group]),
                "minimum_c": min(values) if values else None, "maximum_c": max(values) if values else None,
                "humidity_pct": avg([r["humidity_pct"] for r in sample_rows]), "wind_m_s": avg([r["wind_m_s"] for r in sample_rows])}
        expected_days = calendar.monthrange(int(group[0]["date"][:4]), month)[1] if hourly else len(group)
        item["expected_days"] = expected_days
        for key in ("solar_kwh_m2", "heating_degree_days", "cooling_degree_days"):
            item[key] = round(sum(d[key] for d in group), 3) if len(group) == expected_days and all(d[key] is not None for d in group) else None
        months.append(item)
    annual = {"temperature_c": None, "heating_degree_days": None, "cooling_degree_days": None, "solar_kwh_m2": None}
    if full_year and days:
        annual["temperature_c"] = avg([d["temperature_c"] for d in days]) if all(d["temperature_c"] is not None for d in days) else None
        for key in ("heating_degree_days", "cooling_degree_days", "solar_kwh_m2"):
            annual[key] = round(sum(d[key] for d in days), 3) if all(d[key] is not None for d in days) else None
    heatmap = []
    if hourly:
        cells = defaultdict(list)
        for r in rows:
            cells[(int(r["date"][5:7]), r["hour"])].append(r["temperature_c"])
        for month in range(1, 13):
            for hour in range(1, 25):
                values = cells[(month, hour)]
                heatmap.append({"month": month, "hour": hour, "temperature_c": avg(values), "valid_count": sum(v is not None for v in values)})
    insights = []
    valid_months = [m for m in months if m["temperature_c"] is not None]
    if valid_months:
        warm, cold = max(valid_months, key=lambda m: m["temperature_c"]), min(valid_months, key=lambda m: m["temperature_c"])
        insights.append(f"当前数据中，{warm['month']} 月均温最高（{warm['temperature_c']:.1f}°C），{cold['month']} 月最低（{cold['temperature_c']:.1f}°C）。缺测月份须先补证。")
    if annual["heating_degree_days"] is not None:
        insights.append(f"按日均温计算：HDD{options.heating_base_c:g}={annual['heating_degree_days']:.1f} °C·d，CDD{options.cooling_base_c:g}={annual['cooling_degree_days']:.1f} °C·d。度日反映气候需求，不是建筑耗能预测。")
    insights.append("保留原始数据；无效值在整理表中为空，不插值、不把缺失当成 0。" if issues else "检查范围内未发现缺测或时间异常；仍需核对地点、气象年和项目适用性。")
    return {"monthly": months, "annual": annual, "heatmap": heatmap, "daily": days, "insights": insights}


def analyze_epw(path, options):
    raw = Path(path).read_bytes()
    if len(raw) > 20*1024*1024:
        raise core.ValidationError("天气文件超过 20 MB")
    text = None
    for encoding in ("utf-8-sig", "gb18030", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    lines = list(csv.reader(io.StringIO(text or "")))
    if len(lines) < 9 or not lines[0] or lines[0][0] != "LOCATION" or len(lines[0]) < 10:
        raise core.ValidationError("不是有效 EPW：缺少 LOCATION 和八行头部")
    if len(lines) > 8792:
        raise core.ValidationError("本分析器仅接受单个逐时气象年，最多 8784 条记录")
    location = lines[0]
    lat, lon = finite(location[6], -90, 90), finite(location[7], -180, 180)
    timezone, elevation = finite(location[8], -12, 14), finite(location[9], -500, 9000)
    if None in (lat, lon, timezone, elevation):
        raise core.ValidationError("EPW 地点、时区或海拔无效")
    leap = any(len(r) >= 3 and [v.strip().lstrip("0") for v in r[1:3]] == ["2", "29"] for r in lines[8:])
    year = 2000 if leap else 2001  # Calendar for TMY chronology only, not the observation year.
    expected = [(f"{year}-{m:02}-{d:02}", h) for m in range(1, 13) for d in range(1, calendar.monthrange(year, m)[1]+1) for h in range(1, 25)]
    issues, invalid, rows, keys = [], Counter(), [], []
    minutes = set()
    for number, values in enumerate(lines[8:], 9):
        try:
            if len(values) < 35:
                raise ValueError()
            y, m, d, h, minute = (int(values[i]) for i in range(5))
            key = date(year, m, d).isoformat()
            # Legacy EnergyPlus TMY3 files use minute=0; modern hourly EPW uses 60.
            # Accept either consistent convention, never subhourly or mixed records.
            if not 1 <= h <= 24 or minute not in (0, 60) or not 1600 <= y <= 2500:
                raise ValueError()
        except (ValueError, IndexError):
            invalid["timestamp_or_columns"] += 1
            continue
        minutes.add(minute)
        row = {"date": key, "source_year": y, "hour": h, "source_minute": minute, "source_line": number}
        keys.append((key, h))
        for name, (index, missing, low, high) in EPW_FIELDS.items():
            row[name] = finite(values[index], low, high, missing)
            if row[name] is None:
                invalid[name] += 1
        if row["dew_point_c"] is not None and row["temperature_c"] is not None and row["dew_point_c"] > row["temperature_c"]+1:
            invalid["dew_point_above_dry_bulb"] += 1
        rows.append(row)
    duplicates = len(keys)-len(set(keys))
    missing_hours = len(set(expected)-set(keys))
    full = keys == expected
    if not full:
        issues.append(f"逐时序列不完整或顺序错误：缺少 {missing_hours} 小时，重复 {duplicates} 条；不能作为本流程的全年天气。")
    if not lines[7] or lines[7][0] != "DATA PERIODS" or len(lines[7]) < 3 or lines[7][1:3] != ["1", "1"]:
        issues.append("仅支持一个数据周期、每小时一条记录的 EPW。")
    if invalid:
        issues.append("发现缺测标记、越界值或无效记录；见逐字段质量清单。")
    if len(minutes) > 1:
        issues.append("分钟字段混用了 0 和 60；请核对原始文件的逐时时标。")
    result = aggregate(rows, options, True, full, issues)
    return {**result, "rows": rows, "kind": "epw", "name": location[1],
            "location": {"name": location[1], "region": location[2], "country": location[3], "station": location[5],
                         "latitude": lat, "longitude": lon, "timezone_hours": timezone, "elevation_m": elevation},
            "time_basis": "EPW 本地标准时，hour 1–24 为时段结束；兼容旧 TMY3 minute=0。整理日期 2000/2001 仅为典型年索引，source_year/source_minute 保留原值。",
            "quality": {"records": len(lines)-8, "expected_records": len(expected), "missing_records": missing_hours,
                        "duplicate_records": duplicates, "invalid_fields": dict(invalid), "full_year": full,
                        "simulation_candidate": full and not issues, "issues": issues},
            "limitations": ["仅检查时间、常用气象字段和数值范围，不证明站点代表性或气象测量准确性。",
                            "典型气象年不能代表极端设计条件；月度极值为文件中的小时气温极值。", "通过检查后仍须人工登记和复核 EPW 证据。"]}


@lru_cache(maxsize=32)
def checked_epw_quality(path, checksum, version=VERSION):
    """Cache only after the caller's file/evidence hash checks; never cache source validity."""
    return analyze_epw(path, AnalysisOptions())["quality"]


def analyze_nasa(data, options):
    try:
        header, parameters, values = data["header"], data["parameters"], data["properties"]["parameter"]
        if header["time_standard"] != "LST":
            raise ValueError("NASA 时间标准不匹配")
        if str(header["start"]) != options.start.strftime("%Y%m%d") or str(header["end"]) != options.end.strftime("%Y%m%d"):
            raise ValueError("NASA 返回日期与请求不一致")
        coordinates = data["geometry"]["coordinates"]
        longitude, latitude = finite(coordinates[0], -180, 180), finite(coordinates[1], -90, 90)
        if longitude is None or latitude is None or abs(longitude-options.longitude) > 0.001 or abs(latitude-options.latitude) > 0.001:
            raise ValueError("NASA 返回坐标与请求不一致")
        for key, (_, unit, _, _) in NASA_FIELDS.items():
            if parameters[key]["units"] != unit:
                raise ValueError("NASA 字段单位变化，需更新转换器："+key)
        rows, invalid, missing_dates = [], Counter(), 0
        for n in range((options.end-options.start).days+1):
            day = options.start+timedelta(days=n)
            key = day.strftime("%Y%m%d")
            if key not in values["T2M"]:
                missing_dates += 1
            row = {"date": day.isoformat()}
            for field, (name, _, low, high) in NASA_FIELDS.items():
                value = values[field].get(key)
                row[name] = None if value == header["fill_value"] else finite(value, low, high)
                if row[name] is None:
                    invalid[name] += 1
            low, mean, high = row["minimum_c"], row["temperature_c"], row["maximum_c"]
            if all(v is not None for v in (low, mean, high)) and not low <= mean <= high:
                invalid["temperature_order"] += 1
                row.update(minimum_c=None, temperature_c=None, maximum_c=None)
            rows.append(row)
    except (KeyError, IndexError, AttributeError, TypeError, ValueError) as exc:
        raise core.ValidationError("NASA 响应结构或单位校验失败："+str(exc)[:200]) from exc
    full = options.start.month == 1 and options.start.day == 1 and options.end == date(options.start.year, 12, 31) and not missing_dates
    issues = ["有缺失或异常字段；全年汇总按指标完整性决定是否显示。"] if invalid else []
    result = aggregate(rows, options, False, full, issues)
    # Daily minima/maxima are provided explicitly; don't mislabel daily mean extremes.
    for item in result["monthly"]:
        group = [r for r in rows if int(r["date"][5:7]) == item["month"]]
        lows, highs = [r["minimum_c"] for r in group if r["minimum_c"] is not None], [r["maximum_c"] for r in group if r["maximum_c"] is not None]
        item.update(minimum_c=min(lows) if lows else None, maximum_c=max(highs) if highs else None)
    return {**result, "rows": rows, "kind": "nasa_daily", "name": options.label,
            "location": {"name": options.label, "latitude": options.latitude, "longitude": options.longitude},
            "time_basis": "NASA LST 本地太阳时（日尺度），不等同于中国标准时间 UTC+8。",
            "upstream": {"header": header, "parameters": parameters, "geometry": data.get("geometry")},
            "quality": {"records": len(rows)-missing_dates, "expected_records": len(rows), "missing_records": missing_dates,
                        "duplicate_records": 0, "invalid_fields": dict(invalid), "full_year": full,
                        "simulation_candidate": False, "issues": issues},
            "limitations": ["NASA POWER 为格点/再分析与卫星衍生数据，不是建筑现场实测。",
                            "日尺度资料仅供气候分析，不能直接生成或替代 EnergyPlus 逐时 EPW。",
                            "度日与太阳辐射不直接等于建筑能耗、节能收益或可安装光伏发电量。"]}


class Weather:
    def __init__(self, domain):
        self.domain, self.store = domain, domain.store
        self.capacity = threading.BoundedSemaphore(2)
        self.lock = threading.RLock()

    def get(self, project_id, weather_id):
        obj = self.store.get("weather", weather_id)
        if obj["project_id"] != project_id:
            raise core.ValidationError("天气记录不属于当前项目")
        file, _ = self.domain.file_record(project_id, obj["file_id"])
        if obj["source_hash"] != file["hash"] or obj["analyzer_version"] != VERSION:
            raise core.ValidationError("天气分析来源或解析器版本已变，请重新分析")
        return obj

    def list(self, project_id):
        result = []
        for obj in self.store.list("weather", project_id):
            try:
                obj = self.get(project_id, obj["weather_id"])
                result.append({k: v for k, v in obj.items() if k not in {"rows", "daily", "heatmap", "upstream"}})
            except (core.ValidationError, KeyError, OSError):
                result.append({"weather_id": obj["weather_id"], "name": obj["name"], "kind": obj["kind"],
                               "invalid": True, "error": "原始来源或分析版本已变化，请重新分析"})
        return result

    def save(self, project_id, file, data, options, provenance):
        obj = {**data, "weather_id": identifier("weather"), "project_id": project_id, "file_id": file["file_id"],
               "source_hash": file["hash"], "analyzer_version": VERSION, "created_at": core.now(),
               "options": options, "provenance": provenance}
        return self.store.put("weather", obj)

    def epw(self, project_id, options):
        file, path = self.domain.file_record(project_id, options.file_id)
        if path.suffix.lower() != ".epw":
            raise core.ValidationError("请选择原始 .epw 文件；日均 CSV/JSON 不能冒充 EPW")
        settings = options.model_dump(exclude={"file_id"})
        with self.lock:
            for previous in self.list(project_id):
                if not previous.get("invalid") and previous["file_id"] == options.file_id and previous["options"] == settings:
                    return self.get(project_id, previous["weather_id"])
            data = analyze_epw(path, options)
            return self.save(project_id, file, data, settings, {"provider": "uploaded_epw", "filename": file["name"],
                "source_note": "用户上传原始文件；来源授权及地点适用性需登记人复核。"})

    def nasa(self, project_id, options):
        self.store.get("project", project_id)
        settings = options.model_dump(mode="json", exclude={"refresh"})
        for previous in self.list(project_id):
            if not options.refresh and not previous.get("invalid") and previous["kind"] == "nasa_daily" and previous["options"] == settings:
                return self.get(project_id, previous["weather_id"])
        if not self.capacity.acquire(blocking=False):
            raise core.ValidationError("天气下载任务已满，请稍后再试")
        params = {"parameters": ",".join(NASA_FIELDS), "community": "RE", "longitude": options.longitude,
                  "latitude": options.latitude, "start": options.start.strftime("%Y%m%d"), "end": options.end.strftime("%Y%m%d"),
                  "format": "JSON", "time-standard": "LST"}
        url = NASA_URL+"?"+urlencode(params)
        try:
            with httpx.Client(timeout=45, follow_redirects=False) as client:
                with client.stream("GET", url) as response:
                    response.raise_for_status()
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 5*1024*1024:
                            raise core.ValidationError("NASA 响应超过 5 MB 限制")
            data = analyze_nasa(json.loads(raw), options)
            file = self.domain.add_file(project_id, f"NASA_POWER_{options.start}_{options.end}.json", bytes(raw))
            return self.save(project_id, file, data, settings, {"provider": "NASA POWER", "url": url,
                "retrieved_at": core.now(), "attribution": "NASA POWER Project, NASA Langley Research Center",
                "documentation": "https://power.larc.nasa.gov/docs/services/api/temporal/daily/"})
        except (httpx.HTTPError, json.JSONDecodeError):
            raise core.ValidationError("NASA 数据服务请求失败或返回非 JSON；没有生成替代数据，请稍后重试") from None
        finally:
            self.capacity.release()

    def csv(self, project_id, weather_id):
        obj = self.get(project_id, weather_id)
        stream = io.StringIO(newline="")
        rows = obj["rows"]
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ["date"])
        writer.writeheader()
        writer.writerows(rows)
        return stream.getvalue().encode("utf-8-sig")
