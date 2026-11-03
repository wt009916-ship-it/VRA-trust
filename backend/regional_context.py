"""Project-scoped, offline regional reference. No site/geotechnical assumptions."""
from functools import lru_cache
import math
from pathlib import Path
import re
from typing import Literal

from fastapi import Query
from fastapi.responses import FileResponse

from . import core

REGIONS = dict(zip('AH BJ CQ FJ GD GS GX GZ HA HB HE HI HKG HL HN JL JS JX LN MAC NM NX QH SC SD SH SN SX TJ TWN XJ XZ YN ZJ'.split(),
    '安徽 北京 重庆 福建 广东 甘肃 广西 贵州 河南 湖北 河北 海南 香港 黑龙江 湖南 吉林 江苏 江西 辽宁 澳门 内蒙古 宁夏 青海 四川 山东 上海 陕西 山西 天津 台湾 新疆 西藏 云南 浙江'.split(), strict=True))


@lru_cache(maxsize=8)
def _read(path, size, modified):
    return core.read_json(path)


def snapshot(path):
    stat = path.stat()
    if stat.st_size > 20_000_000:
        raise core.ValidationError('区域资料索引超过加载上限')
    return _read(path, stat.st_size, stat.st_mtime_ns)


def search(root, kind, query, region, page):
    root = Path(root)
    index = root/'catalogue.json'
    if not index.is_file():
        return {'items': [], 'total': 0, 'pages': 0, 'page': page, 'coverage': {}, 'source': None}
    catalogue = snapshot(index)
    needle = query.strip().casefold()
    if kind == 'weather':
        source = {k: v for k, v in catalogue['sources'].items() if k in {'CHN', 'HKG', 'TWN', 'MAC'}}
        rows = [{**r, 'region_name': REGIONS.get(r['region'], r['region'])} for r in catalogue['weather']]
        if region:
            rows = [r for r in rows if r['region'] == region.upper() or r['region_name'] == region]
        fields = ('name', 'region_name', 'station', 'edition')
        rows.sort(key=lambda r: (r['status'] != 'QA_PASSED', r['region'], r['name'], r['edition']))
    else:
        source = catalogue['sources']['geology']
        path = root/'geology.json'
        if not path.is_file() or core.sha(path) != source['sha256']:
            raise core.ValidationError('地层原件缺失或哈希不匹配')
        rows = [{k: r.get(k) for k in ('name', 'province', 'period', 'stage', 'lithology_pattern', 'endAge', 'begAge')}
                for r in snapshot(path).values()]
        if region:
            rows = [r for r in rows if region.casefold() in str(r['province'] or '').casefold()]
        fields = ('name', 'province', 'period', 'stage', 'lithology_pattern')
        rows.sort(key=lambda r: str(r['name']).casefold())
    selected = [r for r in rows if not needle or any(needle in str(r.get(k) or '').casefold() for k in fields)]
    return {'items': selected[(page-1)*20:page*20], 'total': len(selected), 'pages': math.ceil(len(selected)/20),
            'page': page, 'coverage': catalogue['coverage'], 'source': source,
            'scope': '地层词条是区域背景，不是地块点位地质或勘察。岩土参数、地下水位、承载力、地源热泵设计值均不从目录推定。' if kind == 'geology' else
            '典型年是工程气象参考；目录文件、通过逐时检查的原件和现场实测分别计数。仍须复核项目站点与年代。'}


def register_regions(app, domain):
    root = domain.store.root/'regional-context'

    @app.get('/api/projects/{project_id}/weather/regional')
    def catalogue(project_id: str, kind: Literal['weather', 'geology'] = 'weather',
                  query: str = Query('', max_length=120), region: str = Query('', max_length=40),
                  page: int = Query(1, ge=1, le=1000)):
        domain.store.get('project', project_id)
        return search(root, kind, query, region, page)

    @app.get('/api/projects/{project_id}/weather/regional/{entry_id}.epw')
    def epw(project_id: str, entry_id: str):
        domain.store.get('project', project_id)
        if not re.fullmatch(r'[a-f0-9]{64}', entry_id) or not (root/'catalogue.json').is_file():
            raise KeyError(entry_id)
        row = next((r for r in snapshot(root/'catalogue.json')['weather'] if r['id'] == entry_id), None)
        if not row or row['status'] != 'QA_PASSED':
            raise KeyError(entry_id)
        path = core.relative_file(root, 'epw/'+entry_id+'.epw')
        if not path.is_file() or core.sha(path) != row['epw_sha256']:
            raise core.ValidationError('天气原件缺失或哈希不匹配，请重新入库')
        return FileResponse(path, media_type='application/octet-stream', filename=f'{entry_id}.epw')
