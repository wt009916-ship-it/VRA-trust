"""Archive and validate a bounded China regional reference catalogue; no project mutation."""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlencode, urljoin, urlsplit
import zipfile

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import core
from backend.weather import AnalysisOptions, NASA_FIELDS, NASA_URL, NASARequest, analyze_epw, analyze_nasa

BASE = 'https://climate.onebuilding.org/WMO_Region_2_Asia/'
PAGES = {'CHN': BASE+'CHN_China/index.html', 'HKG': BASE+'HKG_Hong_Kong/index.html', 'TWN': BASE+'TWN_Taiwan/index.html'}
GEOL = 'https://chinalex.geolex.org/searchAPI.php?response=long'
PATTERN = re.compile(r'^(CHN|HKG|TWN)_([A-Z]+)_(.+)\.([0-9]{5,8})_(CSWD|TMYx(?:\.\d{4}-\d{4})?)\.zip$')


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a' and (href := dict(attrs).get('href')):
            self.hrefs.append(href)


def catalogue(data, url):
    parser = Links()
    parser.feed(data.decode('utf-8', errors='replace'))
    items = {}
    for href in parser.hrefs:
        link = urljoin(url, href)
        parts = urlsplit(link)
        match = PATTERN.fullmatch(parts.path.rsplit('/', 1)[-1])
        if parts.scheme != 'https' or parts.netloc != 'climate.onebuilding.org' or not parts.path.startswith('/WMO_Region_2_Asia/') or not match:
            continue
        country, area, name, station, edition = match.groups()
        region = area if country == 'CHN' else country
        key = core.hash_json(link)
        items[key] = {'id': key, 'region': region, 'name': name.replace('.', ' '), 'station': station,
                      'edition': edition, 'source_url': link, 'status': 'CATALOGUED'}
    return list(items.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--per-region', type=int, choices=range(1, 6), default=2)
    parser.add_argument('--seed', type=Path, help='Optional saved original sources from the same provider')
    a = parser.parse_args()
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out/'epw').mkdir()
    (out/'archives').mkdir()
    rows, sources, failures = [], {}, []
    with httpx.Client(timeout=60, follow_redirects=False) as client:
        def fetch(name, url, bound):
            target = out/name
            with client.stream('GET', url) as response:
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > bound:
                        raise ValueError('Public source exceeds download budget')
            target.write_bytes(data)
            return bytes(data), {'url': url, 'sha256': core.sha(target), 'bytes': len(data)}

        for code, url in PAGES.items():
            try:
                seed = a.seed/'weather-index.raw' if a.seed and code == 'CHN' else None
                if seed and seed.is_file():
                    raw = seed.read_bytes()
                    (out/'CHN.html').write_bytes(raw)
                    meta = {'url': url, 'sha256': core.sha(seed), 'bytes': len(raw)}
                else:
                    raw, meta = fetch(code+'.html', url, 4_000_000)
                sources[code] = meta
                rows.extend(catalogue(raw, url))
            except (ValueError, httpx.HTTPError) as exc:
                failures.append({'source': code, 'error': str(exc)[:240]})
        grouped = defaultdict(list)
        for row in rows:
            grouped[row['region']].append(row)
        sample = []
        for group in grouped.values():
            seen = set()
            for row in sorted(group, key=lambda r: (r['edition'] != 'TMYx.2011-2025', r['station'], r['id'])):
                if row['station'] not in seen:
                    sample.append(row)
                    seen.add(row['station'])
                if len(seen) == a.per_region:
                    break
        core.write_json(out/'frozen-weather-sample.json', [{**r} for r in sample])

        def analyze(row):
            key = row['id']
            try:
                archive, meta = fetch('archives/'+key+'.zip', row['source_url'], 3_000_000)
                with zipfile.ZipFile(io.BytesIO(archive)) as z:
                    matches = [m for m in z.infolist() if m.filename.lower().endswith('.epw') and not m.is_dir()]
                    if len(matches) != 1 or matches[0].file_size > 5_000_000:
                        raise ValueError('Archive must contain one bounded EPW')
                    member = matches[0]
                    target = out/'epw'/f'{key}.epw'
                    target.write_bytes(z.read(member))
                result = analyze_epw(target, AnalysisOptions())
                row.update(status='QA_PASSED' if result['quality']['simulation_candidate'] else 'QA_BLOCKED',
                           archive_sha256=meta['sha256'], epw_sha256=core.sha(target), archive_member=member.filename,
                           location=result['location'], annual=result['annual'], quality=result['quality'])
            except (ValueError, OSError, httpx.HTTPError, zipfile.BadZipFile) as exc:
                row.update(status='FAILED', error=str(exc)[:240])
            print(row['region'], row['station'], row['status'], flush=True)

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(analyze, sample))
        seed = a.seed/'geology-formations.raw' if a.seed else None
        if seed and seed.is_file():
            raw = seed.read_bytes()
            (out/'geology.json').write_bytes(raw)
            sources['geology'] = {'url': GEOL, 'sha256': core.sha(seed), 'bytes': len(raw)}
        else:
            raw, sources['geology'] = fetch('geology.json', GEOL, 15_000_000)
        geo = json.loads(raw)
        if not isinstance(geo, dict) or not geo or not all(isinstance(d, dict) and d.get('name') for d in geo.values()):
            raise ValueError('Unexpected ChinaLex source contract')
        daily_regions = []
        try:
            option = NASARequest(latitude=22.1987, longitude=113.5439, start=date(2024, 1, 1),
                                 end=date(2024, 12, 31), label='澳门参考格点')
            url = NASA_URL+'?'+urlencode({'parameters': ','.join(NASA_FIELDS), 'community': 'RE',
                'latitude': option.latitude, 'longitude': option.longitude, 'start': '20240101', 'end': '20241231',
                'format': 'JSON', 'time-standard': 'LST'})
            data, sources['MAC'] = fetch('macao-nasa.json', url, 3_000_000)
            result = analyze_nasa(json.loads(data), option)
            rows.append({'id': core.hash_json(url), 'region': 'MAC', 'name': option.label,
                         'station': 'NASA POWER', 'edition': '2024 日值', 'source_url': url,
                         'status': 'DAILY_REFERENCE', 'annual': result['annual'], 'quality': result['quality'],
                         'source_sha256': sources['MAC']['sha256']})
            daily_regions.append('MAC')
        except (ValueError, httpx.HTTPError) as exc:
            failures.append({'source': 'MAC NASA POWER', 'error': str(exc)[:240]})
        core.write_json(out/'catalogue.json', {'built_at': core.now(), 'sources': sources, 'weather': rows,
            'coverage': {'weather_regions': sorted(grouped), 'weather_archives': sum(r['status'] != 'DAILY_REFERENCE' for r in rows),
                         'weather_station_keys': len({(r['region'], r['station']) for r in rows if r['status'] != 'DAILY_REFERENCE'}),
                         'download_attempts': len(sample), 'daily_reference_regions': daily_regions, 'geology_formations': len(geo)},
            'failures': failures})
        print('Catalogue saved', len(rows), len(geo), flush=True)


if __name__ == '__main__':
    main()
