"""Extract public, credential-free result tables from actual saved benchmark runs."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--evidence', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    root = args.evidence

    def read(path):
        return json.loads((root/path).read_text(encoding='utf8'))

    weather = []
    for path in sorted((root/'weather-vra').glob('USA*.json')):
        a = read('weather-vra/'+path.name)
        row = {'file':path.stem, 'records':len(a['temperature']), **a['annual'], 'comparisons':{}}
        for engine in ['ladybug','pvlib']:
            b = read('weather-'+engine+'/'+path.name)
            native_diff = max(abs(x-y) for x,y in zip(a['temperature'],b['temperature']))
            aligned = b['temperature'][1:]+b['temperature'][:1] if engine=='ladybug' else b['temperature']
            row['comparisons'][engine] = {
                'native_order_temperature_max_difference_c':native_diff,
                'aligned_temperature_max_difference_c':max(abs(x-y) for x,y in zip(a['temperature'],aligned)),
                'ghi_max_difference_wh_m2':max(abs(x-y) for x,y in zip(a['ghi'],b['ghi'])),
                'annual_mean_difference_c':a['annual']['temperature_c']-sum(b['temperature'])/len(b['temperature']),
                'annual_ghi_difference_kwh_m2':a['annual']['solar_kwh_m2']-sum(b['ghi'])/1000,
                'alignment':'Undo Ladybug EPW point-in-time last-to-first rotation; epw.py lines 577-582' if engine=='ladybug' else 'Original row order'}
        weather.append(row)
    agents = []
    for round_name in ['agents-after','agents-repeat']:
        for row in read(round_name+'/results.json'):
            result = row.get('result', {})
            if row['engine']=='vra':
                final = result.get('llm_commentary')
                tools = [e['tool'] for e in result.get('events',[]) if e['tool']!='llm.request']
                authoritative_weather = bool((result.get('answer') or {}).get('weather'))
            else:
                final = result.get('messages',[{}])[-1].get('content')
                tools = [e['tool'] for e in row['tool_trace']]
                authoritative_weather = None
            agents.append({'round':round_name,'engine':row['engine'],'case':row['case'],
                'question':row['question'],'runtime_status':row['status'],'seconds':row['seconds'],
                'final_text_verbatim':final,'tools':tools,'vra_structured_weather_present':authoritative_weather,
                'source_sha256':hashlib.sha256((root/round_name/f"{row['case']}-{row['engine']}.json").read_bytes()).hexdigest()})
    native = read('duplex-cli/comparison.json')
    ifc = read('ifc-schependomlaan/results.json')
    ifc64 = read('ifc-schependomlaan-64mb/results.json')
    summary = {'scope':'Measured software behavior on public inputs; not calibrated building accuracy or commercial product ranking',
        'baseline_commit':'f7dd5d09a14b8dc3c20bacec878f312f62f0b48d',
        'weather':weather,'weather_mutations':{e:[r for r in read('weather-'+e+'/results.json')['rows'] if r.get('synthetic_mutation')]
            for e in ['vra','ladybug','pvlib']},
        'native_engine':native,
        'ifc':{'sha256':ifc['sha256'],'bytes':ifc['bytes'],'inventory':ifc['inventory'],
            'default_upload_http':ifc['api_upload']['status'],'configured_64mb_upload_http':ifc64['api_upload']['status'],
            'configured_64mb_import_http':ifc64['api_import']['status'],
            'geometry':read('ifc-representation-diagnostic.json')['counts'],
            'representations':read('ifc-representation-diagnostic.json')['representation_types']},
        'agents':agents,'authorization_control':read('agents-repeat/direct-authorization-control.json'),
        'versions':read('agents-after/versions.json'),
        'not_measured':['Glodon','THS/斯维尔','Revit','Claude','ChatGPT','Dify','OpenStudio'],
        'limits':['Five US TMY files, not China coverage','Duplex was previously used during development; Schependomlaan was new',
            'Qwen 0.6B CPU only; no model training; frameworks share production tools',
            'Fresh project IDs/timestamps between repetitions; within each round the same project is used',
            'No energy bills/field measurements, no commercial software licenses, no speed superiority claim']}
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    with (args.output/'weather.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer = csv.DictWriter(f,fieldnames=['file','records','temperature_c','heating_degree_days','cooling_degree_days','solar_kwh_m2'])
        writer.writeheader()
        writer.writerows({k:v for k,v in row.items() if k!='comparisons'} for row in weather)
    (args.output/'agent-verbatim.json').write_text(json.dumps(agents,ensure_ascii=False,indent=2),encoding='utf8')
    (args.output/'requirements-benchmark.lock.txt').write_bytes((root/'requirements-benchmark.lock.txt').read_bytes())
    files = [p for p in root.rglob('*') if p.is_file() and 'private-runtime' not in str(p) and
             p.suffix in {'.json','.csv','.log','.txt','.py','.idf','.epw','.sql','.err','.html','.pdf','.zip'}
             and not p.name.endswith('.partial')]
    hashes = {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (args.output/'evidence-index.json').write_text(json.dumps(hashes,indent=2),encoding='utf8')
    print(json.dumps({'weather_files':len(weather),'agent_runs':len(agents),'indexed_evidence':len(hashes)}))


if __name__ == '__main__':
    main()
