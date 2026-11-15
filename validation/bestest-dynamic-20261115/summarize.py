"""Post-run diagnosis; archived EnergyPlus values are never independent truth."""
import hashlib,json
from pathlib import Path
from read_xlsx import sheets
BASE=Path(__file__).parent
f=json.loads((BASE/'reference-frozen-v2.json').read_text())
rows=[r for n in ['native-v4-first','native-v4-remaining'] for r in json.loads((BASE/n/'receipt.json').read_text())['cases']]
lookup={r['case']:r for r in rows}
table=BASE/'public-reference/ASHRAE140-Envelope/Sec5-2out-Part 1 Results and Bar Charts-Cases 600 thru 900.xlsx'
cells={k:v for row in dict(sheets(table))['RESULTS1'] for k,v in row.items()}
historical=[];outside=[]
for c in f['cases']:
    for m in c['metrics']:
        actual=lookup[c['case']]['metrics'][m['key']]
        cached=cells.get(m['excluded_energyplus_cell'],{}).get('value')
        historical_value=float(cached) if cached and cached.strip() else None
        historical.append({'case':c['case'],'key':m['key'],'current':actual,'archived_energyplus':historical_value,
                           'difference':actual-historical_value if historical_value is not None else None,'locator':'RESULTS1!'+m['excluded_energyplus_cell'],
                           'role':'post-run diagnosis only; same engine family, not independent validation'})
        if not m['minimum']<=actual<=m['maximum']:
            boundary=m['minimum'] if actual<m['minimum'] else m['maximum']
            outside.append({'case':c['case'],'key':m['key'],'actual':actual,'minimum':m['minimum'],'maximum':m['maximum'],
                            'signed_distance_to_range':actual-boundary,'archived_energyplus':historical_value})
(BASE/'historical-energyplus-diagnostic.json').write_text(json.dumps(historical,indent=2)+'\n',encoding='utf-8')
pairs=json.loads((BASE/'paired-observations.json').read_text());http=json.loads((BASE/'http-integrated-v1/summary.json').read_text())
summary={'reference_sha256':hashlib.sha256((BASE/'reference-frozen-v2.json').read_bytes()).hexdigest(),
 'candidate_parent':'f32b4f4fd9e86324164e48f8b646d6e18923438e','source_commit':f['source_commit'],
 'scope':'17 fixed historical envelope/fabric cases,67 scalar metrics,24 within-program paired load differences; not the complete standard or field calibration',
 'native_cases':len(rows),'scalar_inside':67-len(outside),'scalar_count':67,'outside':outside,
 'paired_inside':sum(r['within_range'] for r in pairs),'paired_count':len(pairs),'paired_outside':[{k:r[k] for k in ['changed','baseline','key','minimum','maximum','actual']} for r in pairs if not r['within_range']],
 'native_warnings':'Ground temperature applicability warning in every case; Case960 also has world-coordinate/axis warning; kept for professional review; no severe/fatal in final17.',
 'http_integration':{'cases':17,'checks':len(http['checks']),'all_checks_passed':http['all_checks_passed'],'server_stopped':http['server_stopped'],'note':'Repeated same fixed cases for integration, not 17 extra independent references'},
 'unit_tests':{'backend_targeted':63,'frontend':258,'frontend_build':'passed after missing junction corrected; first failure retained'},
 'original_failures':['First workbook reader treated chartsheet as worksheet; fixed skip for nonworksheet relations only',
 'First freeze script used string path; corrected before any native run; v1/v2 retained',
 'First native harness mkdir on existing temp dir failed before engine',
 'First engine v2 rejected10 severe legacy field schema errors; no simulated hours',
 'Next v3 engine rejected missed IdealLoads inlet node field; v4 field mapping preserved separately',
 'Existing application rejected32-column public weather; actualHTTP409/no run saved',
 'First isolated build lacked dependency junction; corrected environment only',
 'Post-run historical diagnostic found absent archivedEnergyPlus cells; kept null without affecting frozen external-program intervals'],
 'product_change':'Read-only uniform32-column EPW support, explicit absent columns with unknown numeric values, retained strict35 and critical data validation, UI notification',
 'score':79,'score_delta':0,'published_score':76,'browser':'deferred_by_user','field_validation':'unavailable_no_authorized_building_data',
 'decision':'No reference interval widening, no physical parameter fitting, no replacement of missing observations. Comparative discrepancies remain open; no full-standard/engineering-compliance claim.'}
(BASE/'assessment.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'native_cases':len(rows),'outside':outside,'http_checks':len(http['checks'])},ensure_ascii=False))
