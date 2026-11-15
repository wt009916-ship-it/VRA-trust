import hashlib,json,math,re
from pathlib import Path
from read_xlsx import sheets

BASE=Path(__file__).parent
PUBLIC=BASE/'public-reference'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def cells(rows):return {k:v for row in rows for k,v in row.items()}
acquisition=json.loads((BASE/'acquisition.json').read_text())
source=PUBLIC/'ASHRAE140-Envelope'
summary=source/'BESTEST Comparison with Reference Results.xlsx'
table=source/'Sec5-2out-Part 1 Results and Bar Charts-Cases 600 thru 900.xlsx'
data={name:cells(rows) for name,rows in sheets(summary)}
raw=cells(dict(sheets(table))['RESULTS1'])
cases={k:{'case':k,'metrics':[]} for k in acquisition['cases_fixed_before_run']}
kind_rows={'Cases 600':[(21,'heating_mwh'),(30,'cooling_mwh'),(39,'peak_heating_kw'),(48,'peak_cooling_kw')],
 'Cases 900':[(21,'heating_mwh'),(30,'cooling_mwh'),(39,'peak_heating_kw'),(48,'peak_cooling_kw')],
 'Free Float Cases':[(21,'temperature_max_c'),(30,'temperature_min_c'),(39,'temperature_mean_c')]}
def value(cell):return cell['value']
for sheet,metrics in kind_rows.items():
    d=data[sheet]
    cols={re.sub(r'\d+','',k):value(v) for k,v in d.items() if re.fullmatch('[A-Z]+11',k) and value(v) in cases}
    for col,case in cols.items():
        for row,key in metrics:
            cell=col+str(row);match=re.fullmatch(r'\[1\]RESULTS1!\$N\$(\d+)',d[cell]['formula']);assert match,cell
            r=int(match[1]);programs={}
            for c in 'BCDEFGHIJKL':
                x=raw.get(c+str(r),{}).get('value')
                if x is None or not x.strip():continue
                n=float(x);assert math.isfinite(n);programs[c+str(r)]=n
            assert len(programs)>=2
            low,high=min(programs.values()),max(programs.values())
            assert math.isclose(low,float(value(d[cell])),abs_tol=1e-10)
            assert math.isclose(high,float(value(d[col+str(row+1)])),abs_tol=1e-10)
            cases[case]['metrics'].append({'key':key,'minimum':low,'maximum':high,'independent_program_values':programs,
              'excluded_energyplus_cell':'M'+str(r),'source_sheet':'RESULTS1','source_range':'B'+str(r)+':L'+str(r),
              'summary_locator':sheet+'!'+cell+':'+col+str(row+1),'kind':'external_program_comparative_range_not_exact_truth'})
out=BASE/'frozen-inputs-v1';out.mkdir(exist_ok=False)
for case,item in cases.items():
    p=source/'Inputs'/('Case'+case+'.idf');original=p.read_bytes()
    body,n=re.subn(rb'(?i)\bVERSION\s*,\s*\.\s*;',b'Version,9.0;',original);assert n==1
    addition=b'\n! VRA audit output-only requests. Physical source fields unchanged.\nOutput:SQLite,SimpleAndTabular;\nOutput:Table:SummaryReports,AllSummary;\n'
    for variable in ['Zone Air Temperature','Zone Air System Sensible Heating Rate','Zone Air System Sensible Cooling Rate']:
        addition+=('Output:Variable,*,'+variable+',Hourly;\n').encode()
    path=out/('Case'+case+'.idf');path.write_bytes(body+addition)
    stripped=re.sub(rb'!.*',b'',body)
    zones=[x.decode().strip() for x in re.findall(rb'(?im)(?:^|;)\s*Zone\s*,\s*([^,]+),',stripped)]
    item.update(source_sha256=sha(p),derived_sha256=sha(path),zones=zones,
      input_derivation='Replace one Version placeholder with explicit9.0; append only SQLite/summary/3 hourly variables. Compatibility unverified before first engine call; original retained.')
    assert item['metrics'] and zones
frozen={'repository':acquisition['repository'],'source_commit':acquisition['commit'],
 'workbooks':{p.name:sha(p) for p in (summary,table)},'weather':{'path':'WeatherData/DRYCOLDTMY.epw','sha256':sha(PUBLIC/'WeatherData/DRYCOLDTMY.epw')},
 'script_sha256':sha(__file__),'reader_sha256':sha(BASE/'read_xlsx.py'),'engine_sha256':sha(Path('F:/EnergyPlusV9-0-1/energyplus.exe')),
 'cases':list(cases.values()),'decision':'All frozen available metrics reported, exact inclusive source ranges without widening; outside range is a comparative discrepancy, not proof of erroneous physics or legal noncompliance.',
 'not_for_redistribution':'Downloaded models/workbooks and derived inputs stay local, provenance and own observations can be published.',
 'sensitivity_scope':'First batch all67 scalar metrics. Paired sensitivity ranges must be separately frozen before analyzing paired outputs, not invented from marginal bounds.'}
assert sum(len(c['metrics']) for c in frozen['cases'])==67
assert not (BASE/'reference-frozen-v1.json').exists()
(BASE/'reference-frozen-v1.json').write_text(json.dumps(frozen,indent=2)+'\n')
print(json.dumps({'cases':len(cases),'metrics':67,'reference_sha256':sha(BASE/'reference-frozen-v1.json'),'zones':{k:v['zones'] for k,v in cases.items()}}))
