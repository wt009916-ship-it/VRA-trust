"""Run with product Python (vra) or independent benchmark environment (others)."""
import argparse
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def read(engine, path):
    if engine == 'vra':
        from backend.weather import AnalysisOptions, analyze_epw
        value = analyze_epw(path, AnalysisOptions())
        return {'temperature': [r['temperature_c'] for r in value['rows']],
                'ghi': [r['ghi_wh_m2'] for r in value['rows']],
                'quality': value['quality'], 'annual': value['annual']}
    if engine == 'ladybug':
        from ladybug.epw import EPW
        value = EPW(str(path))
        return {'temperature': list(value.dry_bulb_temperature.values),
                'ghi': list(value.global_horizontal_radiation.values),
                'time_note': 'Ladybug native collection ordering, preserved without alignment'}
    from pvlib.iotools import read_epw
    value, metadata = read_epw(path, coerce_year=2001)
    return {'temperature': value.temp_air.tolist(), 'ghi': value.ghi.tolist(),
            'metadata': metadata}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', choices=['vra', 'ladybug', 'pvlib'], required=True)
    parser.add_argument('--weather-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    files = sorted(args.weather_dir.glob('*.epw'))
    assert len(files) == 5, 'Protocol expects the five bundled E+ 9.0.1 EPWs'
    rows = []
    # Rotate input order across three repetitions; not independent buildings.
    for repeat in range(3):
        for path in files[repeat:]+files[:repeat]:
            row = {'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                   'engine': args.engine, 'repeat': repeat}
            start = time.perf_counter()
            try:
                data = read(args.engine, path)
                row.update(status='ok', records=len(data['temperature']),
                           temperature_mean=sum(data['temperature'])/len(data['temperature']),
                           ghi_kwh_m2=sum(data['ghi'])/1000)
                if repeat == 0:
                    (args.output/(path.stem+'.json')).write_text(json.dumps(data, ensure_ascii=False), encoding='utf8')
            except Exception as exc:
                row.update(status='error', error=f'{type(exc).__name__}: {exc}')
            row['seconds'] = time.perf_counter()-start
            rows.append(row)
    golden = next(p for p in files if 'Golden' in p.name)
    original = list(csv.reader(golden.read_text().splitlines()))
    for kind in ['missing_hour', 'duplicate_hour', 'missing_temperature']:
        data = [r.copy() for r in original]
        if kind == 'missing_hour':
            del data[108]
        elif kind == 'duplicate_hour':
            data.insert(108, data[108].copy())
        else:
            data[108][6] = '99.9'
        path = args.output/(kind+'.epw')
        with path.open('w', newline='') as handle:
            csv.writer(handle).writerows(data)
        row = {'file': kind, 'synthetic_mutation': True, 'engine': args.engine}
        try:
            result = read(args.engine, path)
            row.update(status='ok', records=len(result['temperature']),
                       missing_temperature_count=result['temperature'].count(None),
                       sentinel_99_9_count=result['temperature'].count(99.9),
                       quality=result.get('quality'), annual=result.get('annual'))
        except Exception as exc:
            row.update(status='error', error=f'{type(exc).__name__}: {exc}')
        rows.append(row)
    version = None if args.engine == 'vra' else importlib.metadata.version({'ladybug':'ladybug-core','pvlib':'pvlib'}[args.engine])
    result = {'engine': args.engine, 'version': version, 'rows': rows,
              'timing_scope': 'In-process parsing and aggregate extraction; first call includes Python imports, no speed ranking.'}
    (args.output/'results.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf8')
    print(json.dumps({'engine': args.engine, 'cases': len(rows), 'failures': [r for r in rows if r['status']=='error']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
