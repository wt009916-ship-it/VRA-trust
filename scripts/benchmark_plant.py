"""Reproduce source-bound operating-point calibration from a CSV and explicit mapping."""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import core
from backend.plant_calibration import PlantFit, analyze_plant


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', required=True, type=Path)
    parser.add_argument('--mapping', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    # New directory required: an old failure is never overwritten by a new run.
    args.out.mkdir(parents=True, exist_ok=False)
    settings = PlantFit(**json.loads(args.mapping.read_text(encoding='utf-8')))
    summary, rows = analyze_plant(args.csv, settings)
    record = {'created_at': core.now(), 'source_sha256': core.sha(args.csv),
              'rules_sha256': core.sha(Path(__file__).resolve().parents[1]/'backend/plant_calibration.py'), 'options': settings.model_dump(), 'result': summary}
    (args.out/'result.json').write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    with (args.out/'audit.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=sorted({key for row in rows for key in row}))
        writer.writeheader()
        writer.writerows(rows)
    print(summary['status'], 'rows', summary['rows'], 'water balance failures', summary['balance_failed_rows'])


if __name__ == '__main__':
    main()
