"""Compare production API artifacts with an independent direct EnergyPlus invocation."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import time


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--api-output', type=Path, required=True)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    run = json.loads((args.api_output/'result.json').read_text(encoding='utf8'))
    directory = args.api_output/'private-runtime/runs'/run['run_id']
    idf = next((directory/'input').glob('*.idf')).resolve()
    epw = next((directory/'input').glob('*.epw')).resolve()
    original = {'idf':sha(idf), 'epw':sha(epw)}
    start = time.perf_counter()
    process = subprocess.run([str(args.engine.resolve()), '-w', str(epw), '-d', str(args.output.resolve()), str(idf)],
                             capture_output=True, text=True, timeout=240)
    (args.output/'stdout.txt').write_text(process.stdout, encoding='utf8')
    (args.output/'stderr.txt').write_text(process.stderr, encoding='utf8')
    result = {'engine_exit_code':process.returncode, 'seconds':time.perf_counter()-start,
              'input_sha256':original, 'source_api_run':run['run_id'], 'metrics':{}}
    if process.returncode == 0:
        with sqlite3.connect(args.output/'eplusout.sql') as con:
            for name, locator in run['metrics']['locators'].items():
                rows = con.execute('SELECT Value FROM TabularDataWithStrings WHERE TableName=? AND RowName=? AND ColumnName=? AND Units=?',
                    (locator['table'],locator['row'],locator['column'],locator['unit'])).fetchall()
                assert len(rows)==1, (name,rows)
                value = float(rows[0][0])
                baseline = float(locator['raw_value'])
                result['metrics'][name] = {'api':baseline,'cli':value,'delta':value-baseline,
                                           'within_tolerance':abs(value-baseline)<=.01,'unit':locator['unit']}
            result['time_days'] = con.execute('SELECT MAX(SimulationDays) FROM Time').fetchone()[0]
        err = (args.output/'eplusout.err').read_text(errors='replace')
        result['warning_messages'] = err.count('** Warning **')
        result['severe_messages'] = err.count('** Severe  **')
        result['completed'] = 'EnergyPlus Completed Successfully' in err
    result['sources_unchanged'] = original == {'idf':sha(idf),'epw':sha(epw)}
    (args.output/'comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__':
    main()
