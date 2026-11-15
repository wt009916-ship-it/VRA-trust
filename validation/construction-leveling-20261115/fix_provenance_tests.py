from pathlib import Path
repo=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
p=repo/'tests/test_calculation_provenance.py'
text=p.read_text(encoding='utf-8');assert text.count('importlib.import_module(service.__module__)')==2
text=text.replace('importlib.import_module(service.__module__)', 'importlib.import_module(service.save.__module__)')
text=text.replace("    module = importlib.import_module(service.save.__module__)\n    function", "    # Fault injection follows the actual inherited calculation method, not its facade class.\n    module = importlib.import_module(service.save.__module__)\n    function")
p.write_text(text,encoding='utf-8')
p=repo/'tests/test_construction_leveling.py'
text=p.read_text(encoding='utf-8')
text+='''

def test_derived_calculator_change_withdraws_results_without_rewriting_original(client, monkeypatch):
    from backend import construction_records
    pid, base, source, _ = saved(client)
    service = ScheduleRecords(client.app.state.domain)
    record = service.level(pid, source['schedule_id'], LevelingRequest(**request(source)))
    monkeypatch.setattr(construction_records, 'version', lambda: 'changed-derived-calculator')
    current = service.view(pid, record['schedule_id'])
    assert current['status'] == 'stale' and current['result'] is None
    assert 'calculator_version' in current['stale_reasons']
    assert service.view(pid, source['schedule_id']) == source
    assert service.store.get('schedule', record['schedule_id'])['result']['leveled']['schedule']['duration_days'] == '6'
'''
p.write_text(text,encoding='utf-8')
print('Fault injection now targets inherited save method; assertions retained. Added derived-version withdrawal check.')
