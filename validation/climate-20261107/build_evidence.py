"""Final local evidence index; run only after both complete regression logs exist."""
import hashlib,json,re,subprocess,sys
from pathlib import Path
repo=Path(__file__).resolve().parents[2];out=Path(__file__).resolve().parent
sys.path.insert(0,str(repo))
from backend import core
application='1394facc4be2e4ff36799e4c9151188fe89309dc'


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8',newline='\n') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)
def row(path):
    raw=path.read_bytes()
    return {'path':path.relative_to(repo).as_posix(),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def result(path):
    matches=re.findall(r'(\d+) passed, (\d+) skipped,.*?(\d+) subtests passed in ([\d.]+)s',path.read_text(encoding='utf-8'))
    assert matches,path
    p,s,sub,t=matches[-1]
    return {'passed':int(p),'skipped':int(s),'subtests':int(sub),'seconds':float(t),'log':path.relative_to(repo).as_posix()}


windows=result(out/'windows-full-v2.log');linux=result(out/'linux-full-v2.log')
native_w=read(out/'weather-native-v2.json');native_l=read(out/'linux-weather-v2.json')
public=[]
for w,l in zip(native_w['public_climates'],native_l['public_climates'],strict=True):
    assert w['source_sha256']==l['source_sha256'] and w['weather_quality']==l['weather_quality']
    assert w['code_hash']==l['code_hash']==core.code_hash()
    assert w['metrics']=={**l['metrics'],'engine_sql_version':w['metrics']['engine_sql_version']}
    public.append({'station':w['weather_quality']['station'],'weather_sha256':w['source_sha256'],
                   'annual_energy_kwh':w['metrics']['annual_energy_kwh'],'area_m2':w['metrics']['area_m2'],
                   'windows_warnings':w['warnings'],'linux_warnings':l['warnings'],
                   'conditions':w['weather_quality']['conditions'],'windows_manifest_sha256':w['manifest_sha256'],
                   'linux_manifest_sha256':l['manifest_sha256']})
sky=[]
for w,l in zip(native_w['synthetic_sky_checks'],native_l['synthetic_sky_checks'],strict=True):
    assert w['max_absolute_error_C']<=w['tolerance_C'] and l['max_absolute_error_C']<=l['tolerance_C']
    sky.append({key:w[key] for key in ['cloud_cover_tenths','independent_expected_C','hourly_values','tolerance_C']} |
               {'windows_max_absolute_error_C':w['max_absolute_error_C'],'linux_max_absolute_error_C':l['max_absolute_error_C']})
benchmark={'generated_at':core.now(),'application_commit':application,'physics_code_hash':core.code_hash(),
           'scope':'Five fixed-model annual weather scenarios, two independent constant-weather sky checks; not local design or real-building calibration.',
           'public_climates':public,'synthetic_sky':sky,'native_weather_simulations_per_platform':8,
           'new_annual_reference_simulations_per_platform':3,'old_manifests_rewritten':0,
           'design_day_discovery':'All five weather variations retained Golden design days; ZoneSizes is not yet a delivered design-load result.'}
save(repo/'docs/benchmarks/WEATHER_20261107_RESULTS.json',benchmark)
browser_dir=out/'browser';browser_dir.mkdir(exist_ok=False)
for path in sorted((repo/'output/playwright/weather-20261107').iterdir()):
    if path.suffix in {'.json','.png'}:(browser_dir/path.name).write_bytes(path.read_bytes())
assert read(browser_dir/'final-source-report.json')['run']['provenance']['code_version']==core.code_hash()
assert read(browser_dir/'final-api-source-v2.json')['gate']['can_simulate'] is False
assert len(read(browser_dir/'harness-errors.json'))==4
prefix=(f"2026-11-07天气输入更新：关键缺测/范围/年度时钟在准入和物理核心阻断；可选缺测与原生天空推导保留来源回执，报告/ZIP同源。"
        f"最终Windows {windows['passed']}通过/{windows['skipped']}跳过、Linux {linux['passed']}通过/{linux['skipped']}跳过，均6子测试；77前端通过。"
        "双平台各5公开天气+2独立天空公式+1认证API实际仿真，并新跑三方案年度参考。Linux首轮临时调试文件删除竞争失败保留并限定修复；浏览器两处交互缺陷修复，4个脚本/断言失败原样保留。"
        "原型业务原件及历史manifest不改写；评分75保持。下一批重点交付设计日/分区负荷与独立热平衡基准；不同城市天气仍不能替代匹配设计日。"
        "RS-07/RS-09、一般注入、净工程量、图纸修复及实楼验收保留。详[交付](WEATHER_QUALITY_DELIVERY.md)、[证据](WEATHER_QUALITY_EVIDENCE.json)、[复评](RESCORE_20261107_WEATHER.md)。训练和整体视觉后置。\n\n")
for name in ['IMPLEMENTATION_STATUS.md','EXECUTION_PLAN_95_PLUS.md']:
    path=repo/'docs'/name;old=path.read_text(encoding='utf-8');assert not old.startswith('2026-11-07天气输入更新')
    path.write_text(prefix+old,encoding='utf-8',newline='\n')
path=repo/'docs/WEATHER_QUALITY_DELIVERY.md'
text=path.read_text(encoding='utf-8')
text=text.replace('## 测试纪律与下一批',
    f"## 最终局部验证结果\n\n最终Windows：{windows['passed']}通过、{windows['skipped']}跳过、6子测试，{windows['seconds']}秒；Linux：{linux['passed']}通过、{linux['skipped']}跳过、6子测试，{linux['seconds']}秒；前端77项、语法、构建通过。双平台全量存在时间重叠，耗时不是受控性能基准。最终浏览器新建项目→确认→方案切换→实际仿真→JSON/PDF/ZIP完成，5页PDF提取核对天气摘要与条件，旧异常项目仍禁用且返回stale/null。四个早期浏览器失败保留，最终页面脚本异常为零。\n\n## 测试纪律与下一批")
path.write_text(text,encoding='utf-8',newline='\n')
files=[p for p in out.rglob('*') if p.is_file() and p.suffix in {'.json','.log','.py','.cjs','.md','.err','.png'}]
publications=[repo/'docs'/name for name in ['WEATHER_QUALITY_DELIVERY.md','RESCORE_20261107_WEATHER.md',
              'IMPLEMENTATION_STATUS.md','EXECUTION_PLAN_95_PLUS.md','benchmarks/WEATHER_20261107_RESULTS.json']]
index={'schema':'vra.weather.acceptance.v1','generated_at':core.now(),'application_commit':application,
       'physics_code_hash':core.code_hash(),'local_status':'verified','remote_release':'GitHub PR checks and local release-receipt.json are recorded after this immutable local evidence commit.',
       'score':75,'goal_status':'active','training_expanded':False,'real_building_calibration':'not_validated',
       'final_regressions':{'windows':windows,'linux':linux,'frontend_passed':77},
       'historical_failures':['Initial sandbox temporary-directory failure','40 old weather contract failures',
          'First Linux public native run failed on transient eplusout.dbg removal','Initial Windows cached-stat test fixture corrected',
          'Four browser harness/assertion failures, including two product interaction defects',
          'Optional PyMuPDF unavailable; pinned pypdf verified the downloaded PDF',
          'Read-only design-day discovery first used default GBK; explicit UTF-8 retry recorded'],
       'source_snapshots':[read(out/'windows-source-v2.json'),read(out/'linux-source-v2.json')],
       'source_scope':'Final implementation hashes checked; the earlier v1 snapshots remain historical evidence and are not claimed as final.',
       'evidence_files':[row(p) for p in sorted(files)],'publications':[row(p) for p in publications],
       'next_work':'Design-day/zone-load source bindings, independent steady-state benchmark and native sizing output validation; preserve open Agent/file/production gaps.'}
save(repo/'docs/WEATHER_QUALITY_EVIDENCE.json',index)
print(json.dumps({'application_commit':application,'files':len(files),'windows':windows,'linux':linux,'score':75}))
