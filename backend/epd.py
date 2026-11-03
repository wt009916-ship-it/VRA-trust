"""Immutable official CSV releases, searchable declarations and scoped GWP arithmetic.

The library does not approve project applicability, procurement, or carbon credits.
Only an explicit, unambiguous EN15804+A2 module combination may be calculated.
"""
import csv
import io
import json
import math
import re
import shutil
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import Query
from pydantic import Field

from . import core
from .schema import Contract

SOURCE_URL = 'https://www.oekobaudat.de/OEKOBAU.DAT/resource/datastocks/cc64f7e1-14d8-4a57-b11b-2cf03d200c82/exportCSV'
TERMS_URL = 'https://oekobaudat.de/en/guidance/data-users.html'
UNITS = {'kg': 'kg', 'qm': 'm2', 'm2': 'm2', 'm3': 'm3', 'pcs.': 'item'}
REQUIRED = {'UUID', 'Version', 'Name (en)', 'Typ', 'Bezugsgroesse', 'Bezugseinheit',
            'Modul', 'Szenario', 'GWPtotal (A2)', 'Konformitaet', 'Gueltig bis', 'URL'}


class EpdReference(Contract):
    release_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    uuid: str = Field(pattern=r'^[a-f0-9-]{36}$')
    version: str = Field(min_length=1, max_length=40)


class EpdCalculation(EpdReference):
    quantity: float = Field(gt=0, le=1e9, strict=True)
    unit: Literal['kg', 'm2', 'm3', 'item']
    boundary: Literal['A1-A3', 'A1-A5'] = 'A1-A3'


def number(value):
    if value is None or not value.strip():
        return None
    try:
        result = float(value)
    except ValueError as exc:
        raise core.ValidationError('EPD数值格式无效；需使用点号小数的官方CSV') from exc
    if not math.isfinite(result):
        raise core.ValidationError('EPD含非有限数值')
    return result


def parse_csv(path, *, encoding):
    path = Path(path)
    if not 0 < path.stat().st_size <= 150_000_000:
        raise core.ValidationError('EPD原件须为非空且不超过150MB')
    data = path.read_bytes()
    try:
        text = data.decode(encoding)
        reader = csv.DictReader(io.StringIO(text), delimiter=';', strict=True)
        fields = reader.fieldnames or []
        if len(fields) != len(set(fields)) or not REQUIRED.issubset(fields):
            raise core.ValidationError('不是受支持的ÖKOBAUDAT点号小数CSV表头')
        grouped = defaultdict(list)
        for line, raw in enumerate(reader, 2):
            if line > 100001 or None in raw or any(v is None for v in raw.values()):
                raise core.ValidationError('EPD行数或列数不正确')
            uid = str(UUID(raw['UUID']))
            if uid != raw['UUID'] or not re.fullmatch(r'\d{2}\.\d{2}\.\d{3}', raw['Version']):
                raise core.ValidationError('EPD标识或版本无效')
            amount = number(raw['Bezugsgroesse'])
            if amount is not None and amount <= 0:
                raise core.ValidationError('EPD声明量非正')
            number(raw['GWPtotal (A2)'])  # Missing is permitted and remains unknown.
            grouped[(uid, raw['Version'])].append({'csv_line': line, 'values': raw})
    except (UnicodeError, csv.Error, ValueError) as exc:
        raise core.ValidationError('EPD原件解析失败：'+str(exc)[:200]) from exc
    if not grouped:
        raise core.ValidationError('EPD原件没有数据行')
    datasets = []
    identity = ['Name (en)', 'Name (de)', 'Typ', 'Bezugsgroesse', 'Bezugseinheit',
                'Konformitaet', 'Gueltig bis', 'Laenderkennung', 'Declaration owner']
    for (uid, version), rows in grouped.items():
        first = rows[0]['values']
        if any(any(row['values'].get(k) != first.get(k) for k in identity) for row in rows):
            raise core.ValidationError('同一UUID/版本的声明信息冲突：'+uid)
        datasets.append({'uuid': uid, 'version': version, 'name': first['Name (en)'] or first.get('Name (de)', ''),
                         'category': first.get('Kategorie (en)', ''), 'dataset_type': first['Typ'],
                         'region': first.get('Laenderkennung', ''), 'owner': first.get('Declaration owner', ''),
                         'unit': UNITS.get(first['Bezugseinheit']), 'declared_unit': first['Bezugseinheit'],
                         'declared_amount': number(first['Bezugsgroesse']), 'valid_until_year': first['Gueltig bis'],
                         'standard': first['Konformitaet'], 'background_database': first.get('Hintergrunddatenbank(en)', ''),
                         'registration': first.get('Registrierungsnummer', ''),
                         'source_url': f'https://www.oekobaudat.de/OEKOBAU.DAT/resource/processes/{uid}?version={version}', 'rows': rows})
    return data, datasets


class EpdLibrary:
    def __init__(self, store):
        self.store = store
        with store.connect() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS epd_releases(sha256 TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS epd_datasets(release_sha256 TEXT NOT NULL, uuid TEXT NOT NULL,
                    version TEXT NOT NULL, name TEXT NOT NULL, category TEXT NOT NULL,
                    dataset_type TEXT NOT NULL, unit TEXT, body TEXT NOT NULL,
                    PRIMARY KEY(release_sha256,uuid,version));
                CREATE INDEX IF NOT EXISTS epd_filter ON epd_datasets(release_sha256,dataset_type,unit);
                CREATE TABLE IF NOT EXISTS epd_active(singleton INTEGER PRIMARY KEY CHECK(singleton=1), sha256 TEXT NOT NULL);
            ''')

    def import_csv(self, path, *, encoding='cp1252'):
        data, datasets = parse_csv(path, encoding=encoding)
        digest = core.sha(path)
        archive = self.store.root/'epd-sources'/f'{digest}.csv'
        archive.parent.mkdir(exist_ok=True)
        if archive.exists() and core.sha(archive) != digest:
            raise core.ValidationError('EPD归档已损坏，未覆盖原件')
        if not archive.exists():
            shutil.copyfile(path, archive)
        if core.sha(archive) != digest:
            raise core.ValidationError('EPD归档哈希不符')
        release = {'sha256': digest, 'source_url': SOURCE_URL, 'terms_url': TERMS_URL, 'encoding': encoding,
                   'bytes': len(data), 'dataset_count': len(datasets), 'module_rows': sum(len(d['rows']) for d in datasets),
                   'types': dict(Counter(d['dataset_type'] for d in datasets)), 'imported_at': core.now(),
                   'notice': '官方公开声明数据，尚未核定中国本项目适用性；不是产品采购批准、完整LCA或碳信用。'}
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            old = con.execute('SELECT body FROM epd_releases WHERE sha256=?', (digest,)).fetchone()
            if old:
                release = json.loads(old[0])
            else:
                con.execute('INSERT INTO epd_releases VALUES (?,?)', (digest, json.dumps(release, ensure_ascii=False)))
                con.executemany('INSERT INTO epd_datasets VALUES (?,?,?,?,?,?,?,?)',
                    [(digest, d['uuid'], d['version'], d['name'], d['category'], d['dataset_type'], d['unit'],
                      json.dumps(d, ensure_ascii=False, allow_nan=False)) for d in datasets])
            con.execute('INSERT INTO epd_active VALUES (1,?) ON CONFLICT(singleton) DO UPDATE SET sha256=excluded.sha256', (digest,))
        return release

    def release(self, digest=None):
        with self.store.connect() as con:
            if digest is None:
                row = con.execute('SELECT sha256 FROM epd_active WHERE singleton=1').fetchone()
                if not row:
                    return None
                digest = row[0]
            row = con.execute('SELECT body FROM epd_releases WHERE sha256=?', (digest,)).fetchone()
        if not row:
            raise core.ValidationError('EPD来源版本不存在，请刷新资料库')
        return json.loads(row[0])

    def search(self, query='', page=1, dataset_type='', unit=''):
        release = self.release()
        if release is None:
            return {'release': None, 'items': [], 'total': 0, 'page': page, 'page_size': 20, 'pages': 0}
        where, args = ['release_sha256=?'], [release['sha256']]
        if query.strip():
            where.append("(instr(lower(name),?)>0 OR instr(lower(category),?)>0 OR instr(uuid,?)>0)")
            args.extend([query.strip().lower()]*3)
        for column, value in [('dataset_type', dataset_type), ('unit', unit)]:
            if value:
                where.append(column+'=?')
                args.append(value)
        clause = ' AND '.join(where)
        with self.store.connect() as con:
            count = con.execute('SELECT COUNT(*) FROM epd_datasets WHERE '+clause, args).fetchone()[0]
            rows = con.execute('SELECT body FROM epd_datasets WHERE '+clause+' ORDER BY name,uuid,version LIMIT 20 OFFSET ?',
                               [*args, (page-1)*20]).fetchall()
        items = []
        for row in rows:
            d = json.loads(row[0])
            items.append({k: v for k, v in d.items() if k != 'rows'})
        return {'release': release, 'items': items, 'total': count, 'page': page, 'page_size': 20, 'pages': math.ceil(count/20)}

    def calculate(self, reference, quantity, unit, boundary):
        release = self.release(reference.release_sha256)
        path = self.store.root/'epd-sources'/f'{release["sha256"]}.csv'
        if not path.is_file() or core.sha(path) != release['sha256']:
            raise core.ValidationError('EPD原件缺失或哈希失效，拒绝生成材料碳结果')
        with self.store.connect() as con:
            row = con.execute('SELECT body FROM epd_datasets WHERE release_sha256=? AND uuid=? AND version=?',
                              (reference.release_sha256, reference.uuid, reference.version)).fetchone()
        if not row:
            raise core.ValidationError('EPD UUID/版本不存在')
        dataset = json.loads(row[0])
        gaps = []
        if dataset['declared_amount'] is None:
            gaps.append('源声明量缺失，未默认按1单位核算')
        if dataset['unit'] is None or dataset['unit'] != unit:
            gaps.append('工程量与EPD声明单位不同；未根据密度或厚度猜测换算')
        if '15804+A2' not in dataset['standard']:
            gaps.append('当前核算仅支持EN15804+A2的GWP-total，不混用A1口径')
        expiry = dataset['valid_until_year']
        if not expiry.isdigit() or int(expiry) <= date.today().year:
            gaps.append('声明已过有效年或仅提供本年到期年份；须核实确切有效日期')
        rows = dataset['rows']
        combinations = [('A1-A3',)] if boundary == 'A1-A3' else [('A1-A3', 'A4', 'A5')]
        # Also permit explicitly disaggregated manufacturing, never both summed twice.
        combinations += [('A1', 'A2', 'A3')] if boundary == 'A1-A3' else [('A1', 'A2', 'A3', 'A4', 'A5')]
        chosen = None
        for modules in combinations:
            available = [[r for r in rows if r['values']['Modul'] == module] for module in modules]
            if all(len(options) == 1 and not options[0]['values']['Szenario'].strip() for options in available):
                chosen = [options[0] for options in available]
                break
        if chosen is None:
            gaps.append('生命周期模块缺失或存在多情景；未挑选、累加替代情景或自动补零')
        values = [number(r['values']['GWPtotal (A2)']) for r in chosen] if chosen else []
        if chosen and any(v is None for v in values):
            gaps.append('所选模块GWP-total缺失；未将空白解释成0')
        factor = math.fsum(values)/dataset['declared_amount'] if chosen and not gaps else None
        return {'reference': reference.model_dump(), 'dataset': {k: v for k, v in dataset.items() if k != 'rows'},
                'quantity': quantity, 'unit': unit, 'boundary': boundary, 'gwp_per_unit': factor,
                'material_kgco2e': quantity*factor if factor is not None else None,
                'state': 'CALCULATED_DECLARATION_ONLY' if factor is not None else 'NEEDS_EVIDENCE', 'gaps': gaps,
                'source_rows': chosen or [], 'release': release,
                'project_applicability': 'NOT_REVIEWED', 'issued_credits_t': None,
                'notice': '仅为所选声明阶段与工程量的材料GWP；允许有来源的负值，但不等于全生命周期负碳、节能量或可售碳信用。'}


def register_epds(app, service):
    library = service.epds = EpdLibrary(service.store)

    @app.get('/api/projects/{project_id}/sustainability/epds')
    def search(project_id: str, query: str = Query('', max_length=200), page: int = Query(1, ge=1, le=10000),
               dataset_type: str = Query('', max_length=80), unit: str = Query('', max_length=10)):
        service.store.get('project', project_id)
        return library.search(query, page, dataset_type, unit)

    @app.post('/api/projects/{project_id}/sustainability/epds/calculate')
    def calculate(project_id: str, body: EpdCalculation):
        service.store.get('project', project_id)
        return library.calculate(EpdReference(**body.model_dump(include=set(EpdReference.model_fields))),
                                 body.quantity, body.unit, body.boundary)
